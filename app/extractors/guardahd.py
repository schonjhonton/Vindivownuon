import logging
import json
import os
import time
import base64
import urllib.parse
from bs4 import BeautifulSoup
from app.utils import get_tmdb_info
from app.resolvers import resolve_supervideo, resolve_mixdrop, resolve_maxstream

logger = logging.getLogger("ITA-Addon")

# --- COSTANTI DAL FILE JS ---
CACHE_FILE = os.path.join(os.getcwd(), 'config', 'guardahd_embeds.json')
CACHE_TTL = 12 * 60 * 60  # 12 Ore in secondi
BASE_URL = 'https://mostraguarda.stream'

# Header copiati ESATTAMENTE dal file JS per bypassare protezioni
HEADERS_DEF = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Referer': 'https://google.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
}

class GuardaHDProvider:
    def get_name(self):
        return "GuardaHD"

    # ==========================================
    # 1. GESTIONE CACHE (Uguale al JS)
    # ==========================================
    def _read_cache(self):
        if not os.path.exists(CACHE_FILE):
            return {}
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_cache(self, cache_data):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass

    def _purge_cache(self, cache):
        now = time.time()
        keys_to_remove = [k for k, v in cache.items() if now - (v.get('timestamp', 0) / 1000) > CACHE_TTL] # JS usa ms, Python s. Adattiamo.
        
        if keys_to_remove:
            for k in keys_to_remove:
                del cache[k]
            self._write_cache(cache)

    # ==========================================
    # 2. HELPER TITOLI (Stile JS)
    # ==========================================
    def _generate_rich_description(self, title, quality="HD"):
        # Replica la funzione generateRichDescription del JS
        lines = [
            f"🎬 {title or 'Video'}",
            f"🇮🇹 ITA • 🔊 AAC",
            f"🎞️ {quality} • Streaming Web",
            f"☁️ Web Stream • ⚡ Instant",
            f"🦁 GuardaHD"
        ]
        return "\n".join(lines)

    # ==========================================
    # 3. LOGICA PRINCIPALE
    # ==========================================
    async def get_stream(self, imdb_id: str, type: str, config: dict, client):
        if type != "movie":
            return []  # Il JS gestisce solo film

        streams = []
        mfp_url = config.get("mfp_url")
        mfp_pass = config.get("mfp_pass")

        if not mfp_url:
            return []

        # Setup Proxy URL e Headers
        base_proxy = mfp_url if mfp_url.endswith('/') else f"{mfp_url}/"
        
        # Uniamo gli header definiti nel JS con l'auth MFP
        request_headers = HEADERS_DEF.copy()
        
        if mfp_pass:
            auth_str = f"admin:{mfp_pass}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            request_headers.update({
                "Authorization": f"Basic {auth_b64}",
                "X-Proxy-Password": mfp_pass,
                "mfp-code": mfp_pass
            })

        # Pulizia ID (tt12345)
        clean_id = imdb_id.split(":")[0]

        # --- GESTIONE CACHE ---
        cache = self._read_cache()
        # Nota: nel JS il timestamp è in ms, qui usiamo ms per compatibilità
        now_ms = time.time() * 1000
        
        cached_entry = cache.get(clean_id)
        embed_urls = []
        real_title = clean_id
        
        # Verifica validità cache (TTL)
        if cached_entry and (now_ms - cached_entry.get('timestamp', 0) < (CACHE_TTL * 1000)):
            logger.info(f"[GH] Cache HIT per {clean_id}")
            embed_urls = cached_entry.get('embedUrls', [])
            real_title = cached_entry.get('title', clean_id)
        else:
            logger.info(f"[GH] Cache MISS per {clean_id}. Scraping...")
            
            # --- SCRAPING (Replica JS fetchText) ---
            # URL: {PROXY}/{BASE_URL}/movie/{IMDB}
            target_url = f"{base_proxy}{BASE_URL}/movie/{clean_id}"
            
            try:
                # Timeout aumentato come nel JS (10000ms)
                res = await client.get(target_url, headers=request_headers, allow_redirects=True, timeout=10)
                
                if res.status_code == 200:
                    html = res.text
                    soup = BeautifulSoup(html, 'lxml')
                    
                    # Estrazione Titolo
                    page_title = soup.find('h1')
                    if page_title:
                        real_title = page_title.text.strip().replace('Streaming', '').strip()

                    # Estrazione Embed (extractEmbedUrlsFromHtml del JS)
                    raw_urls = []
                    for tag in soup.select('[data-link]'):
                        u = tag.get('data-link', '').strip()
                        if u.startswith('//'): u = 'https:' + u
                        raw_urls.append(u)
                    
                    # Filtro domini supportati (Mixdrop/Supervideo)
                    supported_domains = ['mixdrop', 'supervideo']
                    embed_urls = []
                    for u in raw_urls:
                        if not u or not u.startswith('http'): continue
                        if 'mostraguarda' in u: continue # Evita self-reference
                        
                        # Verifica se contiene uno dei domini supportati
                        if any(d in u for d in supported_domains):
                            if u not in embed_urls:
                                embed_urls.append(u)
                    
                    # Salvataggio Cache
                    if embed_urls:
                        cache[clean_id] = {
                            "timestamp": now_ms,
                            "embedUrls": embed_urls,
                            "title": real_title
                        }
                        self._write_cache(cache)
                        logger.info(f"[GH] Trovati {len(embed_urls)} embed.")
                    else:
                        logger.warning(f"[GH] Nessun embed valido trovato per {clean_id}")
                else:
                    logger.warning(f"[GH] Errore HTTP {res.status_code} su {target_url}")

            except Exception as e:
                logger.error(f"[GH] Errore Scraping: {e}")

        # --- RISOLUZIONE STREAM ---
        # Il JS usa estrattori specifici, qui usiamo i resolver Python equivalenti
        # ma formattiamo l'output come nel JS ("🦁 GuardaHD...")
        
        logger.info(f"[GH] Risoluzione di {len(embed_urls)} url...")
        
        unique_streams = set()

        for link in embed_urls:
            try:
                resolver = None
                host_name = ""
                
                if 'mixdrop' in link:
                    resolver = resolve_mixdrop
                    host_name = "MixDrop"
                elif 'supervideo' in link:
                    resolver = resolve_supervideo
                    host_name = "SuperVideo"
                
                if resolver:
                    # Risoluzione
                    direct_url = await resolver(link, client)
                    
                    if direct_url and direct_url not in unique_streams:
                        unique_streams.add(direct_url)
                        
                        # Generazione Titolo "Rich" stile JS
                        rich_title = self._generate_rich_description(real_title, "HD")
                        
                        streams.append({
                            "name": f"🦁 GuardaHD\n⚡ {host_name}",
                            "title": rich_title,
                            "url": direct_url,
                            "behaviorHints": {
                                "bingeGroup": "guardahd",
                                "notWebReady": True,
                                "proxyHeaders": {"request": {"User-Agent": request_headers['User-Agent']}}
                            }
                        })
            except Exception:
                pass

        return streams

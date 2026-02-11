import logging
import re
import urllib.parse
from bs4 import BeautifulSoup, SoupStrainer
from fake_headers import Headers
from app.utils import get_tmdb_info
from app.resolvers import resolve_supervideo, resolve_maxstream, resolve_mixdrop

GHD_DOMAIN = "https://guardahd.stream" # Assicurati che sia il dominio corrente
logger = logging.getLogger(__name__)

class GuardaHDProvider:
    def get_name(self):
        return "GuardaHD"

    async def get_stream(self, imdb_id: str, type: str, config: dict, client):
        streams = []
        tmdb_key = config.get("tmdb_key")
        
        # Parsing ID
        if ":" in imdb_id:
            clean_id, season_num, episode_num = imdb_id.split(":")
        else:
            clean_id = imdb_id
            season_num = None
            episode_num = None

        random_headers = Headers().generate()

        # LOGICA FILM (Usa ID diretto)
        if type == "movie":
            search_url = f"{GHD_DOMAIN}/set-movie-a/{clean_id}"
            await self._parse_page(search_url, client, streams, "Film")

        # LOGICA SERIE (Usa Ricerca Titolo)
        elif type == "series" and season_num and episode_num:
            # 1. Recupera titolo da TMDB
            info = await get_tmdb_info(clean_id, type, tmdb_key, client)
            if not info:
                return []
            
            title = info['title']
            logger.info(f"GuardaHD: Cerco serie '{title}'")
            
            # 2. Cerca su GuardaHD
            encoded_title = urllib.parse.quote(title)
            search_page_url = f"{GHD_DOMAIN}/?s={encoded_title}"
            
            try:
                res = await client.get(search_page_url, headers=random_headers)
                soup = BeautifulSoup(res.text, 'lxml')
                
                # Trova il link alla pagina della serie
                # (Questa parte dipende dalla struttura HTML dei risultati di ricerca di GuardaHD)
                # Solitamente sono dentro un div con classe 'result-item' o simile
                found_link = None
                for a in soup.select('div.title a, .box a'): 
                    # Controllo euristico semplice: se il titolo cercato è nel testo del link
                    if title.lower() in a.text.lower():
                        found_link = a['href']
                        break
                
                if found_link:
                    # 3. Naviga nella pagina della serie e trova l'episodio
                    # Url tipico: .../stagione-1-episodio-1 (varia molto, meglio scraping)
                    logger.info(f"Serie trovata: {found_link}")
                    episode_page_url = await self._find_episode_url(found_link, season_num, episode_num, client)
                    
                    if episode_page_url:
                        # 4. Estrai stream dalla pagina episodio
                        await self._parse_page(episode_page_url, client, streams, f"S{season_num}E{episode_num}")
                        
            except Exception as e:
                logger.error(f"Errore ricerca serie GuardaHD: {e}")

        return streams

    async def _find_episode_url(self, serie_url, season, episode, client):
        """
        Trova l'URL specifico dell'episodio nella pagina della serie.
        """
        try:
            res = await client.get(serie_url)
            soup = BeautifulSoup(res.text, 'lxml')
            
            # Cerca pattern tipo "1x01", "1x1", "Stagione 1 Episodio 1"
            # Molti temi wordpress usano liste di link
            target_texts = [
                f"{season}x{episode}",
                f"{season}x0{episode}" if int(episode) < 10 else f"{season}x{episode}",
                f"stagione {season} episodio {episode}"
            ]
            
            for a in soup.find_all('a'):
                link_text = a.text.lower().strip()
                for target in target_texts:
                    if target in link_text:
                        return a['href']
                        
        except Exception as e:
            logger.error(f"Errore parsing episodi: {e}")
        return None

    async def _parse_page(self, url, client, streams, label):
        """
        Estrae i link (Supervideo, etc) da una pagina finale (Film o Episodio).
        """
        try:
            res = await client.get(url)
            soup = BeautifulSoup(res.text, 'lxml')
            
            # Cerca i player (spesso in <li> data-link="...")
            li_tags = soup.find_all('li')
            
            for tag in li_tags:
                data_link = tag.get('data-link')
                if not data_link: continue
                
                host_url = 'https:' + data_link if data_link.startswith('//') else data_link
                
                resolver = None
                host_name = ""
                
                if 'supervideo' in host_url:
                    resolver = resolve_supervideo
                    host_name = "SuperVideo"
                elif 'mixdrop' in host_url:
                    resolver = resolve_mixdrop
                    host_name = "MixDrop"
                elif 'maxstream' in host_url:
                    resolver = resolve_maxstream
                    host_name = "MaxStream"
                
                if resolver:
                    try:
                        direct_url = await resolver(host_url, client)
                        if direct_url:
                            streams.append({
                                "name": "GuardaHD",
                                "title": f"{host_name} - {label}\nGuardaHD",
                                "url": direct_url,
                                "behaviorHints": {
                                    "bingeGroup": "guardahd",
                                    "proxyHeaders": {"request": {"Referer": "https://supervideo.tv/"}}
                                }
                            })
                    except Exception as e:
                        logger.warning(f"Errore resolver {host_name}: {e}")

        except Exception as e:
            logger.error(f"Errore parsing pagina player: {e}")

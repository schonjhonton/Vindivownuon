import re
import logging
from bs4 import BeautifulSoup, SoupStrainer
from fake_headers import Headers
from app.utils import get_tmdb_info

SC_DOMAIN = "https://vixsrc.to"
User_Agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
logger = logging.getLogger(__name__)

class VixProvider:
    def get_name(self):
        return "VixSrc"

    async def get_stream(self, imdb_id: str, type: str, config: dict, client):
        streams = []
        tmdb_key = config.get("tmdb_key")
        
        # Parsing ID Stremio
        if ":" in imdb_id:
            clean_id, season, episode = imdb_id.split(":")
        else:
            clean_id = imdb_id
            season = "1"
            episode = "1"

        # Ottieni info TMDB
        info = await get_tmdb_info(clean_id, type, tmdb_key, client)
        if not info:
            logger.warning(f"Vix: Impossibile trovare info TMDB per {clean_id}")
            return []
        
        tmdb_id = info['tmdb_id']

        # Costruzione URL Vix
        if type == "movie":
            site_url = f"{SC_DOMAIN}/movie/{tmdb_id}/"
        else:
            # URL Serie: /tv/ID/Stagione/Episodio
            site_url = f"{SC_DOMAIN}/tv/{tmdb_id}/{season}/{episode}/"

        logger.info(f"Vix Scraping: {site_url}")

        random_headers = Headers().generate()
        headers = {
            'Referer': f"{SC_DOMAIN}/",
            'Origin': f"{SC_DOMAIN}",
            'User-Agent': User_Agent,
        }
        headers.update(random_headers)

        try:
            response = await client.get(site_url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Vix Error: {response.status_code}")
                return []

            # Logica di estrazione (dal tuo vixcloud.py)
            soup = BeautifulSoup(response.text, "lxml", parse_only=SoupStrainer("body"))
            script_tag = soup.find("body").find("script")
            
            if not script_tag:
                return []
                
            script = script_tag.text
            
            # Regex
            token_match = re.search(r"'token':\s*'(\w+)'", script)
            expires_match = re.search(r"'expires':\s*'(\d+)'", script)
            server_url_match = re.search(r"url:\s*'([^']+)'", script)
            
            if not (token_match and expires_match and server_url_match):
                return []
            
            token = token_match.group(1)
            expires = expires_match.group(1)
            server_url = server_url_match.group(1)
            
            try:
                quality = re.search(r'"quality":(\d+)', script).group(1)
            except:
                quality = "HD"

            # Costruzione Link Finale
            separator = "&" if "?" in server_url else "?"
            final_url = f"{server_url}{separator}token={token}&expires={expires}"

            if "window.canPlayFHD = true" in script:
                final_url += "&h=1"

            # Adattamento per player (aggiunta .m3u8)
            parts = final_url.split("?")
            playable_url = parts[0] + ".m3u8?" + parts[1]

            streams.append({
                "name": "VixSrc",
                "title": f"VixCloud {quality}p\n{info['title']}",
                "url": playable_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "proxyHeaders": {"request": {"User-Agent": User_Agent}}
                }
            })

        except Exception as e:
            logger.error(f"Errore Vix: {e}")

        return streams

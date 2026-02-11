import logging
import re
from bs4 import BeautifulSoup, SoupStrainer
from fake_headers import Headers
from app.resolvers import resolve_supervideo, resolve_mixdrop, resolve_maxstream

# Config
GHD_DOMAIN = "https://guardahd.stream" # Verifica che sia il dominio attivo
logger = logging.getLogger(__name__)

class GuardaHDProvider:
    def get_name(self):
        return "GuardaHD"

    async def get_stream(self, imdb_id: str, type: str, config: dict, client):
        streams = []
        
        # GuardaHD usa ID IMDB (tt...) direttamente nell'URL per i film?
        # Dal tuo codice sembra usare: /set-movie-a/{clean_id}
        # "clean_id" di solito è l'ID IMDB.
        
        if ":" in imdb_id:
            # È una serie (tt:s:e) - GuardaHD gestisce serie? 
            # Il tuo script originale controllava "if ismovie == 0: return streams"
            # Quindi sembra supportare SOLO FILM per ora.
            logger.info("GuardaHD skip: Serie non ancora supportate nel codice originale")
            return []
        
        clean_id = imdb_id # es. tt1234567

        search_url = f"{GHD_DOMAIN}/set-movie-a/{clean_id}"
        logger.info(f"GuardaHD Searching: {search_url}")

        random_headers = Headers().generate()
        
        try:
            # 1. Cerca la pagina del film
            response = await client.get(search_url, allow_redirects=True, headers=random_headers)
            
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, 'lxml', parse_only=SoupStrainer('li'))
            li_tags = soup.find_all('li')
            
            host_url = None
            host_type = None

            # 2. Trova il link del player
            for tag in li_tags:
                data_link = tag.get('data-link', '')
                if not data_link:
                    continue
                
                # Priorità Supervideo (come da tuo script)
                if 'supervideo' in data_link:
                    host_url = 'https:' + data_link if data_link.startswith('//') else data_link
                    host_type = 'supervideo'
                    break
                # Backup Maxstream/Mixdrop (se volessi aggiungerli)
                elif 'maxstream' in data_link:
                    host_url = data_link
                    host_type = 'maxstream'
                    break

            if not host_url:
                logger.info("GuardaHD: Nessun host compatibile trovato")
                return []

            # 3. Risolvi il link usando i resolvers
            direct_url = None
            if host_type == 'supervideo':
                direct_url = await resolve_supervideo(host_url, client)
            elif host_type == 'maxstream':
                direct_url = await resolve_maxstream(host_url, client)

            if direct_url:
                streams.append({
                    "name": "GuardaHD",
                    "title": f"GuardaHD [{host_type}]\n{direct_url.split('.')[-1].upper()}",
                    "url": direct_url,
                    "behaviorHints": {
                        "bingeGroup": "guardahd",
                        # Supervideo a volte richiede referer
                        "proxyHeaders": {"request": {"Referer": "https://supervideo.tv/"}}
                    }
                })

        except Exception as e:
            logger.error(f"Errore GuardaHD: {e}")

        return streams

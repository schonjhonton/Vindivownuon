import base64
import json
import logging
import re
from curl_cffi.requests import AsyncSession

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def decode_config(config_str: str) -> dict:
    """Decodifica la configurazione base64 dall'URL"""
    try:
        if not config_str:
            return {}
        decoded_bytes = base64.b64decode(config_str)
        return json.loads(decoded_bytes.decode('utf-8'))
    except Exception as e:
        logger.error(f"Errore decodifica config: {e}")
        return {}

async def get_tmdb_info(imdb_id: str, type: str, tmdb_key: str, client: AsyncSession):
    """
    Restituisce ID TMDB e Titolo.
    Return: {'tmdb_id': '123', 'title': 'Breaking Bad', 'year': '2008'}
    """
    if not tmdb_key:
        return None

    clean_id = imdb_id.split(":")[0] # Rimuove season/episode se presenti

    try:
        # 1. Trova ID TMDB da IMDB ID
        url = f"https://api.themoviedb.org/3/find/{clean_id}"
        params = {"api_key": tmdb_key, "external_source": "imdb_id"}
        
        resp = await client.get(url, params=params)
        data = resp.json()
        
        result = None
        if type == "movie" and data.get("movie_results"):
            res = data["movie_results"][0]
            result = {
                "tmdb_id": str(res["id"]),
                "title": res["title"],
                "year": res.get("release_date", "")[:4]
            }
        elif type == "series" and data.get("tv_results"):
            res = data["tv_results"][0]
            result = {
                "tmdb_id": str(res["id"]),
                "title": res["name"], # Le serie usano 'name'
                "year": res.get("first_air_date", "")[:4]
            }
            
        return result
            
    except Exception as e:
        logger.error(f"Errore TMDB conversion: {e}")
    
    return None

def unpack_js(packed_js):
    """
    Decodifica Javascript 'packed' (Dean Edwards Packer) usato da Supervideo/Mixdrop.
    """
    try:
        def baseN(num, b, numerals="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            return ((num == 0) and numerals[0]) or (baseN(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])

        payload = re.search(r"return p}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", packed_js)
        if not payload:
            return None
            
        p, a, c, k = payload.groups()
        a = int(a)
        c = int(c)
        k = k.split('|')
        
        decoded = p
        for i in range(c - 1, -1, -1):
            key = baseN(i, a)
            val = k[i] if k[i] else key
            # Simple replacement logic
            pattern = r'\b' + re.escape(key) + r'\b'
            try:
                decoded = re.sub(pattern, val, decoded)
            except:
                pass
        return decoded
    except Exception as e:
        logger.error(f"Error unpacking JS: {e}")
        return None

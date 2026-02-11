import re
import logging
from app.utils import unpack_js

logger = logging.getLogger(__name__)

async def resolve_supervideo(url: str, client):
    """Risolve link Supervideo"""
    try:
        response = await client.get(url, allow_redirects=True)
        # Cerca packed JS
        packed = re.search(r"(eval\(function\(p,a,c,k,e,d\).*?\.split\('\|'\)\)\))", response.text)
        
        decoded_html = response.text
        if packed:
            unpacked = unpack_js(packed.group(1))
            if unpacked:
                decoded_html = unpacked
        
        # Cerca il file m3u8 o mp4
        # Pattern tipici di supervideo
        match = re.search(r'file:\s*"([^"]+)"', decoded_html)
        if match:
            return match.group(1)
            
        match_src = re.search(r"src:\s*'([^']+)'", decoded_html)
        if match_src:
            return match_src.group(1)

    except Exception as e:
        logger.error(f"Supervideo error: {e}")
    return None

async def resolve_maxstream(url: str, client):
    """Risolve link Maxstream"""
    try:
        response = await client.get(url, allow_redirects=True)
        # Regex dal tuo file originale
        pattern = r'sources\W+src\W+(.*)",'
        match = re.search(pattern, response.text)
        if match:
            return match.group(1).replace('"', '').strip()
    except Exception as e:
        logger.error(f"Maxstream error: {e}")
    return None

async def resolve_mixdrop(url: str, client):
    """Risolve link Mixdrop"""
    try:
        # Fix URL come dal tuo script
        if "club" in url: url = url.replace("club", "cv").split("/2")[0]
        if "cfd" in url: url = url.replace("cfd", "cv").replace("emb","e").split("/2")[0]
        
        response = await client.get(url)
        
        # Mixdrop usa quasi sempre packed JS
        packed = re.search(r"(eval\(function\(p,a,c,k,e,d\).*?\.split\('\|'\)\)\))", response.text)
        if packed:
            unpacked = unpack_js(packed.group(1))
            if unpacked:
                # Cerca wurl (spesso mixdrop lo chiama wurl o url)
                match = re.search(r'wurl="([^"]+)"', unpacked)
                if match:
                    final_url = "https:" + match.group(1) if match.group(1).startswith("//") else match.group(1)
                    return final_url
    except Exception as e:
        logger.error(f"Mixdrop error: {e}")
    return None

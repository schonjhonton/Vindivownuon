
import re
import logging
from app.utils import unpack_js

logger = logging.getLogger(__name__)

async def resolve_supervideo(url: str, client):
    try:
        response = await client.get(url, allow_redirects=True)
        html = response.text
        
        # Check Packed JS
        packed = re.search(r"(eval\(function\(p,a,c,k,e,d\).*?\.split\('\|'\)\)\))", html)
        if packed:
            unpacked = unpack_js(packed.group(1))
            if unpacked:
                html = unpacked
        
        # Cerca file m3u8/mp4
        match = re.search(r'file:\s*"([^"]+)"', html) or re.search(r"src:\s*'([^']+)'", html)
        if match:
            return match.group(1)
            
    except Exception as e:
        logger.error(f"SV Error: {e}")
    return None

async def resolve_maxstream(url: str, client):
    try:
        response = await client.get(url)
        match = re.search(r'sources\W+src\W+(.*)",', response.text)
        if match:
            return match.group(1).replace('"', '').strip()
    except:
        pass
    return None

async def resolve_mixdrop(url: str, client):
    try:
        if "club" in url: url = url.replace("club", "cv").split("/2")[0]
        response = await client.get(url)
        packed = re.search(r"(eval\(function\(p,a,c,k,e,d\).*?\.split\('\|'\)\)\))", response.text)
        if packed:
            unpacked = unpack_js(packed.group(1))
            if unpacked:
                match = re.search(r'wurl="([^"]+)"', unpacked)
                if match:
                    return "https:" + match.group(1) if match.group(1).startswith("//") else match.group(1)
    except:
        pass
    return None

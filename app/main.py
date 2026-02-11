import asyncio
import logging
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi.requests import AsyncSession

# Import interni
from app.manifest import MANIFEST
from app.extractors import PROVIDERS
from app.utils import decode_config

# Configurazione Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ITA-Addon")

# Inizializzazione App
app = FastAPI(title="ITA Streaming Addon", version="1.0.0")

# Setup Templates (per la pagina configure.html)
templates = Jinja2Templates(directory="templates")

# --- CONFIGURAZIONE CORS ---
# Fondamentale per far funzionare l'addon su Stremio Web e Desktop
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permetti a tutte le origini
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Pagina principale: Mostra il form di configurazione.
    """
    return templates.TemplateResponse("configure.html", {"request": request})

@app.get("/manifest.json")
async def get_base_manifest():
    """
    Manifest base (senza configurazione).
    Utile per check di installazione, ma redirige l'utente a configurare.
    """
    return MANIFEST

@app.get("/{config}/manifest.json")
async def get_configured_manifest(config: str):
    """
    Manifest configurato.
    Stremio chiama questo quando l'utente installa l'addon col link generato.
    """
    # Possiamo opzionalmente modificare il manifest in base alla config (es. aggiungere info all'utente)
    return MANIFEST

@app.get("/{config}/stream/{type}/{id}.json")
async def get_streams(config: str, type: str, id: str):
    """
    CORE LOGIC:
    1. Decodifica la configurazione (TMDB Key, MFP).
    2. Crea un browser virtuale (AsyncSession).
    3. Lancia tutti gli scraper in parallelo.
    4. Raccoglie e restituisce i risultati.
    """
    # 1. Decodifica Config
    user_config = decode_config(config)
    tmdb_key = user_config.get('tmdb_key')
    
    if not tmdb_key:
        logger.error("Richiesta ricevuta senza TMDB Key valida.")
        return {"streams": []} # Ritorna vuoto se manca la chiave

    logger.info(f"Richiesta Stream: [{type}] ID: {id}")

    streams = []

    # 2. Setup Sessione Browser (Impersonate Chrome)
    # Usiamo 'chrome110' per simulare un browser reale e bypassare Cloudflare/Controlli
    async with AsyncSession(impersonate="chrome110", verify=False) as client:
        
        # 3. Preparazione Task Paralleli
        tasks = []
        for provider in PROVIDERS:
            # Creiamo un task asincrono per ogni provider
            tasks.append(
                process_provider(provider, id, type, user_config, client)
            )

        # 4. Esecuzione Parallela
        # return_exceptions=True impedisce che un errore in un provider blocchi tutto
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 5. Raccolta Risultati
        for res in results:
            if isinstance(res, list):
                streams.extend(res)
            elif isinstance(res, Exception):
                logger.error(f"Eccezione non gestita in un provider: {res}")

    # Ordina i risultati (Opzionale: es. prima 1080p)
    # streams.sort(key=lambda x: x.get('title', ''), reverse=True)

    logger.info(f"Totale stream trovati: {len(streams)}")
    
    # Header Cache-Control per evitare richieste doppie immediate da Stremio
    return JSONResponse(
        content={"streams": streams},
        headers={"Cache-Control": "max-age=3600, public"} # Cache di 1 ora
    )

async def process_provider(provider, id, type, config, client):
    """
    Wrapper per gestire errori singoli dei provider senza crashare l'app.
    """
    try:
        provider_name = provider.get_name()
        # logger.debug(f"Avvio provider: {provider_name}")
        
        provider_streams = await provider.get_stream(id, type, config, client)
        
        if provider_streams:
            logger.info(f"✅ {provider_name}: {len(provider_streams)} stream trovati.")
            return provider_streams
        else:
            # logger.debug(f"❌ {provider_name}: Nessun stream.")
            return []
            
    except Exception as e:
        logger.error(f"⚠️ Errore critico in {provider.get_name()}: {e}")
        return []

# Blocco per avvio locale (senza Docker) per debug rapido
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=7000, reload=True)

from contextlib import asynccontextmanager
import logging
import time
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from api.ingestion import router as ingestion_router, recover_pending, _worker
from api.intel import router as intel_router
from api.upload import router as upload_router
from core.scheduler import start_scheduler, scheduler, collector_status
from core.config import settings
from database.database import engine, qdrant, ensure_vector_collection
from database.migrate import upgrade_database

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(upgrade_database)
    try:
        await run_in_threadpool(ensure_vector_collection)
    except Exception:
        log.exception('Vector store unavailable; report indexing will show its actual state.')
    await run_in_threadpool(recover_pending, True)
    start_scheduler()
    yield
    scheduler.shutdown(wait=False)
    await run_in_threadpool(_worker.shutdown, True)

app = FastAPI(title='OpenThreat Platform', version='1.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS.split(','),
                   allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['*'])
app.include_router(ingestion_router, prefix='/api/v1')
app.include_router(intel_router, prefix='/api/v1')
app.include_router(upload_router, prefix='/api/v1')

_status_cache = None
_status_time = 0

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'platform-service'}

@app.get('/api/v1/system/status')
def system_status():
    global _status_cache, _status_time
    if _status_cache is not None and time.monotonic() - _status_time < 10:
        return _status_cache
    result = {'platform': 'online', 'nlp': {'status': 'offline', 'ready': False},
              'database': 'offline', 'qdrant': 'offline', 'collectors': dict(collector_status),
              'ingest_interval_seconds': settings.INGEST_INTERVAL_SECONDS, 'auto_ingest': settings.AUTO_INGEST}
    try:
        with httpx.Client(timeout=3) as client:
            response = client.get(f'{settings.NLP_SERVICE_URL}/health')
            response.raise_for_status()
            result['nlp'] = response.json()
    except Exception:
        pass
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        result['database'] = 'online'
    except Exception:
        pass
    try:
        qdrant.get_collections()
        result['qdrant'] = 'online'
    except Exception:
        pass
    _status_cache, _status_time = result, time.monotonic()
    return result

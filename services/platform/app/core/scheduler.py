"""Collect off the API thread; extraction uses its own document worker."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from datetime import datetime, timezone
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from collectors.nvd_collector import NVDCollector
from collectors.cisa_collector import CISACollector
from collectors.rss_collector import RSSCollector
from database.database import SessionLocal
from database.models import Document
from api.ingestion import submit_document, recover_pending
from core.config import settings

scheduler = BackgroundScheduler(timezone='UTC')
log = logging.getLogger(__name__)
_collection_lock = Lock()
collector_status = {}


def fetch_and_ingest_job():
    if not _collection_lock.acquire(blocking=False):
        return
    try:
        with SessionLocal() as db:
            known = {row[0] for row in db.query(Document.external_id).filter(Document.external_id.isnot(None)).all()}
        def fetch(collector):
            name = collector.__class__.__name__
            try:
                docs = collector.fetch_new_documents(limit=5, known_ids=known)
                collector_status[name] = {'status': 'error' if collector.last_error else 'ok',
                    'checked_at': datetime.now(timezone.utc).isoformat(), 'fetched': len(docs),
                    'error': collector.last_error}
                return docs
            except Exception:
                log.exception('Collector failed: %s', name)
                collector_status[name] = {'status': 'error', 'checked_at': datetime.now(timezone.utc).isoformat(),
                                          'error': 'Collection failed; check service logs.'}
                return []
        with ThreadPoolExecutor(max_workers=3) as pool:
            batches = list(pool.map(fetch, [NVDCollector(), CISACollector(), RSSCollector()]))
        for batch in batches:
            for item in batch:
                try:
                    with SessionLocal() as db:
                        submit_document(db, item['title'], item['content'], item['source_name'], item['source_type'],
                            item['source_url'], item.get('published_at'), item['external_id'])
                except Exception:
                    log.exception('Could not store collected report')
    finally:
        _collection_lock.release()


def start_scheduler():
    if settings.AUTO_INGEST:
        scheduler.add_job(fetch_and_ingest_job, 'interval', seconds=settings.INGEST_INTERVAL_SECONDS,
            id='ingest_cron', max_instances=1, coalesce=True, replace_existing=True)
    scheduler.add_job(recover_pending, 'interval', seconds=30, id='recover_pending', max_instances=1)
    scheduler.start()

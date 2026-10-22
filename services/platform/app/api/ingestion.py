"""Durable document states with a single bounded local extraction worker."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import hashlib
import logging
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from database.database import get_db, SessionLocal, qdrant, COLLECTION_NAME
from database.models import Document
from crud import crud
from core.config import settings
from core.dates import iso_date, parse_date
from novelty.engine import NoveltyEngine

router = APIRouter()
log = logging.getLogger(__name__)
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='intelligence')
_queue_lock = Lock()
_queued = set()


def process_document_pipeline(doc_id, *_unused):
    with SessionLocal() as db:
        doc = db.get(Document, uuid.UUID(str(doc_id)))
        if not doc or doc.processing_status not in ('PENDING', 'PROCESSING'):
            return
        content_hash = doc.content_hash
        doc.processing_status = 'PROCESSING'
        doc.processing_error = None
        db.commit()
        try:
            request = {'document_id': str(doc.id), 'text': doc.content, 'source_name': doc.source.name,
                       'source_url': doc.url, 'published_at': iso_date(doc.published_at)}
            with httpx.Client(timeout=settings.NLP_TIMEOUT_SECONDS) as client:
                response = client.post(f'{settings.NLP_SERVICE_URL}/analyze', json=request)
                response.raise_for_status()
                payload = response.json()
            db.refresh(doc)
            if doc.content_hash != content_hash:
                doc.processing_status = 'PENDING'
                db.commit()
                return
            db.info['defer_commit'] = True
            NoveltyEngine(db).process_nlp_payload(doc.id, payload, request['published_at'])
            doc.processing_metadata = payload.get('processing')
            doc.processing_status = 'COMPLETED'
            doc.embedding_status = 'PENDING'
            db.commit()
            db.info['defer_commit'] = False
            try:
                from qdrant_client.models import PointStruct
                qdrant.upsert(collection_name=COLLECTION_NAME, points=[PointStruct(id=str(doc.id),
                    vector=payload['document_embedding'], payload={'title': doc.title, 'source_name': doc.source.name,
                    'url': doc.url, 'published_at': request['published_at']})])
                doc.embedding_status = 'SYNCED'
            except Exception:
                log.exception('Vector indexing failed for document %s', doc.id)
                doc.embedding_status = 'FAILED'
            db.commit()
        except Exception as exc:
            db.rollback()
            db.info['defer_commit'] = False
            log.exception('Document processing failed: %s', doc_id)
            doc = db.get(Document, uuid.UUID(str(doc_id)))
            doc.processing_status = 'FAILED'
            doc.processing_error = f'{type(exc).__name__}: processing failed; retry when services are available.'
            db.commit()


def queue_document(doc_id):
    key = str(doc_id)
    with _queue_lock:
        if key in _queued:
            return False
        if len(_queued) >= 200:
            return False  # remains PENDING in Postgres; the recovery job submits it later
        _queued.add(key)
    def run():
        try:
            process_document_pipeline(key)
        finally:
            with _queue_lock:
                _queued.discard(key)
            with SessionLocal() as db:
                doc = db.get(Document, uuid.UUID(key))
                if doc and doc.processing_status == 'PENDING':
                    queue_document(key)
    _worker.submit(run)
    return True


def recover_pending(reset_processing=False):
    with SessionLocal() as db:
        if reset_processing:
            db.query(Document).filter(Document.processing_status == 'PROCESSING').update({'processing_status': 'PENDING'})
            db.commit()
        for doc in db.query(Document).filter(Document.processing_status == 'PENDING').order_by(Document.first_seen_at).limit(200):
            queue_document(doc.id)


def submit_document(db, title, content, source_name, source_type='manual', url=None, published_at=None, external_id=None):
    if not content.strip():
        raise HTTPException(422, 'The report contains no readable text.')
    if len(content) > 500_000:
        raise HTTPException(413, 'Reports must contain fewer than 500,000 characters.')
    source = crud.get_or_create_source(db, source_name, source_type, url)
    digest = hashlib.sha256(content.encode()).hexdigest()
    doc = crud.create_document(db, source.id, title, content, digest, url=url,
        external_id=external_id or f'manual_{digest}', published_at=published_at)
    if doc.processing_status == 'PENDING':
        queue_document(doc.id)
    return doc


class ManualUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=500_000)
    source_name: str = Field(default='Manual Upload', min_length=1, max_length=200)
    url: str | None = None
    published_at: str | None = None

    @field_validator('published_at')
    @classmethod
    def valid_date(cls, value):
        if value and not parse_date(value):
            raise ValueError('Provide a valid publication date.')
        return iso_date(value)

    @field_validator('title', 'source_name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('This field cannot be blank.')
        return value.strip()

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        if value and not value.startswith(('https://', 'http://')):
            raise ValueError('Source links must use http or https.')
        return value


@router.post('/upload', status_code=202)
def upload_document(req: ManualUploadRequest, db: Session = Depends(get_db)):
    doc = submit_document(db, req.title, req.content, req.source_name, url=req.url, published_at=req.published_at)
    return {'status': doc.processing_status, 'document_id': str(doc.id)}


@router.post('/documents/{doc_id}/retry', status_code=202)
def retry_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, 'Document not found.')
    if doc.processing_status not in ('FAILED', 'COMPLETED'):
        raise HTTPException(409, 'Document is already queued or processing.')
    if doc.processing_status == 'COMPLETED' and doc.embedding_status != 'FAILED':
        raise HTTPException(409, 'Document is already processed and indexed.')
    doc.processing_status = 'PENDING'
    doc.processing_error = None
    db.commit()
    queue_document(doc.id)
    return {'status': 'PENDING', 'document_id': str(doc.id)}


@router.post('/trigger-ingestion', status_code=202)
def trigger_ingestion():
    from core.scheduler import scheduler, fetch_and_ingest_job
    from datetime import datetime, timezone
    if scheduler.get_job('manual_ingestion'):
        raise HTTPException(409, 'A collection request is already queued.')
    scheduler.add_job(fetch_and_ingest_job, 'date', run_date=datetime.now(timezone.utc), id='manual_ingestion')
    return {'status': 'queued', 'message': 'Collection requested. New reports will appear in the document library.'}

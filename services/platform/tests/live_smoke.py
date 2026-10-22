"""Opt-in integration check: real NLP service, disposable SQLite, no project DB writes."""
import sys, uuid, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database.models import Base, Source, Document, Entity, Relation, Evidence
from novelty.engine import NoveltyEngine
from core.config import settings

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
with Session(engine) as db, httpx.Client(timeout=180) as client:
    health = client.get(settings.NLP_SERVICE_URL + "/health").json()
    assert health["ready"], health
    source = Source(name="Disposable integration test", source_type="test")
    db.add(source); db.flush()
    doc = Document(source_id=source.id, title="Disposable test", content="APT28 used Mimikatz to dump credentials and exploited CVE-2023-23397.", content_hash="test")
    db.add(doc); db.commit()
    started = time.perf_counter()
    response = client.post(settings.NLP_SERVICE_URL + "/analyze", json={"document_id":str(doc.id),"source_name":source.name,"text":doc.content,"published_at":"2024-03-01T00:00:00Z"})
    response.raise_for_status(); payload = response.json()
    assert payload["entities"] and payload["relations"], payload
    db.info["defer_commit"] = True
    result = NoveltyEngine(db).process_nlp_payload(doc.id,payload,"2024-03-01T00:00:00Z")
    db.commit()
    assert db.query(Entity).count() > 0 and db.query(Relation).count() > 0
    assert db.query(Evidence).count() > 0
    print(json.dumps({"real_nlp_seconds":round(time.perf_counter()-started,2),"metadata":payload.get("processing_metadata",payload.get("metadata")),"entities":db.query(Entity).count(),"relations":db.query(Relation).count(),"result":result},default=str))
    repeated = NoveltyEngine(db).process_nlp_payload(doc.id,payload,"2024-03-01T00:00:00Z")
    assert repeated["relations"]["KNOWN"] > 0, repeated
    print("Real extraction, novelty and persistence smoke check passed; disposable database only.")
    db.rollback()

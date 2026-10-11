import uuid
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional, Dict, Any
import datetime
from core.dates import parse_date

def persist(db):
    # Extraction runs as one transaction; API document submissions commit immediately.
    if db.info.get('defer_commit'):
        db.flush()
    else:
        db.commit()
from database.models import Source, Document, DocumentVersion, Entity, EntityAlias, Relation, Behavior, IntelligenceChange, Evidence

# --- SOURCE ---
def get_or_create_source(db: Session, name: str, source_type: str, url: str = None) -> Source:
    source = db.query(Source).filter(Source.name == name).first()
    if not source:
        source = Source(name=name, source_type=source_type, url=url, reliability=0.8)
        db.add(source)
        persist(db)
        db.refresh(source)
    return source

# --- DOCUMENT & VERSIONS ---
def create_document(db: Session, source_id: uuid.UUID, title: str, content: str, content_hash: str, raw_content_path: str = "db", url: str = None, external_id: str = None, published_at: str = None) -> Document:
    # Check if exists by external_id
    doc = None
    if external_id:
        doc = db.query(Document).filter(Document.external_id == external_id).first()

    if doc:
        # Check for version change
        if doc.content_hash != content_hash:
            # Hash changed, create a new version
            version = DocumentVersion(
                document_id=doc.id,
                version_hash=doc.content_hash, # Save old hash
                raw_content_path=raw_content_path,
                processed_at=doc.first_seen_at
                , content=doc.content
            )
            db.add(version)

            # Update current doc
            doc.content_hash = content_hash
            doc.content = content
            doc.title = title
            doc.url = url
            doc.published_at = parse_date(published_at)
            doc.processing_error = None
            doc.embedding_status = 'PENDING'
            doc.processing_status = "PENDING" # Needs re-processing
            persist(db)
            db.refresh(doc)
    else:
        # Create new document
        doc = Document(
            source_id=source_id,
            title=title,
            content=content,
            content_hash=content_hash,
            url=url,
            external_id=external_id,
            published_at=parse_date(published_at),
            processing_status="PENDING"
        )
        db.add(doc)
        persist(db)
        db.refresh(doc)

    return doc

def update_document_status(db: Session, doc_id: uuid.UUID, status: str):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc:
        doc.processing_status = status
        persist(db)
        db.refresh(doc)
    return doc

# --- ENTITY ---
def get_entity_by_name(db: Session, name: str, entity_type: str = None) -> Optional[Entity]:
    query = db.query(Entity).filter(Entity.canonical_name == name)
    if entity_type:
        query = query.filter(Entity.type == entity_type)
    entity = query.first()
    if not entity:
        alias = db.query(EntityAlias).filter(EntityAlias.alias == name).first()
        if alias:
            entity = alias.entity
            if entity_type and entity.type != entity_type:
                entity = None
    return entity

def create_entity(db: Session, canonical_name: str, entity_type: str, confidence: float) -> Entity:
    entity = Entity(canonical_name=canonical_name, type=entity_type, confidence=confidence)
    db.add(entity)
    persist(db)
    db.refresh(entity)
    return entity

# --- RELATION ---
def get_relation(db: Session, subject_id: uuid.UUID, relation_type: str, object_id: uuid.UUID) -> Optional[Relation]:
    return db.query(Relation).filter(
        and_(
            Relation.subject_id == subject_id,
            Relation.relation_type == relation_type,
            Relation.object_id == object_id,
            Relation.status == "ACTIVE"
        )
    ).first()

def get_relations_by_subject(db: Session, subject_id: uuid.UUID, relation_type: str) -> List[Relation]:
    return db.query(Relation).filter(
        and_(
            Relation.subject_id == subject_id,
            Relation.relation_type == relation_type
        )
    ).all()

def create_relation(db: Session, subject_id: uuid.UUID, relation_type: str, object_id: uuid.UUID, confidence: float) -> Relation:
    relation = Relation(
        subject_id=subject_id,
        relation_type=relation_type,
        object_id=object_id,
        confidence=confidence
    )
    db.add(relation)
    persist(db)
    db.refresh(relation)
    return relation

def update_relation_timestamp(db: Session, relation_id: uuid.UUID):
    relation = db.query(Relation).filter(Relation.id == relation_id).first()
    if relation:
        relation.last_seen_at = datetime.datetime.utcnow()
        persist(db)

def mark_relation_historical(db: Session, relation_id: str):
    relation = db.query(Relation).filter(Relation.id == relation_id).first()
    if relation:
        relation.status = "HISTORICAL"
        persist(db)

# --- EVIDENCE ---
def create_evidence(db: Session, document_id: str, relation_id: str, behavior_id: str, snippet: str, evidence: dict = None):
    if db.query(Evidence).filter_by(document_id=document_id, relation_id=relation_id, behavior_id=behavior_id, snippet=snippet).first():
        return
    details = evidence or {}
    evidence = Evidence(
        document_id=document_id,
        relation_id=relation_id,
        behavior_id=behavior_id,
        snippet=snippet
        , char_start=details.get('char_start'), char_end=details.get('char_end'), page_number=details.get('page_number')
    )
    db.add(evidence)
    persist(db)

# --- BEHAVIOR ---
def create_behavior(db: Session, document_id: uuid.UUID, entity_id: uuid.UUID, description: str, mitre_attack_id: str, confidence: float) -> Behavior:
    behavior = Behavior(
        document_id=document_id,
        entity_id=entity_id,
        description=description,
        mitre_attack_id=mitre_attack_id,
        confidence=confidence
    )
    db.add(behavior)
    persist(db)
    db.refresh(behavior)
    return behavior

# --- INTELLIGENCE CHANGE (NOVELTY) ---
def log_intelligence_change(db: Session, entity_type: str, entity_id: uuid.UUID, change_type: str, document_id=None, reason=None):
    if document_id and db.query(IntelligenceChange).filter_by(entity_type=entity_type, entity_id=entity_id, change_type=change_type, document_id=document_id).first():
        return
    change = IntelligenceChange(
        entity_type=entity_type,
        entity_id=entity_id,
        change_type=change_type
        , document_id=document_id, reason=reason
    )
    db.add(change)
    persist(db)

def get_recent_intelligence_changes(db: Session, limit: int = 50):
    return db.query(IntelligenceChange).order_by(IntelligenceChange.timestamp.desc()).limit(limit).all()


def get_document(db, document_id):
    from database.models import Document
    return db.query(Document).filter(Document.id == document_id).first()

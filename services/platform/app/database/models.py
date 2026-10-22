import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Source(Base):
    __tablename__ = 'sources'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    url = Column(String, nullable=True)
    reliability = Column(Float, nullable=True)
    
    documents = relationship("Document", back_populates="source")

class Document(Base):
    __tablename__ = 'documents'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey('sources.id'), nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, nullable=True)
    content_hash = Column(String, nullable=False)
    url = Column(String, nullable=True)
    external_id = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    processing_status = Column(String, default="PENDING")
    processing_error = Column(Text, nullable=True)
    embedding_status = Column(String, default="PENDING")
    processing_metadata = Column(JSON, nullable=True)
    
    source = relationship("Source", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document")
    behaviors = relationship("Behavior", back_populates="document")

class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    version_hash = Column(String, nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow)
    raw_content_path = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    
    document = relationship("Document", back_populates="versions")

class Entity(Base):
    __tablename__ = 'entities'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    
    aliases = relationship("EntityAlias", back_populates="entity")

class EntityAlias(Base):
    __tablename__ = 'entity_aliases'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id'), nullable=False)
    alias = Column(String, nullable=False)
    
    entity = relationship("Entity", back_populates="aliases")

class Relation(Base):
    __tablename__ = 'relations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey('entities.id'), nullable=False)
    relation_type = Column(String, nullable=False)
    object_id = Column(UUID(as_uuid=True), ForeignKey('entities.id'), nullable=False)
    confidence = Column(Float, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="ACTIVE")
    negated = Column(Boolean, nullable=False, default=False)
    source_first_seen_at = Column(DateTime, nullable=True)
    source_last_seen_at = Column(DateTime, nullable=True)
    review_required = Column(Boolean, nullable=False, default=False)

class Behavior(Base):
    __tablename__ = 'behaviors'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id'), nullable=True)
    description = Column(String, nullable=False)
    mitre_attack_id = Column(String, nullable=True)
    confidence = Column(Float, nullable=False)
    
    document = relationship("Document", back_populates="behaviors")

class Evidence(Base):
    __tablename__ = 'evidence'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    relation_id = Column(UUID(as_uuid=True), ForeignKey('relations.id'), nullable=True)
    behavior_id = Column(UUID(as_uuid=True), ForeignKey('behaviors.id'), nullable=True)
    snippet = Column(Text, nullable=False)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    page_number = Column(Integer, nullable=True)

class IntelligenceChange(Base):
    __tablename__ = 'intelligence_changes'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False) # Relation, Entity, Behavior
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    change_type = Column(String, nullable=False) # NEW, KNOWN, UPDATED, CONFLICTING, UNCERTAIN
    timestamp = Column(DateTime, default=datetime.utcnow)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=True)
    reason = Column(Text, nullable=True)

class TemporalEvent(Base):
    __tablename__ = 'temporal_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey('entities.id'), nullable=False)
    event = Column(Text, nullable=False)
    time = Column(String, nullable=False)
    type = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    evidence = Column(JSON, nullable=True)

Index('ix_documents_external_id', Document.external_id)
Index('ix_documents_status', Document.processing_status)
Index('ix_entities_name_type', Entity.canonical_name, Entity.type)
Index('ix_aliases_alias', EntityAlias.alias)
Index('ix_relations_subject_type', Relation.subject_id, Relation.relation_type)
Index('ix_relations_object', Relation.object_id)
Index('ix_evidence_relation', Evidence.relation_id)
Index('ix_evidence_behavior', Evidence.behavior_id)
Index('ix_changes_timestamp', IntelligenceChange.timestamp)
Index('ix_behaviors_entity', Behavior.entity_id)
Index('ix_temporal_entity', TemporalEvent.entity_id)

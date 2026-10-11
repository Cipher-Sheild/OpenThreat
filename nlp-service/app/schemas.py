"""Pydantic models mirroring docs/contracts/*.json (v1.1). They drive validation and /docs."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

EntityType = Literal["THREAT_ACTOR", "MALWARE", "TOOL", "VULNERABILITY", "TECHNIQUE", "ORGANIZATION", "OBSERVABLE"]
RelationType = Literal["USES", "DEPLOYS", "EXPLOITS", "TARGETS", "ATTRIBUTED_TO"]
NoveltyStatus = Literal["NEW", "KNOWN", "UPDATED", "CONFLICTING", "UNCERTAIN"]


# ---------- /analyze ----------
class Page(BaseModel):
    page_number: int = Field(ge=1)
    text: str


class AnalyzeRequest(BaseModel):
    document_id: str
    text: Optional[str] = None
    pages: Optional[list[Page]] = None
    source_name: str
    source_url: Optional[str] = None
    published_at: Optional[str] = Field(None, description="ISO 8601 date-time the source published the document")

    @model_validator(mode="after")
    def _text_or_pages(self):
        if not self.pages and self.text is None:
            raise ValueError("send either 'text' or 'pages'")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "document_id": "3f1c2a9e-0000-4000-8000-000000000001",
                "text": "APT28 used Mimikatz to dump credentials and exploited CVE-2023-23397.",
                "source_name": "CISA",
                "source_url": "https://www.cisa.gov/example",
                "published_at": "2024-03-01T00:00:00Z",
            }]
        }
    }


class Evidence(BaseModel):
    text: str
    char_start: int
    char_end: int
    page_number: Optional[int]


class EntityOut(BaseModel):
    mention: str
    canonical_name: str
    type: EntityType
    subtype: Optional[str] = None
    confidence: float
    char_start: int
    char_end: int
    page_number: Optional[int]


class RelationOut(BaseModel):
    subject: str
    subject_type: EntityType
    relation: RelationType
    object: str
    object_type: EntityType
    negated: bool
    confidence: float
    evidence: Evidence


class BehaviorOut(BaseModel):
    description: str
    mitre_attack_id: Optional[str]
    mitre_attack_name: Optional[str] = None
    confidence: float
    evidence: Evidence


class TemporalOut(BaseModel):
    event: str
    entity: str
    time: str
    type: Literal["FIRST_SEEN", "DISCLOSED", "PATCHED", "ACTIVE", "RETIRED", "OBSERVED"]
    confidence: float
    evidence: Optional[Evidence] = None


class SourceOut(BaseModel):
    name: str
    url: Optional[str]
    published_at: Optional[str] = None


class Processing(BaseModel):
    model_version: str
    processed_at: str
    embedding_model: str
    embedding_dim: int


class NoveltyOut(BaseModel):
    fact: dict
    status: NoveltyStatus
    confidence: float
    matched_fact_id: Optional[str]
    superseded_fact_ids: list[str]
    conflicting_fact_ids: list[str]
    reason: str


class AnalyzeResponse(BaseModel):
    document_id: str
    source: SourceOut
    entities: list[EntityOut]
    relations: list[RelationOut]
    behaviors: list[BehaviorOut]
    temporal_events: list[TemporalOut]
    document_embedding: list[float]
    novelty: list[NoveltyOut]
    processing: Processing
    schema_version: Literal["1.1"]


# ---------- /embed ----------
class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)


class EmbedResponse(BaseModel):
    model: str
    dim: int
    embeddings: list[list[float]]


# ---------- /resolve ----------
class MentionIn(BaseModel):
    mention: str
    type: Optional[str] = None


class KnownEntityIn(BaseModel):
    entity_id: str
    canonical_name: str
    type: str
    aliases: list[str] = []


class ResolveRequest(BaseModel):
    mentions: list[MentionIn]
    known_entities: list[KnownEntityIn]


class ResolveResult(BaseModel):
    mention: str
    entity_id: Optional[str]
    canonical_name: str
    method: Literal["exact", "alias", "builtin_alias", "string_similarity", "semantic_similarity", "none"]
    score: float
    new_aliases: list[str]


class ResolveResponse(BaseModel):
    results: list[ResolveResult]


# ---------- /classify_novelty ----------
class FactIn(BaseModel):
    subject: str
    subject_type: Optional[str] = None
    relation: str
    object: str
    object_type: Optional[str] = None
    negated: bool = False
    confidence: float = Field(ge=0, le=1)
    evidence: Optional[dict] = None


class CandidateIn(BaseModel):
    fact_id: str
    subject: str
    subject_aliases: list[str] = []
    relation: str
    object: str
    object_aliases: list[str] = []
    status: Literal["ACTIVE", "HISTORICAL"]
    negated: bool = False
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    source_name: Optional[str] = None


class ClassifyNoveltyRequest(BaseModel):
    document_id: Optional[str] = None
    published_at: Optional[str] = None
    facts: list[FactIn]
    candidates: list[CandidateIn]


class ClassifyNoveltyResponse(BaseModel):
    results: list[NoveltyOut]

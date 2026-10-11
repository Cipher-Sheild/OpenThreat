# Database Schema

This document outlines the standard Cyber Threat Intelligence (CTI) schema implemented in the OpenThreat NLP platform.

## Core Tables

### sources
Stores information about where intelligence was gathered from.
- `id`: UUID (Primary Key)
- `name`: String
- `source_type`: String (e.g., 'user_upload', 'nvd', 'cisa_feed')
- `url`: String (Nullable)
- `reliability`: Float (0-1)

### documents
Represents a piece of raw intelligence (e.g., a blog post, a PDF report).
- `id`: UUID (Primary Key)
- `source_id`: UUID (Foreign Key to sources)
- `title`: String
- `content_hash`: String (SHA256 of original content)
- `url`: String (Nullable, source URL)
- `external_id`: String (Nullable, source's internal ID)
- `published_at`: DateTime
- `first_seen_at`: DateTime
- `processing_status`: String (PENDING, PROCESSING, COMPLETED, FAILED)
- `content`: Retained text for inspection and processing
- `processing_error`: Nullable processing failure explanation
- `embedding_status`: Separate vector indexing state
- `processing_metadata`: JSON for extraction and indexing metadata

### document_versions
Tracks changes to documents over time.
- `id`: UUID (Primary Key)
- `document_id`: UUID (Foreign Key to documents)
- `version_hash`: String
- `processed_at`: DateTime
- `raw_content_path`: String
- `content`: Nullable retained previous document text

### entities
Identified CTI entities (Threat Actors, Malware, Vulnerabilities, Infrastructure).
- `id`: UUID (Primary Key)
- `canonical_name`: String
- `type`: String
- `confidence`: Float (0-1)
- `first_seen_at`: DateTime
- `last_seen_at`: DateTime

### entity_aliases
Alternative names for entities (e.g., APT28 = Fancy Bear).
- `id`: UUID (Primary Key)
- `entity_id`: UUID (Foreign Key to entities)
- `alias`: String

### relations
Relationships between entities (e.g., Threat Actor USES Malware).
- `id`: UUID (Primary Key)
- `subject_id`: UUID (Foreign Key to entities)
- `relation_type`: String
- `object_id`: UUID (Foreign Key to entities)
- `confidence`: Float (0-1)
- `first_seen_at`: DateTime
- `last_seen_at`: DateTime
- `status`: String (ACTIVE, HISTORICAL)
- `negated`: Boolean indicating negative assertions
- `source_first_seen_at`, `source_last_seen_at`: Nullable source chronology
- `review_required`: Boolean for analyst review

### behaviors
Observed behaviors, often mapped to MITRE ATT&CK.
- `id`: UUID (Primary Key)
- `document_id`: UUID (Foreign Key to documents)
- `entity_id`: UUID (Foreign Key to entities)
- `description`: String
- `mitre_attack_id`: String (Nullable)
- `confidence`: Float (0-1)

### evidence
Text snippets from documents supporting a relation or behavior.
- `id`: UUID (Primary Key)
- `document_id`: UUID (Foreign Key to documents)
- `relation_id`: UUID (Nullable, Foreign Key to relations)
- `behavior_id`: UUID (Nullable, Foreign Key to behaviors)
- `snippet`: String
- `char_start`, `char_end`, `page_number`: Nullable source offsets and provenance fields. Platform PDF imports currently do not preserve page-level evidence.

### intelligence_changes
Audit log for intelligence lifecycle (Novelty/Updates).
- `id`: UUID (Primary Key)
- `entity_type`: String (Relation, Entity, Behavior)
- `entity_id`: UUID
- `change_type`: String (NEW, KNOWN, UPDATED, CONFLICTING, UNCERTAIN)
- `timestamp`: DateTime
- `document_id`: Nullable source document link
- `reason`: Nullable classification explanation

### temporal_events
Stores dated extracted events linked to a document and entity.
- `id`: UUID primary key
- `document_id`, `entity_id`: Foreign keys
- `event`, `time`, `type`: Event description, extracted date string and event type
- `confidence`: Model or rule score
- `evidence`: Nullable JSON evidence

## Vector storage and migrations

Qdrant indexes 768-dimensional document vectors using cosine distance in `document_embeddings`. Its points use document UUIDs and metadata payloads. PostgreSQL remains the source of truth for provenance and stored facts; the two stores do not share one atomic transaction. Failed indexing is recorded and retryable.

Alembic migrations are in `platform-service/app/database/migrations`. Platform startup applies migrations. Query indexes support canonical names, aliases, relationship endpoints, evidence, document processing and lifecycle timestamps. Runtime database contents and backups are excluded from the public repository.

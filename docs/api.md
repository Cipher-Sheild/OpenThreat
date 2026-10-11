# API Documentation

## Platform Service (Port 8002)

### `GET /health`
Returns the health status of the Platform Service.

### `POST /api/v1/upload`
Submit text for asynchronous processing. The JSON body includes required `title` and `content`, with optional `source_name`, `url` and `published_at`. Source URLs must use HTTP or HTTPS. The response is HTTP 202 with `status` and `document_id`; it is not a completed extraction result.

### `POST /api/v1/upload-file`
Upload a searchable PDF, HTML, Markdown or text file as multipart data with a `file` field. Text extraction rejects unreadable documents. The response is HTTP 202 with `status` and `document_id`. Scanned PDFs require OCR before submission.

### Other platform routes

| Method and route | Purpose |
|---|---|
| `POST /api/v1/documents/{doc_id}/retry` | Retry eligible failed processing or indexing |
| `POST /api/v1/trigger-ingestion` | Queue configured source collection |
| `GET /api/v1/dashboard/stats` | Corpus totals and processing state |
| `GET /api/v1/intelligence/feed` | Recent classifications and evidence |
| `GET /api/v1/graph` | Bounded entity relationship graph |
| `GET /api/v1/entities` | Paginated entity directory |
| `GET /api/v1/documents` | Report library and semantic search |
| `GET /api/v1/documents/{doc_id}` | Report content, metadata and original source |
| `GET /api/v1/intelligence/entity/{entity_id}/timeline` | Lifecycle evidence, dates and source links |
| `GET /api/v1/exports/{kind}` | CSV, JSON, classification audit or restricted STIX export |

Interactive platform documentation is available at http://localhost:8002/docs. Refer to the generated OpenAPI schema for request limits and exact query parameters. Processing status is separate from embedding synchronization; a completed document can require an indexing retry.

## NLP Service (Port 8001)

Contract v1.1: request/response schemas are in `docs/contracts/` (see `CHANGELOG.md` there).
Interactive docs: http://localhost:8001/docs

### `GET /health`
Returns the health status of the NLP Service, plus model and schema versions.

### `POST /analyze`
Document in, structured intelligence out (`nlp_output_schema.json`).
- Request: `{"document_id", "text" | "pages": [{"page_number", "text"}], "source_name", "source_url", "published_at"}`
- Response: entities, relations (with evidence), behaviours (ATT&CK), temporal events, 768-dim `document_embedding`. `novelty` is always `[]` here.

### `POST /embed`
`{"texts": [...]}` → `{"model", "dim": 768, "embeddings": [[...]]}`. Use for Qdrant queries.

### `POST /resolve`
`{"mentions": [{"mention", "type"}], "known_entities": [{"entity_id", "canonical_name", "type", "aliases"}]}`
→ for each mention: matched `entity_id` (or null = new entity), `method`, `score`, `new_aliases`.

### `POST /classify_novelty`
`{"published_at", "facts": [relations from /analyze], "candidates": [stored facts]}`
→ per fact: `status` (NEW / KNOWN / UPDATED / CONFLICTING / UNCERTAIN), `matched_fact_id`,
`superseded_fact_ids` (set HISTORICAL), `conflicting_fact_ids` (flag), `reason`.

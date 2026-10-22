# Contract changelog

The contract is `nlp_output_schema.json` (response of `POST /analyze`) and
`nlp_service_api.json` (requests for all endpoints, and the responses of `/embed`, `/resolve`
and `/classify_novelty`). Never change them without bumping `schema_version` and agreeing together.

## Service 0.3.0 — 2026-10-03 (no contract change)
- Trained NER/RE models (Phase 3) run in hybrid mode with the rules when `NER_MODEL` / `RE_MODEL` are set.
- Behaviours are also mapped to ATT&CK by meaning (Phase 4), so more `behaviors[]` items appear, with
  `mitre_attack_id` filled.
- Temporal events now resolve relative dates ("last month") against `published_at`.
- `/health` reports `ner_model` and `re_model`. `processing.model_version` names the models used.

## v1.1 — 2026-10-02 (NLP service)

Implements the points agreed after the v1.0 review, plus the gaps found while building Phase 2.

### Agreed with platform service
| Change | Why |
|---|---|
| `/analyze` request: `document_id`, `text`, `source_name`, `source_url` | Fixed request format |
| `evidence` **required** on relations and behaviours | "No fact without provenance" |
| `mitre_attack_id` **nullable** | Not every behaviour maps to ATT&CK |
| `page_number`, `char_start`, `char_end` on entities and evidence | Ready for PDF evidence (Phase 6) |
| Novelty is classified by the NLP service via `POST /classify_novelty` | platform service sends candidate facts, NLP returns the label, platform service persists |
| Model weights in a mounted `model_cache` folder, not in the image | Image size |

### Decided by NLP service while platform service was offline (please review)
| Change | Why |
|---|---|
| **Embedding: `BAAI/bge-base-en-v1.5`, 768 dims, cosine, L2-normalised** | Configure Qdrant collections with `size=768, distance=Cosine` |
| `published_at` added to the `/analyze` and `/classify_novelty` requests (optional) | Needed to tell which source is newer (UPDATED vs CONFLICTING) |
| `evidence` is now an **object** `{text, char_start, char_end, page_number}` (was a string) | Needed for the position fields. `page_number` is `null` for non-PDF input |
| `/analyze` accepts `pages: [{page_number, text}]` instead of `text` | PDFs: send one item per page; offsets refer to the pages joined with `"\n\n"` |
| `relations[]` gained `subject_type`, `object_type`, `negated` | platform service needs the types to create entities; `negated` marks "no longer uses", "is not attributed to" |
| `entities[]` gained `subtype` (ipv4, domain, sha256, …, `sector`, `coreference`) | Lets the platform treat IOCs differently |
| `behaviors[]` gained `mitre_attack_name` | Display |
| `temporal_events[].type` is an enum: FIRST_SEEN, DISCLOSED, PATCHED, ACTIVE, RETIRED, OBSERVED; `time` is ISO 8601, possibly partial (`2024`, `2024-03`) | |
| `document_embedding` is now **required**, exactly 768 numbers | Qdrant needs it |
| `processing` gained `embedding_model`, `embedding_dim` | Reproducibility |
| `novelty` stays in the `/analyze` response but is **always `[]`** there | Labels come from `/classify_novelty`, which needs the DB candidates |
| `novelty[]` items gained `matched_fact_id`, `superseded_fact_ids`, `conflicting_fact_ids`, `reason` | platform service must know which stored fact to bump / mark HISTORICAL / flag |
| New request/response schemas for `/embed`, `/resolve`, `/classify_novelty` | Were undefined |
| Entity and relation types are enums (the v1 taxonomy) | Catches typos on both sides |

### v1 taxonomy (now enforced by the schema)
- Entities: `THREAT_ACTOR, MALWARE, TOOL, VULNERABILITY, TECHNIQUE, ORGANIZATION, OBSERVABLE`
- Relations: `USES, DEPLOYS, EXPLOITS, TARGETS, ATTRIBUTED_TO`
- Canonical names: ATT&CK names for actors/software (Fancy Bear → `APT28`, X-Agent → `CHOPSTICK`),
  upper-case IDs for CVEs (`CVE-2023-23397`) and techniques (`T1566.001`), refanged lower-case IOCs
  (`update-check[.]com` → `update-check.com`), sectors as `"Energy sector"`.

## Novelty labelling policy (v1.1)

| # | Condition | Label | What platform service stores |
|---|---|---|---|
| 1 | No existing fact for this subject + relation (after entity resolution), **or** a multi-valued relation (USES, DEPLOYS, EXPLOITS, TARGETS) gains another object | **NEW** | Insert as ACTIVE. Old facts stay ACTIVE |
| 2 | Same resolved subject + relation + object as an existing fact | **KNOWN** | Bump `last_seen_at` of `matched_fact_id`; add the evidence row |
| 3 | The new fact **supersedes** an old one: single-valued relation (ATTRIBUTED_TO) with a different object where the new source is newer or explicitly revises it ("now attributed to"); or "no longer uses X" about an ACTIVE "uses X" | **UPDATED** | Insert as ACTIVE; set every id in `superseded_fact_ids` to HISTORICAL |
| 4 | The new fact contradicts an ACTIVE fact without clearly superseding it (sources disagree, no time order; or a denial like "is not attributed to") | **CONFLICTING** | Insert as ACTIVE; keep `conflicting_fact_ids` ACTIVE; flag both for analyst review |
| 5 | Fact confidence < 0.50, or the subject/object match is below 0.90 | **UNCERTAIN** | Store with status UNCERTAIN or queue for review (platform service's choice) |

Nothing is ever deleted.

**Note:** this changes rule 3 of the starter guide. "A new tool alongside an existing one" is now
**NEW**, not UPDATED, as platform service requested. `docs/project_specification.md` §3–4 still says platform service
implements the rules; that section should be updated to match.

### `/classify_novelty` — what to send as `candidates`
For each new fact, existing facts (ACTIVE **and** HISTORICAL) whose subject resolves to the same
entity, e.g. `SELECT … FROM relations JOIN entities … WHERE subject_id IN (resolved ids)`.
Include `subject_aliases` / `object_aliases` from `entity_aliases` so alias matches work. Extra
candidates are harmless; missing ones produce false NEW labels.

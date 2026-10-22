# services/nlp — NLP & Intelligence Engine

NLP service. Answers: *"What does this document mean, and is this fact new?"*
Talks to the platform only through the contract in `docs/contracts/` (v1.1).

**Status: Phases 2–5.** Rule-based pipeline (Phase 2) + trained NER/RE models in hybrid mode
(Phase 3) + semantic ATT&CK mapping and relative dates (Phase 4) + evaluation suite (Phase 5).
The API contract is unchanged (v1.1).

## Run it

```bash
# from the repo root
docker compose up --build nlp-service
# http://localhost:8001/health   http://localhost:8001/docs
```

The first start downloads the embedding model (~440 MB) into `services/nlp/model_cache/`
(git-ignored). Later starts reuse it.

Tests (no Docker or model download needed; they use a small stand-in embedder):

```bash
cd services/nlp
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
python -m pytest -q
```

## Phase 3 — trained models

Training runs on a GPU in Google Colab: open `training/train_models_colab.ipynb`, set your Hugging
Face username, *Run all*. It trains SecureBERT on **CyberNER** (NER, 7 types) and on **AZERG**
(relations, 5 types), evaluates both, and uploads them to `<hf-user>/openthreat-ner` and
`<hf-user>/openthreat-re`. Then switch them on in the repo-root `.env`:

```bash
NER_MODEL=<hf-user>/openthreat-ner
RE_MODEL=<hf-user>/openthreat-re
```

and restart the service. With the models set, extraction is **hybrid**: model predictions plus the
regex IOCs and ATT&CK name lists (`app/pipeline/models.py`). Without them, the rules run alone.
The notebook is generated from `training/*.py` (`python training/build_notebook.py`); every run
writes a reproducibility log (dataset hash, base model, hyper-parameters, seed, metrics) to
`experiments/`.

## Phase 4/5 — evaluation

```bash
# from the repo root, with the service image built and .env set
docker compose run --rm -v "$PWD/services/nlp:/work" -w /work nlp-service python evaluation/run_all.py
```

| Script | What it measures |
|---|---|
| `evaluation/eval_ner.py` | NER P/R/F1 per type on the CyberNER test split: rules vs hybrid |
| `evaluation/eval_attack.py` | ATT&CK mapping top-1/top-3 on held-out TRAM documents and CTI-HAL; threshold calibration |
| `evaluation/eval_temporal.py` | Temporal extraction on a 30-sentence labelled set |
| `evaluation/eval_novelty.py` | Novelty benchmark (142 pairs): full pipeline vs keyword / string / embedding baselines, ablations, confusion matrix |

The novelty benchmark is built by `evaluation/build_novelty_benchmark.py`; its labels must be
checked by both members in `evaluation/data/novelty_benchmark_review.csv` before reporting.

## Endpoints

| Endpoint | In | Out |
|---|---|---|
| `GET /health` | | status, model and schema versions |
| `POST /analyze` | `document_id`, `text` **or** `pages`, `source_name`, `source_url`, `published_at` | entities, relations, behaviours, temporal events, 768-dim document embedding (`nlp_output_schema.json`) |
| `POST /embed` | `texts` (≤256) | 768-dim vectors |
| `POST /resolve` | mentions + known entities from Postgres | which entity each mention is (exact → alias → ATT&CK alias → fuzzy → semantic) |
| `POST /classify_novelty` | new facts + candidate facts from Postgres | NEW / KNOWN / UPDATED / CONFLICTING / UNCERTAIN + which stored facts to bump / supersede / flag |

## Pipeline (Phase 2)

| Step | File | Method now | Phase 3+ plan |
|---|---|---|---|
| Preprocessing | `app/pipeline/preprocess.py` | Sentence split with offsets; **text is never modified** so IOCs survive | — |
| NER | `ner.py`, `gazetteer.py` | Regex (CVE, IPs, domains, URLs, hashes, ATT&CK IDs; defanged forms), ATT&CK + hand-made name lists, name patterns, simple "the group" coreference | Fine-tuned transformer on CyberNER |
| Relations | `relations.py` | Trigger verbs between entity pairs, passive voice, type constraints, negation | Trained RE model (AZERG + own annotations) |
| Behaviours | `behaviors.py` | Explicit technique IDs and exact technique names | + semantic mapping (Phase 4) |
| Temporal | `temporal.py` | Date patterns + cue words | Phase 4 refinements |
| Embeddings | `embeddings.py` | `BAAI/bge-base-en-v1.5`, chunked + length-weighted mean | — |
| Resolution | `resolution.py` | 5-step cascade with type filter | Tune thresholds on a labelled set |
| Novelty | `novelty.py` | Policy rules 1–5 (see `docs/contracts/CHANGELOG.md`) | Evaluate on the Phase 5 benchmark |

Settings (thresholds, model name, single-valued relations) are in `app/config.py` and can be
overridden with environment variables.

## Folder layout

```
app/                 service code (mounted into the container)
  resources/         ATT&CK name lists (scripts/build_attack_resources.py) + extra_entities.json
scripts/             build_attack_resources.py
tests/               pytest suite + two fixture reports
docs/                evaluation report template
model_cache/         downloaded model weights (git-ignored)
```

ATT&CK® data © The MITRE Corporation, used under the ATT&CK Terms of Use.

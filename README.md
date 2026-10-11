# OpenThreat NLP

**An NLP-Driven System for Semantic Correlation and Temporal Analysis of Cyber Threat Intelligence**

OpenThreat converts English cybersecurity reports into searchable, evidence-linked intelligence. Analysts can inspect extracted entities and relationships, compare changing claims, explore a knowledge graph, review dated events and open the original source report.

![Analyst dashboard](docs/images/overview.png)

## What the platform does

- Collects reports from NVD, CISA KEV and configured RSS sources; accepts text, Markdown, HTML and searchable PDF imports.
- Combines trained entity and relation classifiers with identifier patterns and reference dictionaries when checkpoints are configured.
- Uses BGE embeddings for document similarity search and semantic MITRE ATT&CK mapping.
- Classifies extracted facts as NEW, KNOWN, UPDATED, CONFLICTING or UNCERTAIN using deterministic evidence and chronology rules.
- Preserves source links, evidence sentences, publication metadata and extracted temporal events.
- Provides analytics, a relationship graph, document search and CSV, JSON and restricted STIX 2.1 exports.

## Architecture

![System architecture](docs/images/architecture.svg)

| Component | Technology | Responsibility |
|---|---|---|
| Browser interface | React, TypeScript, Vite, Tailwind CSS | Analyst workflows, graph and analytics |
| Platform service | FastAPI, SQLAlchemy, Alembic | Collection, persistence, evidence and fact lifecycle |
| NLP service | PyTorch, Transformers, Sentence Transformers | Extraction, embeddings, behavior and temporal analysis |
| Structured storage | PostgreSQL 16 | Documents, entities, relationships and provenance |
| Vector storage | Qdrant | 768-dimensional document similarity index |

Read [architecture](docs/architecture.md), [methodology](docs/methodology.md), [API documentation](docs/api.md), and [database documentation](docs/database.md).

## Download and run the full application

Download or clone **the entire repository**, not just this README. It includes frontend, platform API, NLP service, database migrations, Docker configuration, trained-model links, tests and documentation. The startup scripts generate your private environment settings and start all five services.

Install and start [Docker with Compose](https://docs.docker.com/compose/install/), open a terminal in this folder, and run one command:

**Windows PowerShell**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

**Linux or macOS**

```sh
sh ./start.sh
```

Then open **http://localhost:4000**. First startup downloads BGE embeddings and the real project NER and relation models; wait for `ready: true` at http://localhost:8001/health. The database begins empty. Import a report or enable public-source collection to populate it.

Read the complete [Docker quickstart](docs/quickstart.md) for first-report steps, logs, restart commands, port changes and troubleshooting. No host Python, Node.js or separate database installation is needed for the application. Model weights are downloaded and cached outside Git rather than committed into the repository.

The example environment configures `alialtam/openthreat-ner` and `alialtam/openthreat-re`. See [model setup](docs/models-and-data.md) for the original links and alternate checkpoints. Leaving those variables empty intentionally selects rule-only entity/relation extraction and does not reproduce the trained-model benchmark scores.

Automatic collection is disabled initially. Set `AUTO_INGEST=true` to enable it. Compose binds ports to loopback for this local setup; see [deployment](docs/deployment.md) before internet hosting.

## Screenshots

| Analytics | Relationship graph |
|---|---|
| ![Analytics](docs/images/analytics.png) | ![Knowledge graph](docs/images/knowledge-graph.png) |

See the [screenshot gallery](docs/screenshots.md) for report browsing, lifecycle evidence and exports. Totals and scores shown in screenshots are captured application state, not accuracy estimates.

## Evaluation

| Saved evaluation | Result | Interpretation |
|---|---|---|
| Rules NER exact-span micro F1 | 0.3655 | CyberNER service evaluation |
| Fine-tuned NER micro F1 | 0.6699 | Saved model test; windowed evaluation |
| Hybrid NER micro F1 | 0.6207 | Service evaluation; gold supports differ slightly |
| Relation positive-class micro / macro F1 | 0.8611 / 0.4873 | Rare relation classes remain weak |
| Novelty accuracy / macro F1 | 0.9085 / 0.8183 | 142 constructed pairs in the NLP evaluation harness |

These results do not measure end-to-end live-platform accuracy. The novelty harness includes a resolution cascade that the platform ingestion path does not fully invoke. The fine-tuned NER result exceeds hybrid NER on the saved evaluations. See [evaluation details](docs/evaluation.md) for scope and limitations.

## Repository layout

```text
frontend/          Analyst interface and production build configuration
nlp-service/       Inference, training, evaluation and tests
platform-service/ API, collectors, migrations, lifecycle and tests
docs/             Architecture, methodology, screenshots and saved metrics
licenses/         Required third-party resource terms and notices
data/             Empty runtime directories; collected data is ignored
```

## Development and testing

Frontend: run `npm ci`, then `npm run build` in `frontend/`.

NLP: install CPU PyTorch and `nlp-service/requirements-dev.txt` in a Python environment, then run `python -m pytest -q` in `nlp-service/`. Tests use isolated mock/hash modes; they are not a trained-model accuracy benchmark.

Platform: install `platform-service/requirements.txt`, then run `python -m unittest discover -s tests -v` in `platform-service/`. Regression tests use an isolated SQLite database. Live smoke checks require a running NLP service.

## Limits and roadmap

Entity errors can propagate into relationships. Cross-sentence attribution and IOC ownership are incomplete. Temporal evaluation is small, confidence is uncalibrated, and CPU processing can be slow. Scanned PDFs require OCR before import. Public user authentication, role authorization, TLS and a durable distributed job queue are future deployment work. Human-reviewed operational evaluation and an audited correction workflow are priorities.

## License

Original code and documentation use the [MIT license](LICENSE). Bundled reference resources and external dependencies retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).

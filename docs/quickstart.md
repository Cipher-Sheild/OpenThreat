# Run OpenThreat on your computer

Download the entire repository ZIP or clone the repository. Extract it into a folder and open a terminal in that folder. The README is the instructions file; it is not the application by itself.

## Prerequisites

Install and start [Docker Desktop](https://docs.docker.com/compose/install/) on Windows or macOS. Docker Desktop includes the Docker Engine, CLI and Compose. Linux users can use Docker Engine with the Compose plugin. On Windows select Linux containers. You do not need to install Python, Node.js, PostgreSQL or Qdrant separately for the application.

The first build needs internet access for container dependencies and model downloads. Allocate sufficient disk and memory for PostgreSQL, Qdrant, PyTorch, three language models and the browser service. Exact minimum hardware and startup time have not been benchmarked. CPU extraction and initial embedding of technique anchors can take time.

## Start on Windows

From PowerShell in the extracted repository folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

The execution-policy option applies to that script process. The script creates an ignored `.env` with a random database password when one does not already exist, then builds and starts the containers. It preserves an existing environment file.

## Start on Linux or macOS

```sh
sh ./start.sh
```

## Open the application

| Address | Use |
|---|---|
| http://localhost:4000 | Analyst application |
| http://localhost:8001/health | NLP loading state and configured model IDs |
| http://localhost:8001/docs | NLP API documentation |
| http://localhost:8002/docs | Platform API documentation |

The default environment configures the real project NER and relation checkpoints and BGE embeddings. Docker downloads them into `nlp-service/model_cache` on first startup. Wait for NLP health to show `ready: true`; a process that is running can still be warming. If downloading or loading fails, the health endpoint reports an error and the logs provide details. The interface can load before extraction is ready.

## Try your first report

The database starts empty. Open **Import Report**, provide a report title and English text, add its HTTP/HTTPS source URL and publication date where available, then submit it. Wait for processing in Databanks; inspect the extracted entities, lifecycle evidence and source link. Open the Knowledge Graph and Analytics after processing completes.

For a quick functional demonstration you may submit: “APT28 used Mimikatz to dump credentials and exploited CVE-2023-23397.” Label its title “Authored demonstration” and treat the output as a test, not as new verified intelligence. Entity or relation predictions can vary or be wrong.

Automatic source collection is disabled initially. Collect through **Data Sources**, or set `AUTO_INGEST=true` in `.env` and recreate services with `docker compose up -d`. Set `NVD_API_KEY` only in your ignored environment file if you have one. Collectors use public source services and remain subject to their availability and limits.

## Common commands

```sh
docker compose ps
docker compose logs -f nlp-service
docker compose logs --tail 100 platform-service
docker compose stop
docker compose start
docker compose down
```

`down` removes the containers but preserves named database volumes. The model cache persists in its host folder. Do not add `-v` unless you intend to delete stored database volumes. Rebuild after code changes using `docker compose up -d --build`.

## Manual setup instead of the scripts

Copy `.env.example` to `.env`, set a strong alphanumeric `POSTGRES_PASSWORD`, and run:

```sh
docker compose up -d --build
```

The PostgreSQL password appears in a connection URI, so reserved URI characters require correct escaping; the startup scripts generate a hex password that avoids this issue.

## If startup fails

- **Docker cannot connect:** start Docker Desktop or your Docker daemon and verify `docker info`.
- **A port is occupied:** stop the conflicting service or change the corresponding port in `.env`. Open the new frontend or API address afterward.
- **Models are warming:** watch NLP logs; the first download and technique-anchor embedding can take much longer than a cached restart.
- **Model download fails:** check internet access, the checkpoint links and download errors. The normal public checkpoints do not require a personal token. Alternative private models need a separately configured credential.
- **Processing failed:** inspect the document error and platform logs, correct the input or dependency problem, and use the retry control.
- **Search indexing failed:** inspect Qdrant and platform logs; indexing is tracked separately from extraction.
- **PDF yields no text:** perform OCR before uploading scanned PDFs.

See [model configuration](models-and-data.md), [architecture](architecture.md), and [hosting considerations](deployment.md). This setup runs the application on your computer; internet hosting remains a separate deployment task.

#!/usr/bin/env sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$repo_root"
if [ ! -f .env ]; then
    database_password=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    (umask 077; sed "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$database_password/" .env.example > .env)
    printf '%s\n' 'Created your ignored .env with a generated database password.'
else
    printf '%s\n' 'Using your existing .env without changing its settings.'
fi
if [ "${1:-}" = '--prepare-only' ]; then exit 0; fi
if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'Install Docker with Compose and start Docker before running this script.' >&2
    exit 1
fi
docker compose version
docker info --format '{{.ServerVersion}}'
docker compose config --quiet
docker compose up -d --build
printf '%s\n' 'Open http://localhost:4000 after startup.'
printf '%s\n' 'Models download and warm up in the background on first launch.'
printf '%s\n' 'Check NLP readiness at http://localhost:8001/health and logs with: docker compose logs -f nlp-service'

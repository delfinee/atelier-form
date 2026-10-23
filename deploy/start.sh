#!/bin/sh
set -eu
cd "$(dirname "$0")"
test -f .env.production || { echo 'Configure deploy/.env.production first.' >&2; exit 1; }
chmod 600 .env.production
docker compose --env-file .env.production -f compose.yml up -d --build
docker compose --env-file .env.production -f compose.yml ps

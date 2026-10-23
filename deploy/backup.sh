#!/bin/sh
set -eu
cd "$(dirname "$0")"
umask 077
mkdir -p backups
target="backups/seller-$(date -u +%Y%m%dT%H%M%SZ).dump"
test ! -e "$target"
docker compose --env-file .env.production -f compose.yml exec -T db pg_dump -U atelier_seller -d atelier_seller -Fc > "$target.partial"
test -s "$target.partial"
mv "$target.partial" "$target"
echo "$target"

#!/usr/bin/env sh
# Nightly Postgres backup for the production stack (run on the VM from the repo root).
#   crontab -e   ->   15 3 * * * cd /home/ubuntu/JobPilot && sh scripts/backup.sh >> data/backups/backup.log 2>&1
# Keeps the last 14 days. Resume files live in the "uploads" volume: back that up too if you
# want to restore them (they're encrypted; FILE_MASTER_KEY is needed to read them).
set -eu

KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p data/backups

docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' \
  > "data/backups/jobpilot-$STAMP.dump"

find data/backups -name 'jobpilot-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) backup ok: jobpilot-$STAMP.dump ($(du -h "data/backups/jobpilot-$STAMP.dump" | cut -f1))"

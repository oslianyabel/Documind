#!/usr/bin/env bash
# Export ALL system data to a portable backup directory:
#   - database.dump    : full PostgreSQL dump (pg_dump custom format -Fc:
#                        compressed, restorable with pg_restore) — documents,
#                        chunks + embeddings, api_keys, search/upload history,
#                        app settings.
#   - documents.tar.gz : original PDFs and cover images (the api container's
#                        /app/data volume).
#
# Usage (from the repo root, with the stack running):
#   ./scripts/export_backup.sh [backup_dir]
# Env overrides: COMPOSE_FILE (default docker-compose.prod.yml),
#                POSTGRES_USER / POSTGRES_DB (default documind).
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
POSTGRES_USER="${POSTGRES_USER:-documind}"
POSTGRES_DB="${POSTGRES_DB:-documind}"
BACKUP_DIR="${1:-backups/$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$BACKUP_DIR"

echo "[1/2] Dumping PostgreSQL ($POSTGRES_DB) ..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$BACKUP_DIR/database.dump"

echo "[2/2] Archiving document files (/app/data) ..."
docker compose -f "$COMPOSE_FILE" cp api:/app/data "$BACKUP_DIR/data"
tar -C "$BACKUP_DIR" -czf "$BACKUP_DIR/documents.tar.gz" data
rm -rf "$BACKUP_DIR/data"

echo "Backup completo en: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"

#!/usr/bin/env bash
# Restore a backup produced by export_backup.sh into a (new) server.
#
# Steps on the new server:
#   1. Clone the repo, create .env, start the stack:
#        docker compose -f docker-compose.prod.yml up -d --build
#   2. Copy the backup directory to the server and run:
#        ./scripts/import_backup.sh backups/20260710_120000
#
# The restore is destructive on purpose (--clean): existing rows are replaced
# by the backup's content.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
POSTGRES_USER="${POSTGRES_USER:-documind}"
POSTGRES_DB="${POSTGRES_DB:-documind}"
BACKUP_DIR="${1:?Uso: ./scripts/import_backup.sh <backup_dir>}"

if [[ ! -f "$BACKUP_DIR/database.dump" || ! -f "$BACKUP_DIR/documents.tar.gz" ]]; then
  echo "ERROR: $BACKUP_DIR debe contener database.dump y documents.tar.gz" >&2
  exit 1
fi

echo "[1/2] Restoring PostgreSQL ($POSTGRES_DB) ..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < "$BACKUP_DIR/database.dump"

echo "[2/2] Restoring document files (/app/data) ..."
tar -C "$BACKUP_DIR" -xzf "$BACKUP_DIR/documents.tar.gz"
docker compose -f "$COMPOSE_FILE" cp "$BACKUP_DIR/data/." api:/app/data
rm -rf "$BACKUP_DIR/data"

echo "Restauración completa. Verifica con:"
echo "  curl http://127.0.0.1:8080/api/health"

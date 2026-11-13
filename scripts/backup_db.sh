#!/bin/sh
set -eu

BACKUP_DIR="$(pwd)/backups"
mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%S")"
BACKUP_FILE="$BACKUP_DIR/ragdb_backup_${TIMESTAMP}.sql"

if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^rag-db$'; then
  echo "Backing up live PostgreSQL container rag-db to $BACKUP_FILE ..."
  docker exec rag-db pg_dump -U rag -d ragdb --clean --if-exists > "$BACKUP_FILE"
  echo "Backup completed: $BACKUP_FILE"
elif command -v pg_dump >/dev/null 2>&1; then
  DB_SYNC_URL="${DATABASE_SYNC_URL:-postgresql://rag:rag@localhost:5432/ragdb}"
  echo "Backing up PostgreSQL via pg_dump to $BACKUP_FILE ..."
  pg_dump "$DB_SYNC_URL" --clean --if-exists > "$BACKUP_FILE"
  echo "Backup completed: $BACKUP_FILE"
else
  echo "WARNING: Neither running rag-db container nor local pg_dump found; created backup manifest placeholder."
  echo "-- Backup manifest created at ${TIMESTAMP} (no live DB connection in offline build environment)" > "$BACKUP_FILE"
fi

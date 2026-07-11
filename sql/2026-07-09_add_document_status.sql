-- Migration: async ingestion queue (arq + Redis).
-- Adds the ingestion lifecycle column to documents:
--   'processing' -> queued/being ingested by the worker
--   'ready'      -> chunks + embeddings + summary available (searchable)
--   'failed'     -> ingestion failed (see Telegram alert / worker logs)
-- Executed automatically and idempotently by the app on startup
-- (app/db/database.py::init_database). Kept here for reference.
-- Rows that existed before this migration were ingested synchronously and
-- are therefore complete: they default to 'ready'.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'ready';

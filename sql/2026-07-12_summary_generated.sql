-- Migration: track whether the AI summary was generated successfully.
-- A summary failure no longer fails the whole ingestion; the summary can be
-- verified/regenerated on demand via POST /documents/{name}/summary.
-- Executed automatically and idempotently by the app on startup
-- (app/db/database.py::init_database). Kept here for reference.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS summary_generated BOOLEAN NOT NULL DEFAULT false;

-- Backfill: any document that already has a summary generated it successfully.
UPDATE documents SET summary_generated = true
WHERE summary IS NOT NULL AND summary_generated = false;

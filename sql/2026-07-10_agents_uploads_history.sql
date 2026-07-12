-- Migration: answer/scope agents + upload history.
-- Executed automatically and idempotently by the app on startup
-- (app/db/database.py::init_database). Kept here for reference.
--
-- 1. search_history.passed_validation: whether the query passed the
--    search-scope validation agent. Historical rows default to true.
ALTER TABLE search_history
    ADD COLUMN IF NOT EXISTS passed_validation BOOLEAN NOT NULL DEFAULT true;

-- 2. New tables (created automatically by SQLAlchemy create_all):
--    upload_history: one row per uploaded file with its outcome
--      ('processing' -> 'success' | 'failed' with error_traceback;
--       'skipped_duplicate' when content already existed)
--    app_settings: key/value store, e.g. key 'search_scope_prompt' holds the
--      prompt that defines which semantic-search queries are in scope.

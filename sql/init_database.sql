-- Executed automatically by the postgres container on first boot
-- (mounted into /docker-entrypoint-initdb.d by docker-compose.yml).
-- Tables and indexes are created by the application on startup
-- (SQLAlchemy metadata in app/db/models.py); only the extension lives here.

CREATE EXTENSION IF NOT EXISTS vector;

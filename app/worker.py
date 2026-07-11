"""arq worker that runs document ingestion jobs.

Run it as a separate process:
    uv run arq app.worker.WorkerSettings
"""

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings

from app.config import settings
from app.services.document_ingestion import process_document

logging.basicConfig(level=logging.INFO)

INGEST_DOCUMENT_JOB = "ingest_document"


async def ingest_document(_ctx: dict[str, Any], document_id: str) -> None:
    await process_document(uuid.UUID(document_id))


class WorkerSettings:
    functions = [ingest_document]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.ingestion_max_concurrent_jobs
    job_timeout = settings.ingestion_job_timeout_seconds
    # A failed job is not retried automatically: process_document already
    # marks the document as 'failed' and alerts the dev via Telegram.
    max_tries = 1

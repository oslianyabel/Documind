import asyncio
import hashlib
import logging
import traceback
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import aiofiles
from openai import OpenAIError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import DocumentNameConflictError, DocumindError
from app.core.notifications import notify_critical_error, notify_document_uploaded
from app.db.database import async_session_maker
from app.db.models import Chunk, Document, DocumentStatus, UploadHistory, UploadOutcome
from app.services.chunking import build_chunks
from app.services.embeddings import embed_texts
from app.services.pdf_parser import parse_pdf
from app.services.storage import save_cover_image, save_document_file
from app.services.summarizer import generate_summary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentUpload:
    name: str
    original_filename: str
    mime_type: str
    content: bytes
    cover_filename: str | None = None
    cover_content: bytes | None = None
    publication_year: int | None = None
    author: str | None = None
    description: str | None = None
    category: str | None = None
    language: str | None = None


async def _active_document_exists(session: AsyncSession, name: str) -> bool:
    result = await session.execute(
        select(Document.id).where(Document.name == name, Document.deleted_at.is_(None))
    )
    return result.scalar_one_or_none() is not None


async def _find_duplicate_by_content(session: AsyncSession, sha256: str) -> Document | None:
    """Return an active, already-ingested (or in-flight) document with the same
    content, so identical uploads are not embedded again.

    Failed documents are ignored: re-uploading their content should retry.
    """
    result = await session.execute(
        select(Document)
        .where(
            Document.sha256 == sha256,
            Document.deleted_at.is_(None),
            Document.status != DocumentStatus.FAILED.value,
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def register_document(
    session: AsyncSession, upload: DocumentUpload
) -> tuple[Document, bool]:
    """Fast phase: store the file on disk and create the row as 'processing'.

    Returns (document, created). ``created`` is False when the same content
    already exists (deduplicated by sha256): the existing document is returned
    and no file is written, no row is created, and no ingestion is queued.
    The heavy work (parse, embeddings, summary) runs later in the arq worker
    via process_document, so a genuine upload request still returns immediately.
    """
    sha256 = hashlib.sha256(upload.content).hexdigest()
    duplicate = await _find_duplicate_by_content(session, sha256)
    if duplicate is not None:
        return duplicate, False

    if await _active_document_exists(session, upload.name):
        raise DocumentNameConflictError(upload.name)

    document_id = uuid.uuid4()
    storage_path = await save_document_file(document_id, upload.original_filename, upload.content)
    cover_path = None
    if upload.cover_content is not None and upload.cover_filename is not None:
        cover_path = await save_cover_image(
            document_id, upload.cover_filename, upload.cover_content
        )

    document = Document(
        id=document_id,
        name=upload.name,
        original_filename=upload.original_filename,
        mime_type=upload.mime_type,
        storage_path=str(storage_path),
        sha256=sha256,
        size_bytes=len(upload.content),
        status=DocumentStatus.PROCESSING.value,
        publication_year=upload.publication_year,
        author=upload.author,
        description=upload.description,
        category=upload.category,
        language=upload.language,
        cover_image_path=str(cover_path) if cover_path is not None else None,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document, True


async def record_upload(
    session: AsyncSession,
    *,
    original_filename: str,
    document_name: str | None,
    sha256: str | None,
    outcome: UploadOutcome,
    document_id: uuid.UUID | None = None,
    error_traceback: str | None = None,
) -> UploadHistory:
    """Audit trail: one row per uploaded file with its (initial) outcome."""
    entry = UploadHistory(
        original_filename=original_filename,
        document_name=document_name,
        sha256=sha256,
        outcome=outcome.value,
        document_id=document_id,
        error_traceback=error_traceback,
        finished_at=None if outcome is UploadOutcome.PROCESSING else datetime.now(UTC),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _finish_upload_record(
    session: AsyncSession,
    upload_history_id: uuid.UUID,
    outcome: UploadOutcome,
    error_traceback: str | None = None,
) -> None:
    await session.execute(
        update(UploadHistory)
        .where(UploadHistory.id == upload_history_id)
        .values(
            outcome=outcome.value,
            error_traceback=error_traceback,
            finished_at=datetime.now(UTC),
        )
    )
    await session.commit()


async def _mark_document_failed(session: AsyncSession, document_id: uuid.UUID) -> None:
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status=DocumentStatus.FAILED.value)
    )
    await session.commit()


async def _generate_summary_safe(document_text: str) -> str | None:
    """Generate the AI summary; None on failure (never breaks ingestion)."""
    try:
        return await generate_summary(document_text)
    except OpenAIError:
        logger.exception("Summary generation failed; document stays searchable")
        return None


async def _ingest(session: AsyncSession, document: Document) -> None:
    async with aiofiles.open(document.storage_path, "rb") as file:
        content = await file.read()

    parsed = parse_pdf(content)
    chunks = build_chunks(parsed.lines, max_chars=settings.max_chunk_chars)
    # Embeddings are mandatory (their failure fails the ingestion); a summary
    # failure is recorded via summary_generated=False and retried on demand.
    embedding_result, summary = await asyncio.gather(
        embed_texts([chunk.content for chunk in chunks]),
        _generate_summary_safe(parsed.full_text),
    )

    session.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=chunk.index,
            content=chunk.content,
            start_page=chunk.start_page,
            start_line=chunk.start_line,
            end_page=chunk.end_page,
            end_line=chunk.end_line,
            embedding=vector,
        )
        for chunk, vector in zip(chunks, embedding_result.vectors, strict=True)
    )
    document.page_count = parsed.page_count
    document.chunk_count = len(chunks)
    document.summary = summary
    document.summary_generated = summary is not None
    document.embedding_tokens_used = embedding_result.total_tokens
    document.status = DocumentStatus.READY.value
    await session.commit()


async def ensure_document_summary(
    session: AsyncSession, document: Document
) -> tuple[str, bool]:
    """Return the document summary, generating (and persisting) it if missing.

    Returns (summary, generated_now). Raises OpenAIError/InvalidDocumentError
    if the on-demand generation fails — the caller decides the HTTP mapping.
    """
    if document.summary is not None:
        return document.summary, False

    async with aiofiles.open(document.storage_path, "rb") as file:
        content = await file.read()
    parsed = parse_pdf(content)
    summary = await generate_summary(parsed.full_text)

    document.summary = summary
    document.summary_generated = True
    await session.commit()
    await session.refresh(document)
    return summary, True


async def process_document(
    document_id: uuid.UUID, upload_history_id: uuid.UUID | None = None
) -> None:
    """Heavy phase, run by the arq worker: parse, chunk, embed and summarize.

    Also closes the upload_history record: 'success' on completion, 'failed'
    with the full traceback otherwise.
    """
    async with async_session_maker() as session:
        document = await session.get(Document, document_id)
        if document is None or document.deleted_at is not None:
            logger.warning("Skipping ingestion of missing/deleted document %s", document_id)
            return
        # Captured before any rollback can expire the instance: ORM attribute
        # access after rollback would trigger a sync lazy-load (MissingGreenlet).
        document_name = document.name
        failure_reason: str | None = None
        try:
            await _ingest(session, document)
        except (DocumindError, OpenAIError, OSError) as error:
            error_traceback = traceback.format_exc()
            await session.rollback()
            await _mark_document_failed(session, document_id)
            if upload_history_id is not None:
                await _finish_upload_record(
                    session, upload_history_id, UploadOutcome.FAILED, error_traceback
                )
            logger.exception("Ingestion failed for document %s", document_id)
            failure_reason = f"{type(error).__name__}: {error}"
        else:
            if upload_history_id is not None:
                await _finish_upload_record(session, upload_history_id, UploadOutcome.SUCCESS)

    if failure_reason is not None:
        await notify_critical_error(
            f"Ingestion failed for document '{document_name}' ({failure_reason})"
        )
        return
    await notify_document_uploaded(document)

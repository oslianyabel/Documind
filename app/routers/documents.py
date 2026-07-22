import asyncio
import traceback
from pathlib import Path
from typing import Annotated

import anyio
from arq.connections import ArqRedis
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from openai import OpenAIError
from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DocumentNotFoundError, DocumindError
from app.core.queue import get_queue_pool
from app.db.database import async_session_maker, get_session
from app.db.models import Document, DocumentStatus, UploadOutcome
from app.schemas.documents import (
    DocumentFilters,
    DocumentListResponse,
    DocumentResponse,
    DocumentSummaryResponse,
)
from app.schemas.uploads import UploadBatchResponse, UploadItemResult
from app.services.document_ingestion import (
    DocumentUpload,
    ensure_document_summary,
    record_upload,
    register_document,
)
from app.services.storage import delete_document_files
from app.worker import INGEST_DOCUMENT_JOB

router = APIRouter(prefix="/documents", tags=["documents"])
# Registered WITHOUT the X-API-Key dependency (see main.py): file downloads
# must be reachable with a plain link (no custom headers).
public_router = APIRouter(prefix="/documents", tags=["documents"])

PDF_MIME_TYPE = "application/pdf"

SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueuePoolDep = Annotated[ArqRedis, Depends(get_queue_pool)]


async def _get_active_document(session: AsyncSession, name: str) -> Document:
    result = await session.execute(
        select(Document).where(Document.name == name, Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise DocumentNotFoundError(name)
    return document


async def _register_one_upload(
    queue_pool: ArqRedis, upload: DocumentUpload
) -> UploadItemResult:
    """Register a single file with its own DB session (parallel-safe).

    Every path leaves an upload_history row: 'skipped_duplicate', 'failed'
    (with traceback) or 'processing' (closed later by the ingestion worker).
    """
    async with async_session_maker() as session:
        try:
            document, created = await register_document(session, upload)
        except (DocumindError, SQLAlchemyError, OSError):
            await session.rollback()
            await record_upload(
                session,
                original_filename=upload.original_filename,
                document_name=upload.name,
                sha256=None,
                outcome=UploadOutcome.FAILED,
                error_traceback=traceback.format_exc(),
            )
            detail = traceback.format_exc(limit=0).strip().splitlines()[-1]
            return UploadItemResult(
                filename=upload.original_filename,
                outcome=UploadOutcome.FAILED,
                detail=detail,
            )

        if not created:
            # Same content already exists: nothing is re-embedded.
            await record_upload(
                session,
                original_filename=upload.original_filename,
                document_name=document.name,
                sha256=document.sha256,
                outcome=UploadOutcome.SKIPPED_DUPLICATE,
                document_id=document.id,
            )
            return UploadItemResult(
                filename=upload.original_filename,
                outcome=UploadOutcome.SKIPPED_DUPLICATE,
                detail=f"El contenido ya existe como '{document.name}'",
                document=DocumentResponse.model_validate(document),
            )

        entry = await record_upload(
            session,
            original_filename=upload.original_filename,
            document_name=document.name,
            sha256=document.sha256,
            outcome=UploadOutcome.PROCESSING,
            document_id=document.id,
        )
        await queue_pool.enqueue_job(INGEST_DOCUMENT_JOB, str(document.id), str(entry.id))
        return UploadItemResult(
            filename=upload.original_filename,
            outcome=UploadOutcome.PROCESSING,
            document=DocumentResponse.model_validate(document),
        )


@router.post("", response_model=UploadBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    queue_pool: QueuePoolDep,
    files: Annotated[list[UploadFile], File(description="Documentos PDF a indexar")],
    name: Annotated[str | None, Form(max_length=255)] = None,
    publication_year: Annotated[int | None, Form(ge=0, le=3000)] = None,
    author: Annotated[str | None, Form(max_length=255)] = None,
    description: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form(max_length=128)] = None,
    language: Annotated[str | None, Form(max_length=64)] = None,
    cover_image: Annotated[UploadFile | None, File(description="Imagen de portada")] = None,
) -> UploadBatchResponse:
    """Upload one or many PDFs; each file is registered in parallel.

    `name` and `cover_image` only apply when a single file is uploaded; the
    shared metadata fields (author, category, ...) apply to every file.
    """
    single_file = len(files) == 1
    cover_filename = cover_image.filename if single_file and cover_image is not None else None
    cover_content = await cover_image.read() if single_file and cover_image is not None else None

    uploads: list[DocumentUpload] = []
    for file in files:
        original_filename = file.filename or "document.pdf"
        is_pdf = (
            file.content_type == PDF_MIME_TYPE or original_filename.lower().endswith(".pdf")
        )
        uploads.append(
            DocumentUpload(
                name=(name if single_file and name else Path(original_filename).stem),
                original_filename=original_filename,
                mime_type=PDF_MIME_TYPE if is_pdf else (file.content_type or "unknown"),
                content=await file.read() if is_pdf else b"",
                cover_filename=cover_filename,
                cover_content=cover_content,
                publication_year=publication_year,
                author=author,
                description=description,
                category=category,
                language=language,
            )
        )

    async def handle(upload: DocumentUpload) -> UploadItemResult:
        if upload.mime_type != PDF_MIME_TYPE:
            async with async_session_maker() as session:
                await record_upload(
                    session,
                    original_filename=upload.original_filename,
                    document_name=upload.name,
                    sha256=None,
                    outcome=UploadOutcome.FAILED,
                    error_traceback="InvalidDocumentError: Only PDF documents are supported",
                )
            return UploadItemResult(
                filename=upload.original_filename,
                outcome=UploadOutcome.FAILED,
                detail="Solo se admiten documentos PDF",
            )
        return await _register_one_upload(queue_pool, upload)

    items = await asyncio.gather(*(handle(upload) for upload in uploads))
    return UploadBatchResponse(items=list(items))


def _build_filter_conditions(filters: DocumentFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Document.deleted_at.is_(None)]
    if filters.name is not None:
        conditions.append(Document.name.ilike(f"%{filters.name}%"))
    if filters.status is not None:
        conditions.append(Document.status == filters.status.value)
    if filters.min_pages is not None:
        conditions.append(Document.page_count >= filters.min_pages)
    if filters.max_pages is not None:
        conditions.append(Document.page_count <= filters.max_pages)
    if filters.min_chunks is not None:
        conditions.append(Document.chunk_count >= filters.min_chunks)
    if filters.max_chunks is not None:
        conditions.append(Document.chunk_count <= filters.max_chunks)
    if filters.min_size_bytes is not None:
        conditions.append(Document.size_bytes >= filters.min_size_bytes)
    if filters.max_size_bytes is not None:
        conditions.append(Document.size_bytes <= filters.max_size_bytes)
    if filters.uploaded_from is not None:
        conditions.append(Document.created_at >= filters.uploaded_from)
    if filters.uploaded_to is not None:
        conditions.append(Document.created_at <= filters.uploaded_to)
    if filters.summary is not None:
        conditions.append(Document.summary.ilike(f"%{filters.summary}%"))
    if filters.publication_year is not None:
        conditions.append(Document.publication_year == filters.publication_year)
    if filters.author is not None:
        conditions.append(Document.author.ilike(f"%{filters.author}%"))
    if filters.description is not None:
        conditions.append(Document.description.ilike(f"%{filters.description}%"))
    if filters.category is not None:
        conditions.append(Document.category.ilike(filters.category))
    if filters.language is not None:
        conditions.append(Document.language.ilike(filters.language))
    if filters.has_cover_image is True:
        conditions.append(Document.cover_image_path.is_not(None))
    if filters.has_cover_image is False:
        conditions.append(Document.cover_image_path.is_(None))
    if filters.min_search_hits is not None:
        conditions.append(Document.search_hit_count >= filters.min_search_hits)
    if filters.max_search_hits is not None:
        conditions.append(Document.search_hit_count <= filters.max_search_hits)
    return conditions


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    session: SessionDep, filters: Annotated[DocumentFilters, Query()]
) -> DocumentListResponse:
    conditions = _build_filter_conditions(filters)
    total = await session.scalar(
        select(func.count()).select_from(Document).where(and_(*conditions))
    )
    result = await session.execute(
        select(Document)
        .where(and_(*conditions))
        .order_by(Document.created_at.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    )
    documents = result.scalars().all()
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        total=total or 0,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{name}", response_model=DocumentResponse)
async def get_document(session: SessionDep, name: str) -> Document:
    return await _get_active_document(session, name)


@router.post("/{name}/summary", response_model=DocumentSummaryResponse)
async def ensure_summary(session: SessionDep, name: str) -> DocumentSummaryResponse:
    """Verify the document's AI summary exists; generate and persist it if not.

    Returns generated_now=False when the summary already existed.
    """
    document = await _get_active_document(session, name)
    if document.status == DocumentStatus.PROCESSING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El documento aún se está ingestando; el resumen llegará al terminar",
        )
    try:
        summary, generated_now = await ensure_document_summary(session, document)
    except OpenAIError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo generar el resumen (fallo del proveedor de IA)",
        ) from error
    return DocumentSummaryResponse(
        document_name=document.name, summary=summary, generated_now=generated_now
    )


@public_router.get("/{name}/download")
async def download_document(session: SessionDep, name: str) -> FileResponse:
    document = await _get_active_document(session, name)
    path = Path(document.storage_path)
    if not await anyio.Path(path).is_file():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored file is missing on disk",
        )
    return FileResponse(
        path, filename=document.original_filename, media_type=document.mime_type
    )


@public_router.get("/{name}/cover")
async def download_cover_image(session: SessionDep, name: str) -> FileResponse:
    document = await _get_active_document(session, name)
    has_cover_file = document.cover_image_path is not None and await anyio.Path(
        document.cover_image_path
    ).is_file()
    if not has_cover_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document has no cover image"
        )
    return FileResponse(Path(document.cover_image_path))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(session: SessionDep, name: str) -> None:
    """Permanently delete the document, its chunks and its files.

    A hard delete keeps the vector index clean: soft-deleted chunks would stay
    in the HNSW graph and keep competing (then get filtered out) in every
    search. Chunks are removed by the ON DELETE CASCADE foreign key; the
    upload-history rows survive with document_id set to NULL (audit trail).
    """
    document = await _get_active_document(session, name)
    storage_path = document.storage_path
    cover_path = document.cover_image_path
    await session.delete(document)
    await session.commit()
    # Files are removed only after the row is gone, so a failed unlink can never
    # leave a dangling DB row pointing at a missing file.
    await delete_document_files(storage_path, cover_path)

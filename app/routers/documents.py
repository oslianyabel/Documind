from datetime import UTC, datetime
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
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DocumentNotFoundError, InvalidDocumentError
from app.core.queue import get_queue_pool
from app.db.database import get_session
from app.db.models import Document
from app.schemas.documents import DocumentFilters, DocumentListResponse, DocumentResponse
from app.services.document_ingestion import DocumentUpload, register_document
from app.worker import INGEST_DOCUMENT_JOB

router = APIRouter(prefix="/documents", tags=["documents"])

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


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    session: SessionDep,
    queue_pool: QueuePoolDep,
    response: Response,
    file: Annotated[UploadFile, File(description="Documento PDF a indexar")],
    name: Annotated[str | None, Form(max_length=255)] = None,
    publication_year: Annotated[int | None, Form(ge=0, le=3000)] = None,
    author: Annotated[str | None, Form(max_length=255)] = None,
    description: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form(max_length=128)] = None,
    language: Annotated[str | None, Form(max_length=64)] = None,
    cover_image: Annotated[UploadFile | None, File(description="Imagen de portada")] = None,
) -> Document:
    original_filename = file.filename or "document.pdf"
    is_pdf = file.content_type == PDF_MIME_TYPE or original_filename.lower().endswith(".pdf")
    if not is_pdf:
        raise InvalidDocumentError("Only PDF documents are supported")

    upload = DocumentUpload(
        name=name or Path(original_filename).stem,
        original_filename=original_filename,
        mime_type=PDF_MIME_TYPE,
        content=await file.read(),
        cover_filename=cover_image.filename if cover_image is not None else None,
        cover_content=await cover_image.read() if cover_image is not None else None,
        publication_year=publication_year,
        author=author,
        description=description,
        category=category,
        language=language,
    )
    # Fast phase only: the heavy work (parse, embeddings, summary) runs in the
    # arq worker; the client polls GET /documents/{name} until status='ready'.
    document, created = await register_document(session, upload)
    if created:
        await queue_pool.enqueue_job(INGEST_DOCUMENT_JOB, str(document.id))
    else:
        # Same content already exists: return the existing document (200), not
        # a freshly-accepted one (202). Nothing is re-embedded.
        response.status_code = status.HTTP_200_OK
    return document


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


@router.get("/{name}/download")
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


@router.get("/{name}/cover")
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
    document = await _get_active_document(session, name)
    document.deleted_at = datetime.now(UTC)
    await session.commit()

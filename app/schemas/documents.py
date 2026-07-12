import uuid
from datetime import datetime
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.db.models import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    original_filename: str
    mime_type: str
    sha256: str
    size_bytes: int
    status: DocumentStatus
    # 0 while status is 'processing'; filled in by the ingestion worker.
    page_count: int
    chunk_count: int
    summary: str | None
    # Whether the AI summary was generated successfully during ingestion (or
    # later via POST /documents/{name}/summary).
    summary_generated: bool
    embedding_tokens_used: int
    publication_year: int | None
    author: str | None
    description: str | None
    category: str | None
    language: str | None
    has_cover_image: bool
    search_hit_count: int
    created_at: datetime

    @computed_field
    @property
    def download_url(self) -> str:
        """API-relative path to download the original file.

        Relative to the API root so it works behind a reverse proxy; the
        download endpoint requires the X-API-Key header.
        """
        return f"/documents/{quote(self.name)}/download"


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentSummaryResponse(BaseModel):
    document_name: str
    summary: str
    # True when this request generated the summary; False when it already existed.
    generated_now: bool


class DocumentFilters(BaseModel):
    """Query-string filters for the document listing endpoint."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    status: DocumentStatus | None = None
    min_pages: int | None = Field(default=None, ge=0)
    max_pages: int | None = Field(default=None, ge=0)
    min_chunks: int | None = Field(default=None, ge=0)
    max_chunks: int | None = Field(default=None, ge=0)
    min_size_bytes: int | None = Field(default=None, ge=0)
    max_size_bytes: int | None = Field(default=None, ge=0)
    uploaded_from: datetime | None = None
    uploaded_to: datetime | None = None
    summary: str | None = None
    publication_year: int | None = None
    author: str | None = None
    description: str | None = None
    category: str | None = None
    language: str | None = None
    has_cover_image: bool | None = None
    min_search_hits: int | None = Field(default=None, ge=0)
    max_search_hits: int | None = Field(default=None, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

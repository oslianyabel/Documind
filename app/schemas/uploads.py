import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import UploadOutcome
from app.schemas.documents import DocumentResponse


class UploadItemResult(BaseModel):
    """Per-file result of a (multi-file) upload request."""

    filename: str
    outcome: UploadOutcome
    detail: str | None = None
    document: DocumentResponse | None = None


class UploadBatchResponse(BaseModel):
    items: list[UploadItemResult]


class UploadHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    document_name: str | None
    sha256: str | None
    outcome: UploadOutcome
    error_traceback: str | None
    document_id: uuid.UUID | None
    created_at: datetime
    finished_at: datetime | None


class UploadHistoryResponse(BaseModel):
    items: list[UploadHistoryEntry]
    total: int
    limit: int
    offset: int

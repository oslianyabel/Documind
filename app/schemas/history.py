import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SearchHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_text: str
    response: dict
    embedding_tokens: int
    duration_ms: float
    passed_validation: bool
    created_at: datetime


class SearchHistoryResponse(BaseModel):
    items: list[SearchHistoryEntry]
    total: int
    limit: int
    offset: int

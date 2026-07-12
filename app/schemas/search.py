from pydantic import BaseModel, Field

from app.schemas.documents import DocumentResponse


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class SearchChunkResult(BaseModel):
    document_name: str
    start_page: int
    start_line: int
    end_page: int
    end_line: int
    text: str
    similarity: float


class SearchMetadata(BaseModel):
    embedding_tokens: int
    total_time_ms: float


class SearchResponse(BaseModel):
    chunks: list[SearchChunkResult]
    documents: list[DocumentResponse]
    # Answer produced by the document-grounded agent; null when the answer is
    # not contained in the documents (NOT_FOUND) or the query was out of scope.
    answer: str | None = None
    # False when the scope-validation agent rejected the query (no search ran).
    in_scope: bool = True
    metadata: SearchMetadata

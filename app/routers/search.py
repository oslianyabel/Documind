import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.notifications import notify_semantic_search
from app.db.database import get_session
from app.db.models import Chunk, Document, DocumentStatus, SearchHistory
from app.schemas.documents import DocumentResponse
from app.schemas.search import SearchChunkResult, SearchMetadata, SearchRequest, SearchResponse
from app.services.embeddings import embed_query

router = APIRouter(prefix="/search", tags=["search"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=SearchResponse)
async def semantic_search(
    payload: SearchRequest, session: SessionDep, background_tasks: BackgroundTasks
) -> SearchResponse:
    started_at = time.perf_counter()

    embedding_result = await embed_query(payload.query)
    query_vector = embedding_result.vectors[0]

    # Cosine distance over every chunk of every active, fully ingested
    # document; lower is closer. Documents still processing never surface.
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    result = await session.execute(
        select(Chunk, Document, distance)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.READY.value,
        )
        .order_by(distance)
        .limit(settings.search_top_k)
    )
    rows = result.all()

    chunk_results: list[SearchChunkResult] = []
    matched_documents: list[Document] = []
    seen_document_ids: set = set()
    for chunk, document, chunk_distance in rows:
        chunk_results.append(
            SearchChunkResult(
                document_name=document.name,
                start_page=chunk.start_page,
                start_line=chunk.start_line,
                end_page=chunk.end_page,
                end_line=chunk.end_line,
                text=chunk.content,
                similarity=round(1.0 - float(chunk_distance), 6),
            )
        )
        if document.id not in seen_document_ids:
            seen_document_ids.add(document.id)
            matched_documents.append(document)

    if seen_document_ids:
        await session.execute(
            update(Document)
            .where(Document.id.in_(seen_document_ids))
            .values(search_hit_count=Document.search_hit_count + 1)
        )

    total_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response = SearchResponse(
        chunks=chunk_results,
        documents=[DocumentResponse.model_validate(document) for document in matched_documents],
        metadata=SearchMetadata(
            embedding_tokens=embedding_result.total_tokens, total_time_ms=total_time_ms
        ),
    )

    # Audit trail: archive the query together with the exact response served.
    session.add(
        SearchHistory(
            query_text=payload.query,
            response=response.model_dump(mode="json"),
            embedding_tokens=embedding_result.total_tokens,
            duration_ms=total_time_ms,
        )
    )
    await session.commit()

    background_tasks.add_task(
        notify_semantic_search,
        query=payload.query,
        chunk_count=len(chunk_results),
        document_names=[document.name for document in matched_documents],
        embedding_tokens=embedding_result.total_tokens,
        duration_ms=total_time_ms,
    )
    return response

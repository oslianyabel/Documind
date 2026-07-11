from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.db.models import SearchHistory
from app.schemas.history import SearchHistoryEntry, SearchHistoryResponse

router = APIRouter(prefix="/search/history", tags=["search-history"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=SearchHistoryResponse)
async def list_search_history(
    session: SessionDep,
    from_date: Annotated[datetime | None, Query(description="Inicio del rango (inclusive)")] = None,
    to_date: Annotated[datetime | None, Query(description="Fin del rango (inclusive)")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchHistoryResponse:
    conditions: list[ColumnElement[bool]] = []
    if from_date is not None:
        conditions.append(SearchHistory.created_at >= from_date)
    if to_date is not None:
        conditions.append(SearchHistory.created_at <= to_date)
    where_clause = and_(*conditions) if conditions else None

    count_stmt = select(func.count()).select_from(SearchHistory)
    list_stmt = (
        select(SearchHistory)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
        list_stmt = list_stmt.where(where_clause)

    total = await session.scalar(count_stmt)
    entries = (await session.execute(list_stmt)).scalars().all()
    return SearchHistoryResponse(
        items=[SearchHistoryEntry.model_validate(entry) for entry in entries],
        total=total or 0,
        limit=limit,
        offset=offset,
    )

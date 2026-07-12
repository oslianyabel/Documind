from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.db.models import UploadHistory, UploadOutcome
from app.schemas.uploads import UploadHistoryEntry, UploadHistoryResponse

router = APIRouter(prefix="/uploads", tags=["uploads"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=UploadHistoryResponse)
async def list_upload_history(
    session: SessionDep,
    outcome: Annotated[UploadOutcome | None, Query()] = None,
    from_date: Annotated[datetime | None, Query(description="Inicio del rango (inclusive)")] = None,
    to_date: Annotated[datetime | None, Query(description="Fin del rango (inclusive)")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UploadHistoryResponse:
    conditions: list[ColumnElement[bool]] = []
    if outcome is not None:
        conditions.append(UploadHistory.outcome == outcome.value)
    if from_date is not None:
        conditions.append(UploadHistory.created_at >= from_date)
    if to_date is not None:
        conditions.append(UploadHistory.created_at <= to_date)
    where_clause = and_(*conditions) if conditions else None

    count_stmt = select(func.count()).select_from(UploadHistory)
    list_stmt = (
        select(UploadHistory)
        .order_by(UploadHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
        list_stmt = list_stmt.where(where_clause)

    total = await session.scalar(count_stmt)
    entries = (await session.execute(list_stmt)).scalars().all()
    return UploadHistoryResponse(
        items=[UploadHistoryEntry.model_validate(entry) for entry in entries],
        total=total or 0,
        limit=limit,
        offset=offset,
    )

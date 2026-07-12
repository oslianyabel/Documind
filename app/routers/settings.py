from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.settings import SearchScopeResponse, SearchScopeUpdate
from app.services.app_settings import get_search_scope_prompt, set_search_scope_prompt

router = APIRouter(prefix="/settings", tags=["settings"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/search-scope", response_model=SearchScopeResponse)
async def read_search_scope(session: SessionDep) -> SearchScopeResponse:
    return SearchScopeResponse(prompt=await get_search_scope_prompt(session))


@router.put("/search-scope", response_model=SearchScopeResponse)
async def update_search_scope(
    payload: SearchScopeUpdate, session: SessionDep
) -> SearchScopeResponse:
    """Persist the prompt that defines which search queries are in scope.

    An empty prompt disables scope validation (every query is allowed).
    """
    await set_search_scope_prompt(session, payload.prompt)
    return SearchScopeResponse(prompt=payload.prompt)

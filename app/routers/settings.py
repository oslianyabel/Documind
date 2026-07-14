from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.settings import (
    AnswerPromptResponse,
    AnswerPromptUpdate,
    SearchScopeResponse,
    SearchScopeUpdate,
)
from app.services.agents import ANSWER_PROMPT, validate_answer_prompt
from app.services.app_settings import (
    get_answer_prompt,
    get_search_scope_prompt,
    set_answer_prompt,
    set_search_scope_prompt,
)

router = APIRouter(prefix="/settings", tags=["settings"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _answer_prompt_response(stored: str | None) -> AnswerPromptResponse:
    if stored and stored.strip():
        return AnswerPromptResponse(prompt=stored, is_default=False)
    return AnswerPromptResponse(prompt=ANSWER_PROMPT, is_default=True)


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


@router.get("/answer-prompt", response_model=AnswerPromptResponse)
async def read_answer_prompt(session: SessionDep) -> AnswerPromptResponse:
    """Return the template used by the document-grounded answer agent.

    is_default=True means no override is set and the built-in default is shown.
    """
    return _answer_prompt_response(await get_answer_prompt(session))


@router.put("/answer-prompt", response_model=AnswerPromptResponse)
async def update_answer_prompt(
    payload: AnswerPromptUpdate, session: SessionDep
) -> AnswerPromptResponse:
    """Persist the answer-agent template. Empty resets to the built-in default.

    The template must contain the {context} and {query} placeholders; an invalid
    template is rejected with 422 rather than silently breaking search.
    """
    if payload.prompt.strip():
        try:
            validate_answer_prompt(payload.prompt)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error
    await set_answer_prompt(session, payload.prompt)
    return _answer_prompt_response(payload.prompt)

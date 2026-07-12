from pydantic import BaseModel, Field


class SearchScopeResponse(BaseModel):
    # None/empty means scope validation is disabled (every query is allowed).
    prompt: str | None


class SearchScopeUpdate(BaseModel):
    prompt: str = Field(max_length=8000)

from pydantic import BaseModel, Field


class SearchScopeResponse(BaseModel):
    # None/empty means scope validation is disabled (every query is allowed).
    prompt: str | None


class SearchScopeUpdate(BaseModel):
    prompt: str = Field(max_length=8000)


class AnswerPromptResponse(BaseModel):
    # Effective template in use, with {context}/{query} placeholders.
    prompt: str
    # True when no override is set and the built-in default is being used.
    is_default: bool


class AnswerPromptUpdate(BaseModel):
    # Empty string resets to the built-in default. Must contain {context} and
    # {query}; the router validates the template before persisting it.
    prompt: str = Field(max_length=8000)

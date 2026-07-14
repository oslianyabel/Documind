"""LLM agents used by the semantic-search endpoint.

- answer_from_documents: answers a query using ONLY the provided document
  fragments; returns NOT_FOUND when the answer is not contained in them.
- is_query_in_scope: validates a client query against the persisted
  search-scope prompt, returning True (in scope) or False (out of scope).
"""

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI, OpenAIError

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

ANSWER_NOT_FOUND = "NOT_FOUND"

# Placeholders the answer template MUST contain: {context} is replaced with the
# retrieved fragments and {query} with the client's query.
ANSWER_CONTEXT_PLACEHOLDER = "{context}"
ANSWER_QUERY_PLACEHOLDER = "{query}"

# Built-in default. The operator can override it at runtime via
# /settings/answer-prompt (persisted); an empty override falls back to this.
ANSWER_PROMPT = (
    "Eres un asistente que responde preguntas basándose EXCLUSIVAMENTE en los "
    "fragmentos de documentos proporcionados. Reglas estrictas:\n"
    "1. Usa únicamente la información contenida en los fragmentos; no uses "
    "conocimiento externo ni hagas suposiciones.\n"
    "2. Si la respuesta a la consulta no está contenida en los fragmentos, "
    f"responde exactamente: {ANSWER_NOT_FOUND}\n"
    "3. Si la respuesta sí está contenida, respóndela de forma clara y concisa "
    "en el idioma de la consulta, citando el documento de origen entre "
    "corchetes cuando aporte valor.\n\n"
    "<fragmentos>\n{context}\n</fragmentos>\n\n"
    "<consulta>\n{query}\n</consulta>"
)


def validate_answer_prompt(template: str) -> None:
    """Ensure a custom answer template is usable; raise ValueError otherwise.

    It must contain both {context} and {query}, and must not carry any other
    unescaped braces (which would make str.format raise at query time).
    """
    for placeholder in (ANSWER_CONTEXT_PLACEHOLDER, ANSWER_QUERY_PLACEHOLDER):
        if placeholder not in template:
            raise ValueError(f"La plantilla debe incluir {placeholder}.")
    try:
        template.format(context="", query="")
    except (KeyError, IndexError, ValueError) as error:
        raise ValueError(
            "La plantilla tiene llaves { } no válidas; usa solo {context} y "
            "{query} (escribe {{ }} para llaves literales)."
        ) from error

SCOPE_PROMPT = (
    "Eres un validador de consultas para un buscador semántico de documentos. "
    "El operador del sistema definió el siguiente alcance de búsquedas:\n"
    "<alcance>\n{scope}\n</alcance>\n\n"
    "Evalúa si la consulta del cliente está dentro de ese alcance. Responde "
    "exactamente una palabra: TRUE si está dentro del alcance, FALSE si está "
    "fuera.\n\n<consulta>\n{query}\n</consulta>"
)


@dataclass(frozen=True)
class DocumentFragment:
    document_name: str
    text: str


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=settings.agent_timeout_seconds
        )
    return _client


def build_answer_context(fragments: list[DocumentFragment]) -> str:
    return "\n\n".join(
        f"[documento: {fragment.document_name}]\n{fragment.text}" for fragment in fragments
    )


def parse_scope_verdict(raw_answer: str) -> bool | None:
    """Map the model output to True/False; None when it can't be parsed."""
    normalized = raw_answer.strip().strip(".").upper()
    if normalized.startswith("TRUE"):
        return True
    if normalized.startswith("FALSE"):
        return False
    return None


async def answer_from_documents(
    query: str,
    fragments: list[DocumentFragment],
    prompt_template: str | None = None,
) -> str | None:
    """Answer the query using only the fragments; None when not answerable.

    prompt_template is the operator-configured template (from settings); when
    empty or malformed it falls back to the built-in ANSWER_PROMPT. It must
    carry {context} and {query} placeholders.

    Returns None both when the agent replies NOT_FOUND and when the agent call
    itself fails — an unavailable agent must never break the search endpoint.
    """
    if not fragments:
        return None
    template = prompt_template if prompt_template and prompt_template.strip() else ANSWER_PROMPT
    context = build_answer_context(fragments)
    try:
        prompt = template.format(context=context, query=query)
    except (KeyError, IndexError, ValueError):
        # A stored template should have passed validation, but never let a bad
        # one break search: fall back to the built-in default.
        logger.exception("Answer template is malformed; using the default prompt")
        prompt = ANSWER_PROMPT.format(context=context, query=query)
    try:
        response = await _get_client().chat.completions.create(
            model=settings.agent_model,
            max_completion_tokens=settings.answer_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except OpenAIError:
        logger.exception("Answer agent call failed; returning no answer")
        return None
    answer = (response.choices[0].message.content or "").strip()
    if not answer or answer.upper().startswith(ANSWER_NOT_FOUND):
        return None
    return answer


async def is_query_in_scope(query: str, scope_prompt: str | None) -> bool:
    """True when the query is within the configured search scope.

    Fail-open by design: with no scope configured, an unparseable verdict or
    an agent failure, the query is allowed (validation must not break search).
    """
    if not scope_prompt or not scope_prompt.strip():
        return True
    prompt = SCOPE_PROMPT.format(scope=scope_prompt.strip(), query=query)
    try:
        response = await _get_client().chat.completions.create(
            model=settings.agent_model,
            max_completion_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
    except OpenAIError:
        logger.exception("Scope agent call failed; allowing the query")
        return True
    verdict = parse_scope_verdict(response.choices[0].message.content or "")
    if verdict is None:
        logger.warning("Scope agent returned an unparseable verdict; allowing the query")
        return True
    return verdict

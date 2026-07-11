from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None

SUMMARY_PROMPT = (
    "Genera un resumen conciso (3 a 6 oraciones) del siguiente documento. "
    "Escribe el resumen en el mismo idioma del documento y no agregues "
    "introducciones ni comentarios, solo el resumen.\n\n<documento>\n{text}\n</documento>"
)


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=settings.summary_timeout_seconds
        )
    return _client


async def generate_summary(document_text: str) -> str:
    """Generate an AI summary of the document using the configured OpenAI model."""
    client = _get_client()
    truncated_text = document_text[: settings.summary_max_input_chars]
    response = await client.chat.completions.create(
        model=settings.summary_model,
        max_completion_tokens=settings.summary_max_tokens,
        messages=[{"role": "user", "content": SUMMARY_PROMPT.format(text=truncated_text)}],
    )
    return (response.choices[0].message.content or "").strip()

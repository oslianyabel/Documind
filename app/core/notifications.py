import logging
from typing import TYPE_CHECKING

import httpx

from app.config import settings

if TYPE_CHECKING:
    from app.db.models import Document

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"
NOTIFICATION_TIMEOUT_SECONDS = 5.0
MESSAGE_PREFIX = "[Launch-Intelligence]"
MAX_MESSAGE_LENGTH = 3900


async def _send_message(text: str) -> None:
    """Deliver a plain-text message to the dev via Telegram, if configured.

    Failures are swallowed: notifications must never break the request that
    triggered them.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    url = f"{TELEGRAM_API_URL}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": f"{MESSAGE_PREFIX} {text}"[:MAX_MESSAGE_LENGTH],
    }
    try:
        async with httpx.AsyncClient(timeout=NOTIFICATION_TIMEOUT_SECONDS) as client:
            await client.post(url, json=payload)
    except httpx.HTTPError:
        logger.warning("Failed to deliver Telegram notification")


async def notify_critical_error(message: str) -> None:
    await _send_message(f"⚠️ {message}")


def _format_optional(label: str, value: object | None) -> str | None:
    return f"{label}: {value}" if value is not None else None


async def notify_document_uploaded(document: "Document") -> None:
    """Notify the dev of a newly ingested document and its details."""
    lines = [
        "📄 Documento subido",
        f"Nombre: {document.name}",
        f"Archivo: {document.original_filename}",
        f"Páginas: {document.page_count}",
        f"Chunks: {document.chunk_count}",
        f"Tamaño: {document.size_bytes} bytes",
        f"Tokens de embeddings: {document.embedding_tokens_used}",
    ]
    optional_fields = [
        _format_optional("Autor", document.author),
        _format_optional("Categoría", document.category),
        _format_optional("Idioma", document.language),
        _format_optional("Año de publicación", document.publication_year),
    ]
    lines.extend(field for field in optional_fields if field is not None)
    await _send_message("\n".join(lines))


async def notify_semantic_search(
    *,
    query: str,
    chunk_count: int,
    document_names: list[str],
    embedding_tokens: int,
    duration_ms: float,
) -> None:
    """Notify the dev of a semantic search and a summary of its result."""
    documents_line = ", ".join(document_names) if document_names else "(sin coincidencias)"
    lines = [
        "🔎 Búsqueda semántica",
        f"Consulta: {query}",
        f"Chunks devueltos: {chunk_count}",
        f"Documentos: {documents_line}",
        f"Tokens de la consulta: {embedding_tokens}",
        f"Tiempo total: {duration_ms} ms",
    ]
    await _send_message("\n".join(lines))

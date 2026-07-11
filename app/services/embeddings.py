import hashlib
import json
import logging
from dataclasses import dataclass

import redis.asyncio as aioredis
from openai import AsyncOpenAI
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_cache: aioredis.Redis | None = None

CACHE_KEY_PREFIX = "emb:query:"


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=settings.embedding_timeout_seconds
        )
    return _client


def _get_cache() -> aioredis.Redis | None:
    global _cache
    if not settings.embedding_cache_enabled:
        return None
    if _cache is None:
        _cache = aioredis.from_url(settings.redis_url)
    return _cache


def _cache_key(query: str) -> str:
    # Keyed on the exact query text + model so a model switch never returns a
    # stale vector of the wrong dimensionality/space.
    digest = hashlib.sha256(f"{settings.embedding_model}\x00{query}".encode()).hexdigest()
    return f"{CACHE_KEY_PREFIX}{digest}"


@dataclass(frozen=True)
class EmbeddingBatchResult:
    vectors: list[list[float]]
    total_tokens: int


async def embed_texts(texts: list[str]) -> EmbeddingBatchResult:
    """Convert texts to embeddings, returning vectors and total tokens consumed.

    Used for document ingestion (chunks are embedded once and persisted in
    Postgres), so it is intentionally uncached.
    """
    client = _get_client()
    vectors: list[list[float]] = []
    total_tokens = 0
    batch_size = settings.embedding_batch_size
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = await client.embeddings.create(model=settings.embedding_model, input=batch)
        vectors.extend(item.embedding for item in response.data)
        total_tokens += response.usage.total_tokens
    return EmbeddingBatchResult(vectors=vectors, total_tokens=total_tokens)


async def embed_query(query: str) -> EmbeddingBatchResult:
    """Embed a single search query, backed by a Redis cache.

    A cache hit returns the stored vector with total_tokens=0 (no OpenAI call).
    Any cache failure falls back to a live embedding — the cache never breaks
    search.
    """
    cache = _get_cache()
    key = _cache_key(query)

    if cache is not None:
        try:
            cached = await cache.get(key)
            if cached is not None:
                return EmbeddingBatchResult(vectors=[json.loads(cached)], total_tokens=0)
        except (RedisError, OSError, json.JSONDecodeError):
            logger.warning("Embedding cache read failed; falling back to OpenAI")

    result = await embed_texts([query])

    if cache is not None:
        try:
            await cache.set(
                key,
                json.dumps(result.vectors[0]),
                ex=settings.embedding_cache_ttl_seconds,
            )
        except (RedisError, OSError):
            logger.warning("Embedding cache write failed")

    return result

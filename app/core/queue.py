from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from app.config import settings


async def create_queue_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


def get_queue_pool(request: Request) -> ArqRedis:
    """FastAPI dependency: the arq pool created during app lifespan."""
    return request.app.state.queue_pool

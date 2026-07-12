from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=30,
    connect_args={"timeout": 30},
)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def init_database() -> None:
    """Ensure the pgvector extension, all tables and idempotent migrations exist."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Migration for databases created before async ingestion existed:
        # documents ingested back then are complete, hence DEFAULT 'ready'.
        # No-op on fresh databases (create_all already added the column).
        await conn.execute(
            text(
                "ALTER TABLE documents "
                "ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'ready'"
            )
        )
        # Migration for databases created before scope validation existed:
        # historical searches were never rejected, hence DEFAULT true.
        await conn.execute(
            text(
                "ALTER TABLE search_history "
                "ADD COLUMN IF NOT EXISTS passed_validation BOOLEAN NOT NULL DEFAULT true"
            )
        )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session

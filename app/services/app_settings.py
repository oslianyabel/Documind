from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting

SEARCH_SCOPE_PROMPT_KEY = "search_scope_prompt"


async def get_setting(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(AppSetting.value).where(AppSetting.key == key))
    return result.scalar_one_or_none()


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    statement = insert(AppSetting).values(key=key, value=value)
    statement = statement.on_conflict_do_update(
        index_elements=[AppSetting.key], set_={"value": value}
    )
    await session.execute(statement)
    await session.commit()


async def get_search_scope_prompt(session: AsyncSession) -> str | None:
    return await get_setting(session, SEARCH_SCOPE_PROMPT_KEY)


async def set_search_scope_prompt(session: AsyncSession, prompt: str) -> None:
    await set_setting(session, SEARCH_SCOPE_PROMPT_KEY, prompt)

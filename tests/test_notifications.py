import pytest

from app.core import notifications
from app.core.notifications import _format_optional


# uv run pytest -s tests/test_notifications.py::test_format_optional_present
def test_format_optional_present() -> None:
    assert _format_optional("Autor", "Borges") == "Autor: Borges"


# uv run pytest -s tests/test_notifications.py::test_format_optional_none_is_dropped
def test_format_optional_none_is_dropped() -> None:
    assert _format_optional("Autor", None) is None


# uv run pytest -s tests/test_notifications.py::test_notifications_noop_when_telegram_unconfigured
@pytest.mark.asyncio
async def test_notifications_noop_when_telegram_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Telegram credentials are unset in the test environment, so every
    # notification helper must return silently without attempting any network
    # call — a missing config must never break the triggering request.
    monkeypatch.setattr(notifications.settings, "telegram_bot_token", None)
    monkeypatch.setattr(notifications.settings, "telegram_chat_id", None)

    await notifications.notify_critical_error("boom")
    await notifications.notify_semantic_search(
        query="q",
        chunk_count=0,
        document_names=[],
        embedding_tokens=0,
        duration_ms=1.0,
    )

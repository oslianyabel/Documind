import pytest

from app.services import embeddings
from app.services.embeddings import CACHE_KEY_PREFIX, _cache_key, _get_cache


# uv run pytest -s tests/test_embeddings.py::test_cache_key_is_deterministic
def test_cache_key_is_deterministic() -> None:
    assert _cache_key("fallo ABS") == _cache_key("fallo ABS")
    assert _cache_key("fallo ABS").startswith(CACHE_KEY_PREFIX)


# uv run pytest -s tests/test_embeddings.py::test_cache_key_differs_per_query
def test_cache_key_differs_per_query() -> None:
    assert _cache_key("fallo ABS") != _cache_key("fallo airbag")


# uv run pytest -s tests/test_embeddings.py::test_cache_key_depends_on_model
def test_cache_key_depends_on_model(monkeypatch: pytest.MonkeyPatch) -> None:
    key_small = _cache_key("consulta")
    monkeypatch.setattr(embeddings.settings, "embedding_model", "text-embedding-3-large")
    assert _cache_key("consulta") != key_small


# uv run pytest -s tests/test_embeddings.py::test_cache_disabled_returns_no_client
def test_cache_disabled_returns_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "_cache", None)
    monkeypatch.setattr(embeddings.settings, "embedding_cache_enabled", False)
    assert _get_cache() is None

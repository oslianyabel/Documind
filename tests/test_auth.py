from app.core.auth import hash_api_key


# uv run pytest -s tests/test_auth.py::test_hash_api_key_is_deterministic
def test_hash_api_key_is_deterministic() -> None:
    assert hash_api_key("some-key") == hash_api_key("some-key")


# uv run pytest -s tests/test_auth.py::test_hash_api_key_differs_per_key
def test_hash_api_key_differs_per_key() -> None:
    assert hash_api_key("key-a") != hash_api_key("key-b")


# uv run pytest -s tests/test_auth.py::test_hash_api_key_is_sha256_hex
def test_hash_api_key_is_sha256_hex() -> None:
    hashed = hash_api_key("key")
    assert len(hashed) == 64
    assert all(character in "0123456789abcdef" for character in hashed)

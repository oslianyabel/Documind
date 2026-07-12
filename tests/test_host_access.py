import pytest

from app.core.host_access import is_ip_allowed, parse_allowlist, resolve_client_ip


# uv run pytest -s tests/test_host_access.py::test_parse_allowlist_star_allows_all
def test_parse_allowlist_star_allows_all() -> None:
    assert parse_allowlist("*") is None
    assert parse_allowlist("") is None
    assert parse_allowlist("  ") is None
    assert parse_allowlist("10.0.0.1, *") is None


# uv run pytest -s tests/test_host_access.py::test_parse_allowlist_ips_and_cidrs
def test_parse_allowlist_ips_and_cidrs() -> None:
    networks = parse_allowlist("203.0.113.5, 10.0.0.0/8")
    assert networks is not None
    assert len(networks) == 2


# uv run pytest -s tests/test_host_access.py::test_parse_allowlist_invalid_entry_raises
def test_parse_allowlist_invalid_entry_raises() -> None:
    with pytest.raises(ValueError):
        parse_allowlist("no-es-una-ip")


# uv run pytest -s tests/test_host_access.py::test_is_ip_allowed_matches_exact_and_cidr
def test_is_ip_allowed_matches_exact_and_cidr() -> None:
    networks = parse_allowlist("203.0.113.5, 10.0.0.0/8")
    assert is_ip_allowed("203.0.113.5", networks) is True
    assert is_ip_allowed("10.42.7.1", networks) is True
    assert is_ip_allowed("203.0.113.6", networks) is False
    assert is_ip_allowed("8.8.8.8", networks) is False


# uv run pytest -s tests/test_host_access.py::test_is_ip_allowed_edge_cases
def test_is_ip_allowed_edge_cases() -> None:
    networks = parse_allowlist("10.0.0.0/8")
    assert is_ip_allowed(None, networks) is False
    assert is_ip_allowed("garbage", networks) is False
    # Allow-all (None) accepts anything, even unknown peers.
    assert is_ip_allowed(None, None) is True
    assert is_ip_allowed("8.8.8.8", None) is True


# uv run pytest -s tests/test_host_access.py::test_resolve_client_ip_prefers_forwarded_for
def test_resolve_client_ip_prefers_forwarded_for() -> None:
    assert resolve_client_ip("172.18.0.4", "203.0.113.9, 172.18.0.4") == "203.0.113.9"
    assert resolve_client_ip("172.18.0.4", None) == "172.18.0.4"
    assert resolve_client_ip(None, None) is None

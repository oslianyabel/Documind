"""Client-host allowlist for the API.

API_ALLOWED_HOSTS is a comma-separated list of IPs and/or CIDR ranges
(e.g. "203.0.113.5, 10.0.0.0/8"). "*" (the default) allows every client.

This is a network-level convenience filter, not the authentication layer:
the X-API-Key requirement always applies. Behind the frontend proxy the real
client IP is taken from X-Forwarded-For (set by nginx); on the directly
exposed port that header could be forged by a malicious client, so do not
rely on the allowlist as the only protection there.
"""

import ipaddress

AllowedNetworks = list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None

ALLOW_ALL = "*"


def parse_allowlist(raw: str) -> AllowedNetworks:
    """Parse the env value into networks. None means 'allow every client'.

    Raises ValueError on malformed entries so the app fails fast at startup.
    """
    cleaned = raw.strip()
    if not cleaned or cleaned == ALLOW_ALL:
        return None
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for part in cleaned.split(","):
        entry = part.strip()
        if not entry:
            continue
        if entry == ALLOW_ALL:
            return None
        # A bare IP becomes a /32 (or /128) network automatically.
        networks.append(ipaddress.ip_network(entry, strict=False))
    return networks or None


def resolve_client_ip(client_host: str | None, forwarded_for: str | None) -> str | None:
    """Effective client IP: first X-Forwarded-For hop (set by the reverse
    proxy) when present, otherwise the direct peer address."""
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop
    return client_host


def is_ip_allowed(ip_raw: str | None, networks: AllowedNetworks) -> bool:
    if networks is None:
        return True
    if not ip_raw:
        return False
    try:
        ip = ipaddress.ip_address(ip_raw)
    except ValueError:
        return False
    return any(ip in network for network in networks)

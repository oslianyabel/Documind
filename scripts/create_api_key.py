"""Create a new API key for the Documind service.

Usage:
    uv run python scripts/create_api_key.py --name "client-name"

The plaintext key is printed ONCE; only its SHA-256 hash is stored.
"""

import argparse
import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth import hash_api_key  # noqa: E402
from app.db.database import async_session_maker, init_database  # noqa: E402
from app.db.models import ApiKey  # noqa: E402


async def create_api_key(name: str) -> str:
    await init_database()
    raw_key = secrets.token_urlsafe(32)
    async with async_session_maker() as session:
        session.add(ApiKey(name=name, key_hash=hash_api_key(raw_key)))
        await session.commit()
    return raw_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Documind API key")
    parser.add_argument("--name", required=True, help="Client name that will own the key")
    args = parser.parse_args()
    raw_key = asyncio.run(create_api_key(args.name))
    print(f"API key for '{args.name}' (store it now, it will not be shown again):")
    print(raw_key)


if __name__ == "__main__":
    main()

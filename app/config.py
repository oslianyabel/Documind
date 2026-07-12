from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://documind:documind@localhost:5433/documind"
    # Host port 6380 in dev to avoid clashing with a locally installed Redis.
    redis_url: str = "redis://localhost:6380"

    ingestion_job_timeout_seconds: int = 1800
    ingestion_max_concurrent_jobs: int = 4

    openai_api_key: str

    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    embedding_timeout_seconds: float = 60.0

    # Query-embedding cache (Redis): repeated searches skip the OpenAI call.
    embedding_cache_enabled: bool = True
    embedding_cache_ttl_seconds: int = 86_400  # 24h

    summary_model: str = "gpt-4o-mini"
    summary_max_tokens: int = 500
    summary_max_input_chars: int = 12_000
    summary_timeout_seconds: float = 60.0

    # Agents: document-grounded answers and search-scope validation.
    agent_model: str = "gpt-5.4-nano"
    agent_timeout_seconds: float = 45.0
    answer_max_tokens: int = 700

    max_chunk_chars: int = 1200
    search_top_k: int = 10

    data_dir: Path = Path("./data")

    # Set to "/api" in production (behind the frontend proxy) so FastAPI's docs
    # and OpenAPI URLs carry the prefix. Empty for direct local access.
    root_path: str = ""

    # Comma-separated IPs/CIDRs allowed to call the API (e.g.
    # "203.0.113.5, 10.0.0.0/8"). "*" = accessible from any client (default).
    api_allowed_hosts: str = "*"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


settings = Settings()

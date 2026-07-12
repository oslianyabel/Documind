import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.auth import require_api_key
from app.core.exceptions import (
    DocumentNameConflictError,
    DocumentNotFoundError,
    InvalidDocumentError,
)
from app.core.host_access import is_ip_allowed, parse_allowlist, resolve_client_ip
from app.core.notifications import notify_critical_error
from app.core.queue import create_queue_pool
from app.db.database import init_database
from app.routers import documents, history, search, uploads
from app.routers import settings as settings_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_database()
    app_instance.state.queue_pool = await create_queue_pool()
    yield
    await app_instance.state.queue_pool.aclose()


app = FastAPI(
    title="Launch-Intelligence",
    description="Microservicio de recomendación de documentos con embeddings en PostgreSQL",
    version="0.1.0",
    lifespan=lifespan,
    # Set ROOT_PATH=/api in production so Swagger (/api/docs) points its spec
    # and "Try it out" calls at the /api prefix the frontend proxy strips.
    root_path=settings.root_path,
)

authenticated = [Depends(require_api_key)]
app.include_router(search.router, dependencies=authenticated)
app.include_router(history.router, dependencies=authenticated)
app.include_router(documents.router, dependencies=authenticated)
app.include_router(uploads.router, dependencies=authenticated)
app.include_router(settings_router.router, dependencies=authenticated)
# Public: document/cover downloads work with a plain link (no X-API-Key).
app.include_router(documents.public_router)

# Parsed at import time so a malformed API_ALLOWED_HOSTS fails fast on startup.
ALLOWED_CLIENT_NETWORKS = parse_allowlist(settings.api_allowed_hosts)


@app.middleware("http")
async def restrict_client_hosts(request: Request, call_next):  # noqa: ANN001, ANN201
    """Reject requests from clients outside API_ALLOWED_HOSTS (default: all).

    /health stays open for readiness probes. This complements — never
    replaces — the X-API-Key authentication.
    """
    if ALLOWED_CLIENT_NETWORKS is not None and request.url.path != "/health":
        client_ip = resolve_client_ip(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
        )
        if not is_ip_allowed(client_ip, ALLOWED_CLIENT_NETWORKS):
            logger.warning("Rejected request from disallowed host %s", client_ip)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Client host not allowed"},
            )
    return await call_next(request)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(DocumentNotFoundError)
async def document_not_found_handler(
    _request: Request, error: DocumentNotFoundError
) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(error)})


@app.exception_handler(DocumentNameConflictError)
async def document_conflict_handler(
    _request: Request, error: DocumentNameConflictError
) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})


@app.exception_handler(InvalidDocumentError)
async def invalid_document_handler(
    _request: Request, error: InvalidDocumentError
) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(error)})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, error: Exception) -> JSONResponse:
    # Global error boundary: log, report to the dev via Telegram and hide internals.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    await notify_critical_error(
        f"Unhandled {type(error).__name__} on {request.method} {request.url.path}: {error}"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )

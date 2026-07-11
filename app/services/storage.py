import re
import uuid
from pathlib import Path

import aiofiles
import anyio

from app.config import settings

DOCUMENTS_SUBDIR = "documents"
COVERS_SUBDIR = "covers"
_SAFE_EXTENSION_PATTERN = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


def _safe_extension(filename: str) -> str:
    extension = Path(filename).suffix
    return extension if _SAFE_EXTENSION_PATTERN.match(extension) else ""


async def _save_bytes(directory: Path, file_id: uuid.UUID, filename: str, content: bytes) -> Path:
    await anyio.Path(directory).mkdir(parents=True, exist_ok=True)
    path = directory / f"{file_id}{_safe_extension(filename)}"
    async with aiofiles.open(path, "wb") as file:
        await file.write(content)
    return path


async def save_document_file(document_id: uuid.UUID, filename: str, content: bytes) -> Path:
    """Persist the original document on disk and return its path.

    Integrity metadata (sha256, size) is computed by the caller so the content
    hash can be reused for deduplication before the file is even written.
    """
    return await _save_bytes(settings.data_dir / DOCUMENTS_SUBDIR, document_id, filename, content)


async def save_cover_image(document_id: uuid.UUID, filename: str, content: bytes) -> Path:
    return await _save_bytes(settings.data_dir / COVERS_SUBDIR, document_id, filename, content)

import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.services.storage import save_cover_image, save_document_file


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


# uv run pytest -s tests/test_storage.py::test_save_document_file_writes_content
@pytest.mark.asyncio
async def test_save_document_file_writes_content(data_dir: Path) -> None:
    content = b"%PDF-1.4 fake content"
    document_id = uuid.uuid4()

    path = await save_document_file(document_id, "report.pdf", content)

    assert path.is_file()
    assert path.read_bytes() == content
    assert path.suffix == ".pdf"
    assert path.parent == data_dir / "documents"


# uv run pytest -s tests/test_storage.py::test_save_document_file_rejects_unsafe_extension
@pytest.mark.asyncio
async def test_save_document_file_rejects_unsafe_extension(data_dir: Path) -> None:
    path = await save_document_file(uuid.uuid4(), "weird.name.<script>", b"data")

    assert path.suffix == ""


# uv run pytest -s tests/test_storage.py::test_save_cover_image_writes_file
@pytest.mark.asyncio
async def test_save_cover_image_writes_file(data_dir: Path) -> None:
    path = await save_cover_image(uuid.uuid4(), "cover.png", b"png-bytes")

    assert path.is_file()
    assert path.parent == data_dir / "covers"

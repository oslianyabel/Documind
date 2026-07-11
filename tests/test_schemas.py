from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.documents import DocumentResponse


def _make_document(name: str) -> dict:
    return {
        "id": uuid4(),
        "name": name,
        "original_filename": "file.pdf",
        "mime_type": "application/pdf",
        "sha256": "abc",
        "size_bytes": 10,
        "status": "ready",
        "page_count": 1,
        "chunk_count": 1,
        "summary": None,
        "embedding_tokens_used": 0,
        "publication_year": None,
        "author": None,
        "description": None,
        "category": None,
        "language": None,
        "has_cover_image": False,
        "search_hit_count": 0,
        "created_at": datetime.now(UTC),
    }


# uv run pytest -s tests/test_schemas.py::test_download_url_uses_document_name
def test_download_url_uses_document_name() -> None:
    doc = DocumentResponse.model_validate(_make_document("mercedes-benz"))
    assert doc.download_url == "/documents/mercedes-benz/download"


# uv run pytest -s tests/test_schemas.py::test_download_url_is_url_encoded
def test_download_url_is_url_encoded() -> None:
    doc = DocumentResponse.model_validate(_make_document("informe final (v2)"))
    assert doc.download_url == "/documents/informe%20final%20%28v2%29/download"


# uv run pytest -s tests/test_schemas.py::test_download_url_present_in_serialized_output
def test_download_url_present_in_serialized_output() -> None:
    doc = DocumentResponse.model_validate(_make_document("doc"))
    assert doc.model_dump()["download_url"] == "/documents/doc/download"

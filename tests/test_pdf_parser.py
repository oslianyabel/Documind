import pytest

from app.core.exceptions import InvalidDocumentError
from app.services.pdf_parser import parse_pdf


# uv run pytest -s tests/test_pdf_parser.py::test_invalid_bytes_raise_invalid_document_error
def test_invalid_bytes_raise_invalid_document_error() -> None:
    with pytest.raises(InvalidDocumentError):
        parse_pdf(b"this is not a pdf file")

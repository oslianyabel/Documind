import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.exceptions import EmptyDocumentError, InvalidDocumentError


@dataclass(frozen=True)
class PdfLine:
    page_number: int
    line_number: int
    text: str


@dataclass(frozen=True)
class ParsedPdf:
    page_count: int
    lines: list[PdfLine]

    @property
    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def parse_pdf(file_bytes: bytes) -> ParsedPdf:
    """Extract text from a PDF keeping page and line positions for each line."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)
        lines: list[PdfLine] = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            for line_number, raw_line in enumerate(page_text.splitlines(), start=1):
                stripped = raw_line.strip()
                if stripped:
                    lines.append(PdfLine(page_number, line_number, stripped))
    except PyPdfError as error:
        raise InvalidDocumentError(f"The PDF could not be read: {error}") from error
    if not lines:
        raise EmptyDocumentError()
    return ParsedPdf(page_count=page_count, lines=lines)

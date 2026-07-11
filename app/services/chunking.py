from dataclasses import dataclass

from app.services.pdf_parser import PdfLine


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    start_page: int
    start_line: int
    end_page: int
    end_line: int


def build_chunks(lines: list[PdfLine], max_chars: int) -> list[TextChunk]:
    """Group consecutive lines into chunks of at most max_chars characters.

    A line longer than max_chars becomes its own chunk — lines are never split,
    so page/line boundaries stay exact.
    """
    chunks: list[TextChunk] = []
    current: list[PdfLine] = []
    current_length = 0

    def close_chunk() -> None:
        nonlocal current, current_length
        if not current:
            return
        chunks.append(
            TextChunk(
                index=len(chunks),
                content="\n".join(line.text for line in current),
                start_page=current[0].page_number,
                start_line=current[0].line_number,
                end_page=current[-1].page_number,
                end_line=current[-1].line_number,
            )
        )
        current = []
        current_length = 0

    for line in lines:
        added_length = len(line.text) + (1 if current else 0)
        if current and current_length + added_length > max_chars:
            close_chunk()
            added_length = len(line.text)
        current.append(line)
        current_length += added_length
    close_chunk()
    return chunks

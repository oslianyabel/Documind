from app.services.chunking import build_chunks
from app.services.pdf_parser import PdfLine


# uv run pytest -s tests/test_chunking.py::test_empty_lines_produce_no_chunks
def test_empty_lines_produce_no_chunks() -> None:
    assert build_chunks([], max_chars=100) == []


# uv run pytest -s tests/test_chunking.py::test_single_chunk_keeps_page_and_line_boundaries
def test_single_chunk_keeps_page_and_line_boundaries() -> None:
    lines = [
        PdfLine(page_number=1, line_number=3, text="first line"),
        PdfLine(page_number=1, line_number=4, text="second line"),
        PdfLine(page_number=2, line_number=1, text="third line"),
    ]

    chunks = build_chunks(lines, max_chars=1000)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.index == 0
    assert chunk.content == "first line\nsecond line\nthird line"
    assert (chunk.start_page, chunk.start_line) == (1, 3)
    assert (chunk.end_page, chunk.end_line) == (2, 1)


# uv run pytest -s tests/test_chunking.py::test_chunks_respect_max_chars
def test_chunks_respect_max_chars() -> None:
    lines = [PdfLine(page_number=1, line_number=i, text="x" * 40) for i in range(1, 11)]

    chunks = build_chunks(lines, max_chars=100)

    assert all(len(chunk.content) <= 100 for chunk in chunks)
    # 2 lines of 40 chars + newline = 81 chars per chunk -> 5 chunks
    assert len(chunks) == 5
    assert [chunk.index for chunk in chunks] == [0, 1, 2, 3, 4]


# uv run pytest -s tests/test_chunking.py::test_oversized_line_becomes_its_own_chunk
def test_oversized_line_becomes_its_own_chunk() -> None:
    lines = [
        PdfLine(page_number=1, line_number=1, text="short"),
        PdfLine(page_number=1, line_number=2, text="y" * 500),
        PdfLine(page_number=1, line_number=3, text="tail"),
    ]

    chunks = build_chunks(lines, max_chars=100)

    assert len(chunks) == 3
    assert chunks[1].content == "y" * 500
    assert (chunks[1].start_line, chunks[1].end_line) == (2, 2)


# uv run pytest -s tests/test_chunking.py::test_chunks_cover_all_lines_in_order
def test_chunks_cover_all_lines_in_order() -> None:
    lines = [PdfLine(page_number=1, line_number=i, text=f"line {i}") for i in range(1, 21)]

    chunks = build_chunks(lines, max_chars=50)

    rebuilt = "\n".join(chunk.content for chunk in chunks)
    assert rebuilt == "\n".join(line.text for line in lines)

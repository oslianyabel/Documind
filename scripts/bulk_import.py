"""Bulk-import a directory of PDFs and (re)optimize the vector index.

Designed to be run repeatedly (e.g. every time a client hands over a new batch
of documents). Each run:

  1. Ingests every PDF found under --source: parse, chunk, embed and insert
     directly (bypassing the HTTP API and the arq queue), with a concurrency
     limit and exponential backoff on OpenAI rate limits.
  2. Skips files whose content (sha256) is already indexed, so re-running is
     idempotent and doubles as a resume: interrupted runs just continue.
  3. Optimizes the HNSW index once at the end (--reindex): a repeatable step,
     not a one-time thing — the index can be rebuilt as many times as needed.

Usage:
    uv run python scripts/bulk_import.py --source /data/import
    uv run python scripts/bulk_import.py --source /data/import \
        --metadata /data/import/metadata.csv --concurrency 6 --reindex concurrent

Metadata (optional) maps each filename to its document fields. CSV with a
header row, or JSON (object keyed by filename, or a list of objects with a
"filename" key). Recognized columns/keys:
    filename (required), name, author, publication_year,
    description, category, language
When absent, `name` defaults to the filename without extension and the rest
are left empty.
"""

import argparse
import asyncio
import csv
import hashlib
import json
import random
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import anyio
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.core.exceptions import DocumindError  # noqa: E402
from app.db.database import async_session_maker, engine, init_database  # noqa: E402
from app.db.models import Chunk, Document, DocumentStatus  # noqa: E402
from app.services.chunking import build_chunks  # noqa: E402
from app.services.embeddings import _get_client  # noqa: E402
from app.services.pdf_parser import parse_pdf  # noqa: E402
from app.services.storage import delete_document_files, save_document_file  # noqa: E402
from app.services.summarizer import generate_summary  # noqa: E402

HNSW_INDEX_NAME = "ix_chunks_embedding_hnsw"
# Retryable transient OpenAI failures (the SDK already retries a couple times;
# this adds a wider, slower backoff so a big batch survives rate limiting).
_RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
_MEM_PATTERN = re.compile(r"^\d+(kB|MB|GB)?$")

METADATA_FIELDS = (
    "name",
    "author",
    "publication_year",
    "description",
    "category",
    "language",
)


@dataclass
class Report:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk-import PDFs and optimize the vector index")
    parser.add_argument("--source", required=True, help="Directory containing the PDFs")
    parser.add_argument(
        "--recursive", action="store_true", help="Search --source recursively for *.pdf"
    )
    parser.add_argument("--metadata", help="CSV or JSON file with per-filename metadata")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="Files ingested in parallel (default 4)"
    )
    parser.add_argument(
        "--summaries",
        action="store_true",
        help="Generate the AI summary per document (slower/costlier). "
        "Off by default: backfill later via POST /documents/{name}/summary.",
    )
    parser.add_argument(
        "--reindex",
        choices=("concurrent", "rebuild", "none"),
        default="concurrent",
        help="Index optimization after ingestion. 'concurrent' = REINDEX INDEX "
        "CONCURRENTLY (no downtime, needs ~2x index disk); 'rebuild' = DROP + "
        "CREATE (faster, requires a maintenance window); 'none' = skip.",
    )
    parser.add_argument(
        "--maintenance-work-mem",
        default="2GB",
        help="maintenance_work_mem for the reindex/build (e.g. 2GB, 512MB). Default 2GB.",
    )
    parser.add_argument("--hnsw-m", type=int, help="HNSW m for 'rebuild' (pgvector default 16)")
    parser.add_argument(
        "--hnsw-ef-construction",
        type=int,
        help="HNSW ef_construction for 'rebuild' (pgvector default 64)",
    )
    parser.add_argument("--report", help="Write a CSV report of per-file outcomes to this path")
    return parser.parse_args()


def _discover_pdfs(source: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in source.glob(pattern) if p.is_file())


def _load_metadata(path: Path | None) -> dict[str, dict]:
    """Return {filename: {field: value}} from a CSV or JSON sidecar."""
    if path is None:
        return {}
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else [{"filename": k, **v} for k, v in raw.items()]
    else:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    metadata: dict[str, dict] = {}
    for row in rows:
        filename = (row.get("filename") or "").strip()
        if filename:
            metadata[filename] = {k: row[k] for k in METADATA_FIELDS if row.get(k)}
    return metadata


def _document_fields(file_meta: dict, stem: str) -> dict:
    year_raw = file_meta.get("publication_year")
    try:
        year = int(year_raw) if year_raw not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    return {
        "name": (file_meta.get("name") or stem).strip(),
        "author": file_meta.get("author") or None,
        "publication_year": year,
        "description": file_meta.get("description") or None,
        "category": file_meta.get("category") or None,
        "language": file_meta.get("language") or None,
    }


async def _duplicate_exists(session, sha256: str) -> bool:
    result = await session.execute(
        select(Document.id).where(
            Document.sha256 == sha256,
            Document.deleted_at.is_(None),
            Document.status != DocumentStatus.FAILED.value,
        )
    )
    return result.scalar_one_or_none() is not None


async def _free_name(session, base_name: str) -> str:
    """Resolve a unique document name, appending -2, -3… on collision."""
    candidate = base_name
    suffix = 2
    while True:
        exists = await session.execute(
            select(Document.id).where(
                Document.name == candidate, Document.deleted_at.is_(None)
            )
        )
        if exists.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base_name}-{suffix}"
        suffix += 1


async def _embed_with_backoff(
    texts: list[str], max_retries: int = 6
) -> tuple[list[list[float]], int]:
    """Embed texts in batches, retrying each batch with exponential backoff."""
    client = _get_client()
    vectors: list[list[float]] = []
    total_tokens = 0
    batch_size = settings.embedding_batch_size
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        for attempt in range(max_retries + 1):
            try:
                response = await client.embeddings.create(
                    model=settings.embedding_model, input=batch
                )
                break
            except _RETRYABLE:
                if attempt == max_retries:
                    raise
                delay = min(60.0, 2.0**attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
        vectors.extend(item.embedding for item in response.data)
        total_tokens += response.usage.total_tokens
    return vectors, total_tokens


async def _ingest_file(path: Path, file_meta: dict, generate_summaries: bool) -> str:
    """Ingest a single PDF. Returns 'ingested' or 'skipped'; raises on failure."""
    content = await anyio.Path(path).read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()

    async with async_session_maker() as session:
        if await _duplicate_exists(session, sha256):
            return "skipped"

    # Parsing/chunking is CPU-bound; run it off the event loop so other files
    # keep embedding in parallel.
    parsed = await anyio.to_thread.run_sync(parse_pdf, content)
    chunks = await anyio.to_thread.run_sync(
        lambda: build_chunks(parsed.lines, settings.max_chunk_chars)
    )
    vectors, tokens = await _embed_with_backoff([c.content for c in chunks])
    summary = None
    if generate_summaries:
        try:
            summary = await generate_summary(parsed.full_text)
        except OpenAIError:
            summary = None

    document_id = uuid.uuid4()
    storage_path = await save_document_file(document_id, path.name, content)
    try:
        for _ in range(5):
            async with async_session_maker() as session:
                fields = _document_fields(file_meta, path.stem)
                fields["name"] = await _free_name(session, fields["name"])
                session.add(
                    Document(
                        id=document_id,
                        original_filename=path.name,
                        mime_type="application/pdf",
                        storage_path=str(storage_path),
                        sha256=sha256,
                        size_bytes=len(content),
                        status=DocumentStatus.READY.value,
                        page_count=parsed.page_count,
                        chunk_count=len(chunks),
                        summary=summary,
                        summary_generated=summary is not None,
                        embedding_tokens_used=tokens,
                        **fields,
                    )
                )
                session.add_all(
                    Chunk(
                        document_id=document_id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        start_page=chunk.start_page,
                        start_line=chunk.start_line,
                        end_page=chunk.end_page,
                        end_line=chunk.end_line,
                        embedding=vector,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                )
                try:
                    await session.commit()
                    return "ingested"
                except IntegrityError:
                    # Lost a name race with a concurrent file; retry name.
                    await session.rollback()
        raise DocumindError(f"Could not resolve a free name for '{path.name}' after retries")
    except BaseException:
        # Roll back the on-disk file so a failed insert leaves nothing behind.
        await delete_document_files(str(storage_path), None)
        raise


async def _optimize_index(args: argparse.Namespace) -> None:
    if args.reindex == "none":
        print("Index optimization skipped (--reindex none).")
        return
    if not _MEM_PATTERN.match(args.maintenance_work_mem):
        raise SystemExit(f"Invalid --maintenance-work-mem: {args.maintenance_work_mem!r}")

    # REINDEX/CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f"SET maintenance_work_mem = '{args.maintenance_work_mem}'"))
        if args.reindex == "concurrent":
            print(f"Reindexing {HNSW_INDEX_NAME} CONCURRENTLY (no downtime)…")
            await conn.execute(text(f"REINDEX INDEX CONCURRENTLY {HNSW_INDEX_NAME}"))
        else:
            with_opts = ""
            opts = []
            if args.hnsw_m is not None:
                opts.append(f"m = {int(args.hnsw_m)}")
            if args.hnsw_ef_construction is not None:
                opts.append(f"ef_construction = {int(args.hnsw_ef_construction)}")
            if opts:
                with_opts = f" WITH ({', '.join(opts)})"
            print(f"Rebuilding {HNSW_INDEX_NAME} (DROP + CREATE)…")
            await conn.execute(text(f"DROP INDEX IF EXISTS {HNSW_INDEX_NAME}"))
            await conn.execute(
                text(
                    f"CREATE INDEX {HNSW_INDEX_NAME} ON chunks "
                    f"USING hnsw (embedding vector_cosine_ops){with_opts}"
                )
            )
        await conn.execute(text("ANALYZE chunks"))
    print("Index optimization done.")


def _write_report(path: Path, report: Report) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["file", "outcome", "detail"])
        for name in report.ingested:
            writer.writerow([name, "ingested", ""])
        for name in report.skipped:
            writer.writerow([name, "skipped_duplicate", ""])
        for name, detail in report.failed:
            writer.writerow([name, "failed", detail])


async def main() -> None:
    args = _parse_args()
    source = Path(args.source)
    if not await anyio.Path(source).is_dir():
        raise SystemExit(f"--source is not a directory: {source}")

    files = _discover_pdfs(source, args.recursive)
    if not files:
        raise SystemExit(f"No PDFs found under {source}")
    metadata = _load_metadata(Path(args.metadata) if args.metadata else None)
    print(f"Found {len(files)} PDF(s). Concurrency={args.concurrency}. Ensuring schema…")
    await init_database()

    report = Report()
    semaphore = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()

    async def worker(path: Path) -> None:
        async with semaphore:
            try:
                outcome = await _ingest_file(path, metadata.get(path.name, {}), args.summaries)
            except (DocumindError, OpenAIError, OSError, ValueError) as error:
                report.failed.append((path.name, f"{type(error).__name__}: {error}"))
                print(f"  ✗ {path.name}: {error}")
            else:
                (report.ingested if outcome == "ingested" else report.skipped).append(path.name)
                mark = "＋" if outcome == "ingested" else "＝"
                print(f"  {mark} {path.name} ({outcome})")

    await asyncio.gather(*(worker(path) for path in files))

    elapsed = time.perf_counter() - started
    print(
        f"\nIngestion done in {elapsed:.1f}s — "
        f"{len(report.ingested)} ingested, {len(report.skipped)} skipped, "
        f"{len(report.failed)} failed."
    )
    # Only optimize when something actually changed.
    if report.ingested:
        await _optimize_index(args)
    else:
        print("Nothing new ingested; skipping index optimization.")

    if args.report:
        _write_report(Path(args.report), report)
        print(f"Report written to {args.report}")
    if report.failed:
        print("Some files failed; re-running the command will retry only those (dedupe skips OK).")


if __name__ == "__main__":
    asyncio.run(main())

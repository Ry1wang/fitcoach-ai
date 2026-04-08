"""Document ingestion pipeline: parse → chunk → embed → store."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from sqlalchemy import delete, select

from app.config import settings
from app.deps import async_session
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.document_service import update_document_status
from app.services.embedding_service import generate_embeddings
from app.services.pdf_processor import chunk_document

# Module-level semaphore: caps the number of ingestion pipelines that can
# run concurrently inside one uvicorn process. Guards against OOM when
# multiple large PDFs are uploaded in parallel — without this, FastAPI
# BackgroundTasks happily runs them all at once and memory peaks stack up.
# Tasks still get enqueued instantly (upload endpoint returns 202 right
# away); they just serialize here.
_INGESTION_SEMAPHORE = asyncio.Semaphore(settings.MAX_CONCURRENT_INGESTIONS)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def run_ingestion_pipeline(
    *,
    doc_id: uuid.UUID,
    user_id: uuid.UUID,
    file_path: str,
    filename: str,
    domain: str | None,
) -> None:
    """Full ingestion pipeline executed as a FastAPI BackgroundTask.

    Creates its own DB session — the request session is already closed
    by the time this runs.

    Concurrency is capped by ``_INGESTION_SEMAPHORE`` (default 1) so that
    multiple simultaneous uploads serialize instead of fighting for memory.

    Status transitions:
        pending → processing → ready
        pending → processing → failed  (on any exception)
    """
    async with _INGESTION_SEMAPHORE, async_session() as session:
        try:
            # 1. Mark as processing
            await update_document_status(
                session, doc_id, user_id, status="processing"
            )
            logger.info("Starting ingestion for doc_id=%s (%s)", doc_id, filename)

            # 2–4. Parse PDF and build chunk dicts
            logger.info("Step 2/4: Chunking document %s...", filename)
            loop = asyncio.get_running_loop()
            raw_chunks = await loop.run_in_executor(
                None, chunk_document, file_path, filename, domain
            )
            if not raw_chunks:
                logger.warning("No text content extracted for doc_id=%s", doc_id)
                await update_document_status(
                    session,
                    doc_id,
                    user_id,
                    status="failed",
                    error_message="No text content could be extracted from the PDF",
                )
                return

            logger.info("Step 5: Generating embeddings for %d chunks of %s...", len(raw_chunks), filename)

            # 5. Generate embeddings (async, batched, with retry)
            texts = [c["content"] for c in raw_chunks]
            embeddings = await generate_embeddings(texts)
            if len(embeddings) != len(texts):
                raise RuntimeError(
                    f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
                )

            logger.info("Step 7: Inserting %d chunks into DB for %s...", len(raw_chunks), filename)

            # 6. Verify document still exists (may have been deleted mid-processing)
            stmt = select(Document.id).where(
                Document.id == doc_id, Document.user_id == user_id
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                logger.warning(
                    "Document %s was deleted during processing, skipping chunk insert",
                    doc_id,
                )
                return

            # 7a. Clear any pre-existing chunks for this document. Normally
            # this is a no-op (first ingestion), but for retries of a 'failed'
            # document there may be stale rows from a partial previous run —
            # or, with the retry endpoint, the document may have been fully
            # ingested before. We want the final state to be deterministic:
            # exactly the chunks from this run.
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )

            # 7b. Batch-insert chunks
            db_chunks = [
                DocumentChunk(
                    document_id=doc_id,
                    content=raw["content"],
                    chunk_index=raw["chunk_index"],
                    chunk_type=raw["chunk_type"],
                    chunk_metadata=raw["chunk_metadata"],
                    embedding=emb,
                    created_at=_utcnow(),
                )
                for raw, emb in zip(raw_chunks, embeddings)
            ]
            session.add_all(db_chunks)

            # 8. Sanity-check chunk count before marking ready.
            #    A real document must yield at least MIN_CHUNK_COUNT chunks;
            #    fewer almost always means the PDF is a scanned image or has
            #    no extractable text layer (silent extraction failure).
            if len(db_chunks) < settings.MIN_CHUNK_COUNT:
                error_msg = (
                    f"Ingestion produced only {len(db_chunks)} chunk(s) "
                    f"(minimum {settings.MIN_CHUNK_COUNT} required). "
                    "The PDF may be a scanned image or have no extractable text."
                )
                logger.warning(
                    "doc_id=%s (%s) produced only %d chunk(s) — marking failed",
                    doc_id, filename, len(db_chunks),
                )
                await update_document_status(
                    session, doc_id, user_id, status="failed", error_message=error_msg
                )
                return

            # 9. Mark ready — commit also flushes the pending chunk inserts
            await update_document_status(
                session,
                doc_id,
                user_id,
                status="ready",
                chunk_count=len(db_chunks),
            )
            logger.info("Successfully indexed doc_id=%s (%s) with %d chunks", doc_id, filename, len(db_chunks))

        except Exception as exc:  # noqa: BLE001
            logger.exception("Ingestion pipeline failed for doc_id=%s", doc_id)
            try:
                await update_document_status(
                    session,
                    doc_id,
                    user_id,
                    status="failed",
                    error_message=str(exc)[:1000],
                )
            except Exception:
                logger.warning(
                    "Could not mark doc %s as failed (possibly already deleted)",
                    doc_id,
                )

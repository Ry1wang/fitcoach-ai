"""Document ingestion pipeline: parse → chunk → embed → store."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from sqlalchemy import select

from app.deps import async_session
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.document_service import update_document_status
from app.services.embedding_service import generate_embeddings
from app.services.pdf_processor import chunk_document


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

    Status transitions:
        pending → processing → ready
        pending → processing → failed  (on any exception)
    """
    async with async_session() as session:
        try:
            # 1. Mark as processing
            await update_document_status(
                session, doc_id, user_id, status="processing"
            )

            # 2–4. Parse PDF and build chunk dicts
            # Run sync CPU-intensive work in a thread pool to avoid blocking
            # the event loop (PDF parsing + text splitting can be slow).
            loop = asyncio.get_running_loop()
            raw_chunks = await loop.run_in_executor(
                None, chunk_document, file_path, filename, domain
            )
            if not raw_chunks:
                await update_document_status(
                    session,
                    doc_id,
                    user_id,
                    status="failed",
                    error_message="No text content could be extracted from the PDF",
                )
                return

            # 5. Generate embeddings (async, batched, with retry)
            texts = [c["content"] for c in raw_chunks]
            embeddings = await generate_embeddings(texts)

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

            # 7. Batch-insert chunks
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

            # 8. Mark ready — commit also flushes the pending chunk inserts
            await update_document_status(
                session,
                doc_id,
                user_id,
                status="ready",
                chunk_count=len(db_chunks),
            )

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

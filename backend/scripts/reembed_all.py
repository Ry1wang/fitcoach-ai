"""Re-embed all document chunks with the currently configured embedding model.

Purpose: After switching EMBEDDING_MODEL (e.g., nomic-embed-text → bge-m3) and
altering the document_chunks.embedding column dimension, all existing rows
have NULL embeddings. This script regenerates them in batches.

Usage (run inside the backend container):
    docker exec -it fitcoach-backend python -m scripts.reembed_all

Idempotent: only operates on chunks where embedding IS NULL.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Make sure we can import `app.*` when invoked as a plain script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.deps import async_session  # noqa: E402
from app.services.embedding_service import generate_embeddings  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("reembed")

BATCH_SIZE = 25


def _vec_to_pg(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def main() -> None:
    logger.info(
        "Re-embedding with model=%s dim=%s",
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_DIMENSION,
    )

    async with async_session() as session:
        # Count pending chunks
        total_result = await session.execute(
            text("SELECT COUNT(*) FROM document_chunks WHERE embedding IS NULL")
        )
        total = total_result.scalar_one()
        logger.info("Found %d chunks pending re-embed", total)
        if total == 0:
            logger.info("Nothing to do.")
            return

        processed = 0
        while True:
            # Fetch a batch of chunks needing embedding
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, content
                        FROM document_chunks
                        WHERE embedding IS NULL
                        ORDER BY document_id, chunk_index
                        LIMIT :batch
                        """
                    ),
                    {"batch": BATCH_SIZE},
                )
            ).fetchall()

            if not rows:
                break

            ids = [row.id for row in rows]
            texts_ = [row.content for row in rows]

            try:
                vectors = await generate_embeddings(texts_)
            except Exception:
                logger.exception(
                    "Embedding batch failed (first id=%s). Aborting.", ids[0]
                )
                raise

            if len(vectors) != len(ids):
                raise RuntimeError(
                    f"Embedding count mismatch: ids={len(ids)} vectors={len(vectors)}"
                )

            # UPDATE each row. Batched in one transaction per outer batch.
            for chunk_id, vec in zip(ids, vectors):
                await session.execute(
                    text(
                        "UPDATE document_chunks "
                        "SET embedding = CAST(:vec AS vector) "
                        "WHERE id = :id"
                    ),
                    {"vec": _vec_to_pg(vec), "id": chunk_id},
                )
            await session.commit()

            processed += len(rows)
            logger.info(
                "Progress: %d / %d (%.1f%%)",
                processed,
                total,
                100 * processed / total,
            )

        logger.info("Done. Re-embedded %d chunks.", processed)


if __name__ == "__main__":
    asyncio.run(main())

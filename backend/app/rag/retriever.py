"""pgvector retrieval — cosine similarity search, user-scoped via JOIN."""
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.embedding_service import generate_embeddings


@dataclass
class ChunkResult:
    id: uuid.UUID
    content: str
    chunk_type: str | None
    chunk_metadata: dict[str, Any] | None
    relevance_score: float


def _vec_to_pg(embedding: list[float]) -> str:
    """Convert a Python float list to a PostgreSQL vector literal string."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def retrieve(
    query: str,
    user_id: uuid.UUID,
    session: AsyncSession,
    *,
    content_domain: str | None = None,
    top_k: int | None = None,
) -> list[ChunkResult]:
    """Return the top-K most relevant chunks for *query*.

    Scoping rules:
    - Only chunks whose parent document is owned by *user_id* are searched.
    - Only documents with status='ready' are considered.
    - If *content_domain* is given, only chunks whose metadata field
      ``content_domain`` matches are returned.

    Relevance score = 1 - cosine_distance (range 0–1, higher = more similar).
    """
    if top_k is None:
        top_k = settings.RETRIEVAL_TOP_K

    # Embed the query (reuse the batched embedding service with a single-item list)
    embeddings = await generate_embeddings([query])
    query_vec = _vec_to_pg(embeddings[0])

    # Build SQL dynamically (domain filter is optional)
    where_clauses = [
        "d.user_id = :user_id",
        "d.status = 'ready'",
    ]
    params: dict[str, Any] = {
        "query_vec": query_vec,
        "user_id": str(user_id),
        "top_k": top_k,
    }

    if content_domain is not None:
        where_clauses.append("dc.metadata->>'content_domain' = :domain")
        params["domain"] = content_domain

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            dc.id,
            dc.content,
            dc.chunk_type,
            dc.metadata,
            1 - (dc.embedding <=> CAST(:query_vec AS vector)) AS relevance_score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE {where_sql}
        ORDER BY dc.embedding <=> CAST(:query_vec AS vector)
        LIMIT :top_k
    """)  # noqa: S608 — all params are bound, no string interpolation of user data

    result = await session.execute(sql, params)
    rows = result.fetchall()

    return [
        ChunkResult(
            id=row.id,
            content=row.content,
            chunk_type=row.chunk_type,
            chunk_metadata=row.metadata,
            relevance_score=float(row.relevance_score),
        )
        for row in rows
    ]

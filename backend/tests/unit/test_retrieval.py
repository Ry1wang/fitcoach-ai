"""Unit tests for the pgvector retrieval layer.

All tests mock both the embedding call and the DB session so they run
without a real database or embedding API.
"""
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.rag.retriever import ChunkResult, _vec_to_pg, retrieve

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * settings.EMBEDDING_DIMENSION
FAKE_USER_ID = uuid.uuid4()
FAKE_DOC_ID = uuid.uuid4()
FAKE_CHUNK_ID = uuid.uuid4()


def _make_row(
    *,
    id: uuid.UUID | None = None,
    content: str = "深蹲是下肢力量的核心动作",
    chunk_type: str = "text",
    metadata: dict | None = None,
    relevance_score: float = 0.91,
) -> MagicMock:
    row = MagicMock()
    row.id = id or uuid.uuid4()
    row.content = content
    row.chunk_type = chunk_type
    row.metadata = metadata or {"source_book": "囚徒健身", "content_domain": "training"}
    row.relevance_score = relevance_score
    return row


def _mock_session(rows: list[Any]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_vec_to_pg_format():
    """_vec_to_pg should produce a valid PostgreSQL vector literal."""
    vec = [0.1, 0.2, 0.3]
    pg_str = _vec_to_pg(vec)
    assert pg_str == "[0.1,0.2,0.3]"


def test_vec_to_pg_large_dimension():
    vec = [0.5] * 1024
    pg_str = _vec_to_pg(vec)
    assert pg_str.startswith("[")
    assert pg_str.endswith("]")
    assert pg_str.count(",") == 1023


# ---------------------------------------------------------------------------
# retrieve() unit tests
# ---------------------------------------------------------------------------


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_returns_list_of_chunk_results(mock_embed):
    """retrieve() should return a list of ChunkResult instances."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([_make_row(id=FAKE_CHUNK_ID)])

    results = await retrieve("如何练深蹲", FAKE_USER_ID, session)

    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], ChunkResult)


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_chunk_result_fields_populated(mock_embed):
    """ChunkResult should have all expected fields with correct types."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    meta = {"source_book": "囚徒健身", "page_start": 42, "content_domain": "training"}
    row = _make_row(id=FAKE_CHUNK_ID, content="引体向上入门", chunk_type="exercise",
                    metadata=meta, relevance_score=0.87)
    session = _mock_session([row])

    results = await retrieve("引体向上", FAKE_USER_ID, session)
    r = results[0]

    assert r.id == FAKE_CHUNK_ID
    assert r.content == "引体向上入门"
    assert r.chunk_type == "exercise"
    assert r.chunk_metadata == meta
    assert abs(r.relevance_score - 0.87) < 1e-9


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_with_domain_filter_passes_param(mock_embed):
    """When content_domain is given, SQL params must include 'domain'."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([_make_row()])

    await retrieve("膝盖疼痛", FAKE_USER_ID, session, content_domain="rehab")

    call_args = session.execute.call_args
    params = call_args[0][1]  # second positional arg is params dict
    assert "domain" in params
    assert params["domain"] == "rehab"


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_without_domain_omits_domain_param(mock_embed):
    """When no content_domain is given, SQL params must NOT include 'domain'."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([_make_row()])

    await retrieve("训练计划", FAKE_USER_ID, session)

    call_args = session.execute.call_args
    params = call_args[0][1]
    assert "domain" not in params


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_uses_settings_top_k_by_default(mock_embed):
    """When top_k is not passed, it defaults to settings.RETRIEVAL_TOP_K."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([])

    await retrieve("训练计划", FAKE_USER_ID, session)

    call_args = session.execute.call_args
    params = call_args[0][1]
    assert params["top_k"] == settings.RETRIEVAL_TOP_K


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_custom_top_k_overrides_default(mock_embed):
    """An explicit top_k should override the settings default."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([])

    await retrieve("训练计划", FAKE_USER_ID, session, top_k=3)

    call_args = session.execute.call_args
    params = call_args[0][1]
    assert params["top_k"] == 3


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_empty_db_returns_empty_list(mock_embed):
    """When no chunks are found, retrieve() returns an empty list (not None)."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([])

    results = await retrieve("蛋白质摄入", FAKE_USER_ID, session, content_domain="nutrition")

    assert results == []


@patch("app.rag.retriever.generate_embeddings", new_callable=AsyncMock)
async def test_retrieve_user_id_in_params(mock_embed):
    """SQL params must include user_id as a string."""
    mock_embed.return_value = [FAKE_EMBEDDING]
    session = _mock_session([])

    await retrieve("test", FAKE_USER_ID, session)

    call_args = session.execute.call_args
    params = call_args[0][1]
    assert params["user_id"] == str(FAKE_USER_ID)

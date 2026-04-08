"""Unit tests for specialist agent nodes: training, rehab, nutrition.

Covers per node:
- Happy path: normal LLM response → correct state fields
- Degradation 1 (空响应): empty LLM response → response field is ""
  (rehab node still appends the mandatory disclaimer)
- Degradation 2 (超时): TimeoutError from call_llm propagates — node has no try/except
- Degradation 3 (LLM错误): Unexpected RuntimeError propagates — node does not swallow it

Mock injection: retrieve, get_llm_client, call_llm are patched at module level so no
DB/embedding/LLM network calls occur during unit tests.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.prompts import REHAB_DISCLAIMER
from app.agents.state import AgentState
from app.rag.retriever import ChunkResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(query: str = "深蹲技术要点") -> AgentState:
    return {
        "user_query": query,
        "refined_query": query,
        "user_id": str(uuid.uuid4()),
        "session": MagicMock(),  # never accessed — retrieve is mocked
        "chat_history": [],
    }


def _make_chunk() -> ChunkResult:
    return ChunkResult(
        id=uuid.uuid4(),
        content="这是一段关于深蹲的训练参考内容，来自囚徒健身第三章。",
        chunk_type="text",
        chunk_metadata={"source_book": "囚徒健身", "chapter": "第三章"},
        relevance_score=0.82,
    )


# ---------------------------------------------------------------------------
# training_node
# ---------------------------------------------------------------------------


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_training_node_happy_path(mock_retrieve, mock_call_llm, mock_get_client):
    """Normal response → agent_used, response, sources, no disclaimer."""
    mock_retrieve.return_value = [_make_chunk()]
    mock_call_llm.return_value = "深蹲时保持核心收紧，脚与肩同宽。"

    from app.agents.specialist import training_node

    result = await training_node(_make_state())

    assert result["agent_used"] == "training"
    assert "深蹲" in result["response"]
    assert result["disclaimer"] is None
    assert len(result["sources"]) == 1
    assert result["sources"][0]["source_book"] == "囚徒健身"


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_training_node_empty_llm_response(mock_retrieve, mock_call_llm, mock_get_client):
    """Empty LLM response → response is '', no disclaimer appended."""
    mock_retrieve.return_value = []
    mock_call_llm.return_value = ""

    from app.agents.specialist import training_node

    result = await training_node(_make_state())

    assert result["response"] == ""
    assert result["agent_used"] == "training"
    assert result["disclaimer"] is None
    assert result["sources"] == []


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_training_node_llm_timeout_propagates(mock_retrieve, mock_call_llm, mock_get_client):
    """TimeoutError from call_llm propagates — training_node has no try/except."""
    mock_retrieve.return_value = []
    mock_call_llm.side_effect = TimeoutError("LLM request timed out")

    from app.agents.specialist import training_node

    with pytest.raises(TimeoutError):
        await training_node(_make_state())


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_training_node_llm_error_propagates(mock_retrieve, mock_call_llm, mock_get_client):
    """Unexpected LLM error (e.g., rate limit) propagates — not silently swallowed."""
    mock_retrieve.return_value = []
    mock_call_llm.side_effect = RuntimeError("rate limit exceeded")

    from app.agents.specialist import training_node

    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        await training_node(_make_state())


# ---------------------------------------------------------------------------
# rehab_node
# ---------------------------------------------------------------------------


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_rehab_node_happy_path(mock_retrieve, mock_call_llm, mock_get_client):
    """Normal response → disclaimer always appended at the end."""
    mock_retrieve.return_value = [_make_chunk()]
    mock_call_llm.return_value = "建议先冰敷患处，避免负重。"

    from app.agents.specialist import rehab_node

    result = await rehab_node(_make_state("膝盖疼痛处理"))

    assert result["agent_used"] == "rehab"
    assert result["response"].startswith("建议先冰敷患处")
    assert result["response"].endswith(REHAB_DISCLAIMER)
    assert result["disclaimer"] == REHAB_DISCLAIMER


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_rehab_node_empty_response_still_appends_disclaimer(
    mock_retrieve, mock_call_llm, mock_get_client
):
    """Even when LLM returns '', rehab node appends the mandatory disclaimer."""
    mock_retrieve.return_value = []
    mock_call_llm.return_value = ""

    from app.agents.specialist import rehab_node

    result = await rehab_node(_make_state())

    assert result["response"] == REHAB_DISCLAIMER
    assert result["disclaimer"] == REHAB_DISCLAIMER
    assert result["agent_used"] == "rehab"


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_rehab_node_llm_timeout_propagates(mock_retrieve, mock_call_llm, mock_get_client):
    mock_retrieve.return_value = []
    mock_call_llm.side_effect = TimeoutError("LLM request timed out")

    from app.agents.specialist import rehab_node

    with pytest.raises(TimeoutError):
        await rehab_node(_make_state())


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_rehab_node_llm_error_propagates(mock_retrieve, mock_call_llm, mock_get_client):
    mock_retrieve.return_value = []
    mock_call_llm.side_effect = RuntimeError("rate limit exceeded")

    from app.agents.specialist import rehab_node

    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        await rehab_node(_make_state())


# ---------------------------------------------------------------------------
# nutrition_node
# ---------------------------------------------------------------------------


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_nutrition_node_happy_path(mock_retrieve, mock_call_llm, mock_get_client):
    mock_retrieve.return_value = [_make_chunk()]
    mock_call_llm.return_value = "增肌期每日蛋白质摄入建议 1.6–2.2 g/kg 体重。"

    from app.agents.specialist import nutrition_node

    result = await nutrition_node(_make_state("增肌蛋白质摄入"))

    assert result["agent_used"] == "nutrition"
    assert "蛋白质" in result["response"]
    assert result["disclaimer"] is None
    assert len(result["sources"]) == 1


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_nutrition_node_empty_llm_response(mock_retrieve, mock_call_llm, mock_get_client):
    mock_retrieve.return_value = []
    mock_call_llm.return_value = ""

    from app.agents.specialist import nutrition_node

    result = await nutrition_node(_make_state())

    assert result["response"] == ""
    assert result["agent_used"] == "nutrition"
    assert result["disclaimer"] is None


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_nutrition_node_llm_timeout_propagates(mock_retrieve, mock_call_llm, mock_get_client):
    mock_retrieve.return_value = []
    mock_call_llm.side_effect = TimeoutError("LLM request timed out")

    from app.agents.specialist import nutrition_node

    with pytest.raises(TimeoutError):
        await nutrition_node(_make_state())


@patch("app.agents.specialist.get_llm_client")
@patch("app.agents.specialist.call_llm", new_callable=AsyncMock)
@patch("app.agents.specialist.retrieve", new_callable=AsyncMock)
async def test_nutrition_node_llm_error_propagates(mock_retrieve, mock_call_llm, mock_get_client):
    mock_retrieve.return_value = []
    mock_call_llm.side_effect = RuntimeError("rate limit exceeded")

    from app.agents.specialist import nutrition_node

    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        await nutrition_node(_make_state())

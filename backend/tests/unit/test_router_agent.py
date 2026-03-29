"""Unit tests for the Router Agent.

Tests cover:
- parse_router_response: 10 parametrized cases (valid, edge, malformed)
- route_by_agent: reads state correctly
- router_node: mocked LLM call produces correct state updates
- graph: compiles without error
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.router import parse_router_response, route_by_agent
from app.agents.state import AgentState


# ---------------------------------------------------------------------------
# parse_router_response — parametrized (10 cases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content, original_query, expected_agent, expected_query_contains",
    [
        # --- Valid JSON responses ---
        (
            '{"agent": "training", "refined_query": "引体向上训练进阶方法"}',
            "我想练引体向上",
            "training",
            "引体向上",
        ),
        (
            '{"agent": "rehab", "refined_query": "膝盖疼痛原因和康复方案"}',
            "跑步后膝盖疼",
            "rehab",
            "膝盖",
        ),
        (
            '{"agent": "nutrition", "refined_query": "增肌期每日蛋白质摄入量"}',
            "增肌吃多少蛋白质",
            "nutrition",
            "蛋白质",
        ),
        # --- JSON embedded in prose ---
        (
            '好的，以下是分类结果：{"agent": "rehab", "refined_query": "肩袖损伤康复训练"} 希望对你有帮助。',
            "肩膀受伤了",
            "rehab",
            "肩",
        ),
        # --- Unknown agent → fallback to training ---
        (
            '{"agent": "general_fitness", "refined_query": "综合健身建议"}',
            "健身入门",
            "training",
            "健身",
        ),
        # --- Missing refined_query → use original query ---
        (
            '{"agent": "nutrition"}',
            "减脂期饮食计划",
            "nutrition",
            "减脂期",
        ),
        # --- Empty JSON → fallback ---
        (
            "{}",
            "如何提高耐力",
            "training",
            "如何提高耐力",
        ),
        # --- Completely invalid JSON → fallback ---
        (
            "我无法理解这个问题",
            "测试问题",
            "training",
            "测试问题",
        ),
        # --- Uppercase agent name → normalised to lowercase → valid ---
        (
            '{"agent": "TRAINING", "refined_query": "力量训练基础"}',
            "力量训练",
            "training",
            "力量",
        ),
        # --- Mixed-case "Rehab" → normalised → valid ---
        (
            '{"agent": "Rehab", "refined_query": "腰部疼痛康复"}',
            "腰疼",
            "rehab",
            "腰",
        ),
    ],
)
def test_parse_router_response(
    content, original_query, expected_agent, expected_query_contains
):
    agent, refined_query = parse_router_response(content, original_query)

    assert agent == expected_agent
    assert expected_query_contains in refined_query


# ---------------------------------------------------------------------------
# route_by_agent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("routed_agent", ["training", "rehab", "nutrition"])
def test_route_by_agent_returns_correct_node(routed_agent):
    state: AgentState = {
        "user_query": "test",
        "user_id": str(uuid.uuid4()),
        "chat_history": [],
        "routed_agent": routed_agent,
    }
    assert route_by_agent(state) == routed_agent


def test_route_by_agent_defaults_to_training_when_missing():
    """If routed_agent is not in state, fall back to 'training'."""
    state: AgentState = {
        "user_query": "test",
        "user_id": str(uuid.uuid4()),
        "chat_history": [],
    }
    assert route_by_agent(state) == "training"


# ---------------------------------------------------------------------------
# router_node — mocked LLM
# ---------------------------------------------------------------------------


@patch("app.agents.router.get_llm_client")
@patch("app.agents.router.call_llm", new_callable=AsyncMock)
async def test_router_node_returns_state_updates(mock_call_llm, mock_get_client):
    mock_call_llm.return_value = '{"agent": "training", "refined_query": "深蹲技术要点"}'

    from app.agents.router import router_node

    state: AgentState = {
        "user_query": "深蹲怎么练",
        "user_id": str(uuid.uuid4()),
        "chat_history": [],
    }
    result = await router_node(state)

    assert result["routed_agent"] == "training"
    assert "深蹲" in result["refined_query"]


@patch("app.agents.router.get_llm_client")
@patch("app.agents.router.call_llm", new_callable=AsyncMock)
async def test_router_node_fallback_on_bad_llm_response(mock_call_llm, mock_get_client):
    """When the LLM returns garbage, router falls back to training."""
    mock_call_llm.return_value = "我不知道"

    from app.agents.router import router_node

    state: AgentState = {
        "user_query": "随便问一个问题",
        "user_id": str(uuid.uuid4()),
        "chat_history": [],
    }
    result = await router_node(state)

    assert result["routed_agent"] == "training"
    assert result["refined_query"] == "随便问一个问题"


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------


def test_agent_graph_compiles():
    """The LangGraph StateGraph must compile without errors."""
    from app.agents.graph import agent_graph

    assert agent_graph is not None
    # Verify all expected nodes are present
    graph_nodes = set(agent_graph.nodes.keys())
    assert {"router", "training", "rehab", "nutrition"}.issubset(graph_nodes)

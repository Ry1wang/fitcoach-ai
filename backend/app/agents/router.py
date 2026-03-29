"""Router agent — classifies user intent and refines the query."""
import json
import re

from app.agents.prompts import ROUTER_SYSTEM_PROMPT
from app.agents.state import AgentState
from app.deps import get_llm_client
from app.services.llm_service import call_llm

_VALID_AGENTS = frozenset({"training", "rehab", "nutrition"})


def parse_router_response(content: str, original_query: str) -> tuple[str, str]:
    """Extract (agent, refined_query) from the LLM's JSON response.

    Falls back to ("training", original_query) on any parse failure or
    when the returned agent name is not one of the three valid values.
    """
    def _extract(data: dict) -> tuple[str, str]:
        agent = str(data.get("agent", "")).strip().lower()
        if agent not in _VALID_AGENTS:
            agent = "training"
        refined = str(data.get("refined_query", "")).strip() or original_query
        return agent, refined

    # 1. Try direct JSON parse
    try:
        return _extract(json.loads(content.strip()))
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    # 2. Try to extract embedded JSON object from prose (handles nested braces)
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            return _extract(json.loads(content[start : end + 1]))
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    # 3. Full fallback
    return "training", original_query


async def router_node(state: AgentState) -> dict:
    """LangGraph node: classify user intent and refine the query."""
    query = state["user_query"]
    client = get_llm_client()

    content = await call_llm(
        client,
        [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0,
        max_tokens=150,
    )

    agent, refined_query = parse_router_response(content, query)
    return {
        "routed_agent": agent,
        "refined_query": refined_query,
    }


def route_by_agent(state: AgentState) -> str:
    """LangGraph conditional edge function — reads routed_agent from state."""
    return state.get("routed_agent", "training")

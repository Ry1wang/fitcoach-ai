"""LangGraph shared state schema for the multi-agent pipeline."""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ── Input (populated before graph invocation) ──────────────────────────
    user_query: str
    chat_history: list[dict]       # previous messages: [{"role": ..., "content": ...}]
    user_id: str                   # UUID string of the authenticated user
    session: Any                   # AsyncSession — passed through, never serialized

    # ── Router output ───────────────────────────────────────────────────────
    routed_agent: str              # "training" | "rehab" | "nutrition"
    refined_query: str             # query rewritten for optimal retrieval

    # ── Retrieval output ────────────────────────────────────────────────────
    retrieved_chunks: list[dict]   # top-K chunks returned by pgvector

    # ── Generation output ───────────────────────────────────────────────────
    response: str                  # final LLM-generated answer
    sources: list[dict]            # formatted source citations
    disclaimer: str | None         # medical disclaimer (rehab agent only)

    # ── Metadata ────────────────────────────────────────────────────────────
    agent_used: str
    latency_ms: int

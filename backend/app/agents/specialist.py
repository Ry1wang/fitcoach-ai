"""Specialist agent nodes: Training, Rehab, Nutrition.

Each node follows the same three-step pattern:
  1. Retrieve relevant chunks (pgvector, user-scoped)
  2. Build prompt with retrieved context
  3. Call LLM and return state updates
"""
import uuid
from typing import Any

from app.agents.prompts import (
    NUTRITION_SYSTEM_PROMPT,
    REHAB_DISCLAIMER,
    REHAB_SYSTEM_PROMPT,
    TRAINING_SYSTEM_PROMPT,
)
from app.agents.state import AgentState
from app.deps import get_llm_client
from app.rag.retriever import ChunkResult, retrieve
from app.services.llm_service import call_llm


def _format_sources(chunks: list[ChunkResult]) -> list[dict[str, Any]]:
    """Convert ChunkResult objects to the sources schema used by messages.sources."""
    sources = []
    for chunk in chunks:
        meta = chunk.chunk_metadata or {}
        sources.append(
            {
                "chunk_id": str(chunk.id),
                "content_preview": chunk.content[:100],
                "source_book": meta.get("source_book", ""),
                "chapter": meta.get("chapter", ""),
                "section": meta.get("section", ""),
                "relevance_score": round(chunk.relevance_score, 4),
            }
        )
    return sources


def _build_context(chunks: list[ChunkResult]) -> str:
    """Format retrieved chunks into a context block for the LLM prompt."""
    if not chunks:
        return "（暂无相关参考资料）"
    parts = []
    for chunk in chunks:
        meta = chunk.chunk_metadata or {}
        book = meta.get("source_book", "未知来源")
        chapter = meta.get("chapter", "")
        label = f"[来源: {book}" + (f" {chapter}" if chapter else "") + "]"
        parts.append(f"{label}\n{chunk.content}")
    return "\n\n---\n\n".join(parts)


async def _run_specialist(
    state: AgentState,
    *,
    system_prompt: str,
    domain: str | None,
    disclaimer: str | None = None,
) -> dict:
    """Shared logic for all three specialist agents."""
    refined_query = state.get("refined_query") or state["user_query"]
    user_id = uuid.UUID(state["user_id"])
    session = state["session"]
    chat_history: list[dict] = state.get("chat_history") or []

    # 1. Retrieve relevant chunks
    chunks = await retrieve(
        refined_query,
        user_id,
        session,
        content_domain=domain,
    )

    # 2. Build prompt
    context = _build_context(chunks)
    user_msg = (
        f"参考资料：\n{context}\n\n"
        f"用户问题：{refined_query}\n\n"
        "请根据以上参考资料回答用户问题，并标注信息来源（书名和章节）。\n"
        "如果参考资料中没有相关内容，请如实说明。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        *chat_history,
        {"role": "user", "content": user_msg},
    ]

    # 3. Call LLM
    client = get_llm_client()
    response = await call_llm(client, messages)

    if disclaimer:
        response = response + disclaimer

    agent_name = domain or "training"
    return {
        "retrieved_chunks": [
            {
                "content": c.content,
                "chunk_type": c.chunk_type,
                "chunk_metadata": c.chunk_metadata,
                "relevance_score": c.relevance_score,
            }
            for c in chunks
        ],
        "response": response,
        "sources": _format_sources(chunks),
        "disclaimer": disclaimer,
        "agent_used": agent_name,
    }


async def training_node(state: AgentState) -> dict:
    return await _run_specialist(
        state,
        system_prompt=TRAINING_SYSTEM_PROMPT,
        domain="training",
    )


async def rehab_node(state: AgentState) -> dict:
    return await _run_specialist(
        state,
        system_prompt=REHAB_SYSTEM_PROMPT,
        domain="rehab",
        disclaimer=REHAB_DISCLAIMER,
    )


async def nutrition_node(state: AgentState) -> dict:
    return await _run_specialist(
        state,
        system_prompt=NUTRITION_SYSTEM_PROMPT,
        domain="nutrition",
    )

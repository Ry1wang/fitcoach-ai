"""POST /chat — SSE streaming chat endpoint with Redis caching and rate limiting.
POST /chat/sync — Non-streaming JSON endpoint for OpenClaw / Feishu bot integration.
"""
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import (
    NUTRITION_SYSTEM_PROMPT,
    REHAB_DISCLAIMER,
    REHAB_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    TRAINING_SYSTEM_PROMPT,
)
from app.agents.router import parse_router_response
from app.config import settings
from app.deps import get_current_user, get_llm_client, get_redis, get_session
from app.models.user import User
from app.rag.retriever import ChunkResult, retrieve
from app.schemas.chat import ChatRequest
from app.services.cache_service import CacheService
from app.services.conversation_service import (
    get_or_create_conversation,
    get_recent_messages,
    save_message,
    update_conversation_title,
)
from app.services.llm_service import call_llm
from app.services.rate_limiter import RateLimiter

router = APIRouter(prefix="/chat", tags=["chat"])

_AGENT_PROMPTS: dict[str, str] = {
    "training": TRAINING_SYSTEM_PROMPT,
    "rehab": REHAB_SYSTEM_PROMPT,
    "nutrition": NUTRITION_SYSTEM_PROMPT,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _format_sources(chunks: list[ChunkResult]) -> list[dict]:
    sources = []
    for c in chunks:
        meta = c.chunk_metadata or {}
        sources.append(
            {
                "chunk_id": str(c.id),
                "content_preview": c.content[:100],
                "source_book": meta.get("source_book", ""),
                "chapter": meta.get("chapter", ""),
                "relevance_score": round(c.relevance_score, 4),
            }
        )
    return sources


def _build_context(chunks: list[ChunkResult]) -> str:
    if not chunks:
        return "（暂无相关参考资料）"
    parts = []
    for c in chunks:
        meta = c.chunk_metadata or {}
        book = meta.get("source_book", "未知来源")
        chapter = meta.get("chapter", "")
        label = f"[来源: {book}" + (f" {chapter}" if chapter else "") + "]"
        parts.append(f"{label}\n{c.content}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# SSE stream generator
# ---------------------------------------------------------------------------


async def _generate_events(
    *,
    request: ChatRequest,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    history_dicts: list[dict],
    is_first: bool,
    session: AsyncSession,
    redis,
) -> AsyncGenerator[str, None]:
    start = time.time()
    cache = CacheService(redis, ttl=settings.CACHE_TTL_SECONDS)

    try:
        # ── Cache hit path (first-message queries only) ────────────────────
        if is_first:
            cached = await cache.get(request.message, str(user_id))
            if cached:
                await cache.track_hit()
                yield _sse(
                    {
                        "type": "routing",
                        "agent": cached["agent_used"],
                        "refined_query": cached.get("refined_query", request.message),
                        "cached": True,
                    }
                )
                yield _sse({"type": "sources", "chunks": cached["sources"]})
                yield _sse({"type": "token", "content": cached["response"]})
                yield _sse(
                    {
                        "type": "done",
                        "agent_used": cached["agent_used"],
                        "latency_ms": 0,
                        "conversation_id": str(conversation_id),
                        "cached": True,
                    }
                )
                await save_message(
                    session,
                    conversation_id,
                    "assistant",
                    cached["response"],
                    agent_used=cached["agent_used"],
                    sources=cached["sources"],
                    latency_ms=0,
                )
                return
            await cache.track_miss()

        # ── Router ─────────────────────────────────────────────────────────
        client = get_llm_client()
        router_content = await call_llm(
            client,
            [
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": request.message},
            ],
            temperature=0,
            max_tokens=150,
        )
        agent, refined_query = parse_router_response(router_content, request.message)
        yield _sse({"type": "routing", "agent": agent, "refined_query": refined_query})

        # ── Retrieve ───────────────────────────────────────────────────────
        chunks = await retrieve(
            refined_query,
            user_id,
            session,
            content_domain=agent,
        )
        sources = _format_sources(chunks)
        yield _sse({"type": "sources", "chunks": sources})

        # ── Generate (token streaming) ─────────────────────────────────────
        context = _build_context(chunks)
        system_prompt = _AGENT_PROMPTS.get(agent, TRAINING_SYSTEM_PROMPT)
        user_msg = (
            f"参考资料：\n{context}\n\n"
            f"用户问题：{refined_query}\n\n"
            "请根据参考资料回答，并标注信息来源（书名和章节）。\n"
            "如果参考资料中没有相关内容，请如实说明。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            *history_dicts,
            {"role": "user", "content": user_msg},
        ]

        full_response = ""
        stream = await client.chat.completions.create(
            model=settings.LLM_CHAT_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            stream=True,
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                full_response += token
                yield _sse({"type": "token", "content": token})

        # Rehab mandatory disclaimer
        if agent == "rehab":
            full_response += REHAB_DISCLAIMER
            yield _sse({"type": "token", "content": REHAB_DISCLAIMER})

        # ── Persist + cache (before done — so client disconnect won't lose data)
        latency = int((time.time() - start) * 1000)
        await save_message(
            session,
            conversation_id,
            "assistant",
            full_response,
            agent_used=agent,
            sources=sources,
            latency_ms=latency,
        )
        if is_first:
            await cache.set(
                request.message,
                str(user_id),
                {"response": full_response, "sources": sources, "agent_used": agent, "refined_query": refined_query},
            )

        # ── Done ───────────────────────────────────────────────────────────
        yield _sse(
            {
                "type": "done",
                "agent_used": agent,
                "latency_ms": latency,
                "conversation_id": str(conversation_id),
            }
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("SSE stream error for user_id=%s conversation_id=%s", user_id, conversation_id)
        yield _sse({"type": "error", "message": str(exc), "code": "INTERNAL_ERROR"})


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    redis = get_redis()

    # Rate limit check
    limiter = RateLimiter(redis, max_requests=settings.RATE_LIMIT_PER_MINUTE)
    if not await limiter.check(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": f"Maximum {settings.RATE_LIMIT_PER_MINUTE} requests per minute",
            },
            headers={"Retry-After": "60"},
        )

    # Validate / create conversation (before streaming so 404 is a proper HTTP error)
    conv = await get_or_create_conversation(
        session, request.conversation_id, current_user.id
    )
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Conversation not found"},
        )

    # Load history before persisting the new user message
    history = await get_recent_messages(session, conv.id, limit=10)
    history_dicts = [{"role": m.role, "content": m.content} for m in history]
    is_first = len(history) == 0

    # Persist user message
    await save_message(session, conv.id, "user", request.message)

    # Auto-title the conversation from the first user message
    if is_first:
        await update_conversation_title(session, conv.id, request.message[:100])

    return StreamingResponse(
        _generate_events(
            request=request,
            user_id=current_user.id,
            conversation_id=conv.id,
            history_dicts=history_dicts,
            is_first=is_first,
            session=session,
            redis=redis,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/sync", summary="Non-streaming chat for bot integrations (OpenClaw/Feishu)")
async def chat_sync(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Collects the full SSE stream internally and returns a single JSON response.
    Intended for OpenClaw / Feishu bot — no SSE handling required on the client side.
    """
    redis = get_redis()

    limiter = RateLimiter(redis, max_requests=settings.RATE_LIMIT_PER_MINUTE)
    if not await limiter.check(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "RATE_LIMIT_EXCEEDED", "message": f"Maximum {settings.RATE_LIMIT_PER_MINUTE} requests per minute"},
            headers={"Retry-After": "60"},
        )

    conv = await get_or_create_conversation(session, request.conversation_id, current_user.id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Conversation not found"},
        )

    history = await get_recent_messages(session, conv.id, limit=10)
    history_dicts = [{"role": m.role, "content": m.content} for m in history]
    is_first = len(history) == 0

    await save_message(session, conv.id, "user", request.message)
    if is_first:
        await update_conversation_title(session, conv.id, request.message[:100])

    # Consume the SSE generator and collect the final result
    reply = ""
    agent_used = "training"
    sources: list[dict] = []
    latency_ms = 0

    async for raw in _generate_events(
        request=request,
        user_id=current_user.id,
        conversation_id=conv.id,
        history_dicts=history_dicts,
        is_first=is_first,
        session=session,
        redis=redis,
    ):
        # raw is "data: {...}\n\n"
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[len("data:"):].strip())
        except json.JSONDecodeError:
            continue

        etype = event.get("type")
        if etype == "token":
            reply += event.get("content", "")
        elif etype == "sources":
            sources = event.get("chunks", [])
        elif etype == "done":
            agent_used = event.get("agent_used", agent_used)
            latency_ms = event.get("latency_ms", 0)
        elif etype == "error":
            raise HTTPException(status_code=500, detail=event.get("message", "Internal error"))

    return JSONResponse({
        "reply": reply,
        "agent_used": agent_used,
        "sources": sources,
        "conversation_id": str(conv.id),
        "latency_ms": latency_ms,
    })

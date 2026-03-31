"""OpenAI-compatible /v1/chat/completions for OpenClaw/Feishu integration."""
import json
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import _generate_events
from app.config import settings
from app.deps import get_redis, get_session
from app.schemas.chat import ChatRequest
from app.services.auth_service import get_user_by_id
from app.services.conversation_service import (
    get_or_create_conversation,
    get_recent_messages,
    save_message,
    update_conversation_title,
)

router = APIRouter(
    prefix="/v1",
    tags=["compat"],
    responses={401: {"description": "Invalid or missing BOT_API_KEY"}},
)


class _Msg(BaseModel):
    role: str
    content: str


class _OAIRequest(BaseModel):
    model: str = "fitcoach"
    messages: list[_Msg]


@router.post(
    "/chat/completions",
    summary="OpenAI-compatible chat (Feishu/OpenClaw)",
    description=(
        "Accepts an OpenAI-style chat completions request and returns a non-streaming JSON response. "
        "Used by OpenClaw to relay Feishu messages to FitCoach RAG. "
        "Authenticate with `Authorization: Bearer <BOT_API_KEY>`."
    ),
)
async def openai_compat(
    body: _OAIRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    # Verify static bot API key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not settings.BOT_API_KEY or authorization[7:] != settings.BOT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Look up bot user
    if not settings.BOT_USER_ID:
        raise HTTPException(status_code=500, detail="BOT_USER_ID not configured")
    bot_user = await get_user_by_id(session, uuid.UUID(settings.BOT_USER_ID))
    if bot_user is None or not bot_user.is_active:
        raise HTTPException(status_code=500, detail="Bot user not found")

    # Extract latest user message
    user_content = next(
        (m.content for m in reversed(body.messages) if m.role == "user"), None
    )
    if not user_content:
        raise HTTPException(status_code=400, detail="No user message")

    redis = get_redis()
    chat_req = ChatRequest(message=user_content, conversation_id=None)
    conv = await get_or_create_conversation(session, None, bot_user.id)
    history = await get_recent_messages(session, conv.id, limit=10)
    history_dicts = [{"role": m.role, "content": m.content} for m in history]
    is_first = len(history) == 0
    await save_message(session, conv.id, "user", user_content)
    if is_first:
        await update_conversation_title(session, conv.id, user_content[:100])

    reply = ""
    error_msg: str | None = None
    async for raw in _generate_events(
        request=chat_req,
        user_id=bot_user.id,
        conversation_id=conv.id,
        history_dicts=history_dicts,
        is_first=is_first,
        session=session,
        redis=redis,
    ):
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if event.get("type") == "token":
            reply += event.get("content", "")
        elif event.get("type") == "error":
            error_msg = event.get("message", "内部错误")

    if error_msg and not reply:
        raise HTTPException(status_code=500, detail=error_msg)

    return JSONResponse({
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": reply},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })

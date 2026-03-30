import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_session
from app.models.user import User
from app.services.conversation_service import (
    delete_conversation,
    get_conversation_messages,
    list_conversations,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ── Schemas ────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    agent_used: str | None = None
    sources: list[dict] | None = None
    latency_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: uuid.UUID
    title: str | None = None
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
    total: int


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=ConversationListResponse)
async def list_user_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    convs = await list_conversations(session, current_user.id)
    return ConversationListResponse(
        conversations=[ConversationSummary.model_validate(c) for c in convs],
        total=len(convs),
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select as sa_select
    from app.models.conversation import Conversation

    # Fetch conversation (for title) and messages in one go
    stmt = sa_select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    )
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Conversation not found"},
        )

    messages = await get_conversation_messages(session, conversation_id, current_user.id)
    return ConversationDetail(
        id=conversation_id,
        title=conv.title,
        messages=[MessageResponse.model_validate(m) for m in messages or []],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    deleted = await delete_conversation(session, conversation_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Conversation not found"},
        )

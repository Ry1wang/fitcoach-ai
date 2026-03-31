"""CRUD helpers for Conversation and Message models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.models.conversation import Conversation
from app.models.message import Message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def get_or_create_conversation(
    session: AsyncSession,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> Conversation | None:
    """Return an existing conversation or create a new one.

    Returns None if conversation_id is given but not found / not owned by user.
    """
    if conversation_id is not None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()
        return conv  # None signals "not found" to the caller

    conv = Conversation(user_id=user_id)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def update_conversation_title(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    title: str,
) -> None:
    """Set the conversation title (called after first user message is known)."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if conv and not conv.title:
        conv.title = title[:255]
        conv.updated_at = _utcnow()
        session.add(conv)
        await session.commit()


async def save_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    *,
    agent_used: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    latency_ms: int | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        agent_used=agent_used,
        sources=sources,
        latency_ms=latency_ms,
        created_at=_utcnow(),
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_recent_messages(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    limit: int = 10,
) -> list[Message]:
    """Return the last `limit` messages in chronological order (oldest first)."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    return list(reversed(messages))  # oldest first


async def list_conversations(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[Conversation]:
    """Return all conversations for a user, newest first."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_conversation_messages(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[Message] | None:
    """Return all messages for a conversation owned by user. None if not found."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        return None

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_conversation(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Delete a conversation owned by user. Returns False if not found."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if conv is None:
        return False
    await session.delete(conv)
    await session.commit()
    return True

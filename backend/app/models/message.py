import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversations.id")
    role: str = Field(max_length=20)
    content: str
    agent_used: str | None = Field(default=None, max_length=50)
    sources: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column("sources", JSONB)
    )
    latency_ms: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)

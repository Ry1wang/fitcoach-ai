import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    title: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

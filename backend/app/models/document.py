import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    filename: str = Field(max_length=255)
    file_path: str = Field(max_length=500)
    file_size: int | None = Field(default=None)
    domain: str | None = Field(default=None, max_length=50)
    chunk_count: int = Field(default=0)
    status: str = Field(default="pending", max_length=20)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

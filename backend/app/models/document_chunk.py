import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="documents.id")
    content: str = Field(sa_column=Column(Text, nullable=False))
    chunk_index: int
    chunk_type: str | None = Field(default=None, max_length=50)
    # "metadata" is reserved by SQLAlchemy Declarative API; use chunk_metadata as the
    # Python attribute name while mapping to the "metadata" column in the DB.
    chunk_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column("metadata", JSONB)
    )
    embedding: Any = Field(
        default=None,
        sa_column=Column(Vector(settings.EMBEDDING_DIMENSION)),
    )
    created_at: datetime = Field(default_factory=_utcnow)

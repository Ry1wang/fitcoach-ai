import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def create_document(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    filename: str,
    file_path: str,
    file_size: int | None = None,
    domain: str | None = None,
) -> Document:
    doc = Document(
        user_id=user_id,
        filename=filename,
        file_path=file_path,
        file_size=file_size,
        domain=domain,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def get_document_by_id(
    session: AsyncSession, doc_id: uuid.UUID, user_id: uuid.UUID
) -> Document | None:
    stmt = select(Document).where(Document.id == doc_id, Document.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_documents(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_document_status(
    session: AsyncSession,
    doc_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    status: str,
    error_message: str | None = None,
    chunk_count: int | None = None,
) -> Document | None:
    doc = await get_document_by_id(session, doc_id, user_id)
    if doc is None:
        return None
    doc.status = status
    doc.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if error_message is not None:
        doc.error_message = error_message
    if chunk_count is not None:
        doc.chunk_count = chunk_count
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def delete_document(
    session: AsyncSession, doc_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    doc = await get_document_by_id(session, doc_id, user_id)
    if doc is None:
        return False
    await session.delete(doc)
    await session.commit()
    return True

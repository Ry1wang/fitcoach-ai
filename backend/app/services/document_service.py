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


async def reset_stuck_processing_documents(session: AsyncSession) -> list[uuid.UUID]:
    """Find documents stuck in 'processing' state and mark them 'failed'.

    Called on backend startup: a fresh uvicorn process cannot have any
    real in-flight ingestion, so any row still at 'processing' must be a
    leftover from a previous crash (OOM kill, manual restart, host reboot).
    Marking them 'failed' gives the user visible feedback and unblocks the
    retry endpoint.

    Returns the list of document IDs that were reset.
    """
    stmt = select(Document).where(Document.status == "processing")
    result = await session.execute(stmt)
    stuck = list(result.scalars().all())
    if not stuck:
        return []

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reset_ids: list[uuid.UUID] = []
    for doc in stuck:
        doc.status = "failed"
        doc.error_message = (
            "Ingestion interrupted by server restart (likely OOM or crash). "
            "Please retry."
        )
        doc.updated_at = now
        session.add(doc)
        reset_ids.append(doc.id)
    await session.commit()
    return reset_ids


async def delete_document(
    session: AsyncSession, doc_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    doc = await get_document_by_id(session, doc_id, user_id)
    if doc is None:
        return False
    await session.delete(doc)
    await session.commit()
    return True

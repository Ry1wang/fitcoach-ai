import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from app.services.document_service import (
    create_document,
    delete_document,
    get_document_by_id,
    list_documents,
    update_document_status,
)
from app.services.pipeline import run_ingestion_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])

_VALID_DOMAINS = {"training", "rehab", "nutrition"}


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    domain: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Validate file extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_FILE_TYPE",
                "message": f"Only {settings.ALLOWED_EXTENSIONS} files are accepted",
            },
        )

    # Validate domain value
    if domain is not None and domain not in _VALID_DOMAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_DOMAIN",
                "message": f"domain must be one of: {sorted(_VALID_DOMAINS)}",
            },
        )

    # Save file to disk via streaming (avoids loading entire file into memory)
    user_dir = Path(settings.UPLOAD_DIR) / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    doc_uuid = uuid.uuid4()
    file_path = user_dir / f"{doc_uuid}{suffix}"
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    try:
        file_size = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 64)  # 64 KB chunks
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_bytes:
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "FILE_TOO_LARGE",
                            "message": f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB limit",
                        },
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception:
        # Clean up partial file on write failure
        file_path.unlink(missing_ok=True)
        raise

    file_path_str = str(file_path)

    # Create pending DB record
    doc = await create_document(
        session,
        user_id=current_user.id,
        filename=file.filename or f"{doc_uuid}{suffix}",
        file_path=file_path_str,
        file_size=file_size,
        domain=domain,
    )

    # Enqueue background ingestion
    background_tasks.add_task(
        run_ingestion_pipeline,
        doc_id=doc.id,
        user_id=current_user.id,
        file_path=file_path_str,
        filename=doc.filename,
        domain=domain,
    )

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        created_at=doc.created_at,
    )


@router.get("", response_model=DocumentListResponse)
async def list_user_documents(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    docs = await list_documents(session, current_user.id)
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await get_document_by_id(session, document_id, current_user.id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Document not found"},
        )
    return DocumentResponse.model_validate(doc)


@router.post(
    "/{document_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentUploadResponse,
)
async def retry_document_ingestion(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retry ingestion for a document previously left in 'failed' state.

    Common causes for 'failed' state: OOM kill, server restart during
    ingestion, transient parsing/embedding errors. The original uploaded
    file is still on disk (delete_document removes it), so we simply
    reset the status to 'pending' and re-enqueue the pipeline.
    """
    doc = await get_document_by_id(session, document_id, current_user.id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Document not found"},
        )

    if doc.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "INVALID_STATUS",
                "message": (
                    f"Only 'failed' documents can be retried; current status is "
                    f"'{doc.status}'"
                ),
            },
        )

    # Verify the file still exists on disk — otherwise retry is impossible.
    if not doc.file_path or not Path(doc.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "error": "FILE_MISSING",
                "message": "Original upload file is no longer on disk; please re-upload",
            },
        )

    # Reset status + clear previous error, then re-enqueue.
    await update_document_status(
        session,
        document_id,
        current_user.id,
        status="pending",
        error_message="",  # clear the stale error; update_document_status only updates if not None
    )

    background_tasks.add_task(
        run_ingestion_pipeline,
        doc_id=doc.id,
        user_id=current_user.id,
        file_path=doc.file_path,
        filename=doc.filename,
        domain=doc.domain,
    )

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        status="pending",
        created_at=doc.created_at,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await get_document_by_id(session, document_id, current_user.id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Document not found"},
        )

    saved_path = doc.file_path
    deleted = await delete_document(session, document_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Document not found"},
        )

    # Best-effort disk cleanup — validate path is within upload directory first
    try:
        if saved_path:
            upload_dir = Path(settings.UPLOAD_DIR).resolve()
            target = Path(saved_path).resolve()
            if target.is_relative_to(upload_dir) and target.exists():
                target.unlink()
    except OSError:
        pass

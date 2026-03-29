"""Integration tests for document ingestion endpoints.

Tests cover POST /upload, GET /documents, GET /documents/{id}, DELETE /documents/{id}.
Real test DB; background pipeline is mocked to avoid LLM/embedding calls.
"""
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_pdf_bytes() -> bytes:
    """Minimal valid-looking PDF content (just needs .pdf extension to pass)."""
    return b"%PDF-1.4 fake content for testing"


def _upload(client, auth_headers, *, filename="test.pdf", domain=None, content=None):
    """Helper that returns an awaitable POST to /upload."""
    data = {}
    if domain is not None:
        data["domain"] = domain
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, io.BytesIO(content or _fake_pdf_bytes()), "application/pdf")},
        data=data,
        headers=auth_headers,
    )


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


async def test_upload_no_auth_returns_401(client):
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", io.BytesIO(_fake_pdf_bytes()), "application/pdf")},
    )
    assert response.status_code == 401


async def test_upload_success_returns_202(client, auth_headers):
    """Upload a valid PDF — should return 202 with pending status."""
    with patch("app.api.documents.run_ingestion_pipeline", new_callable=AsyncMock):
        response = await _upload(client, auth_headers)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["filename"] == "test.pdf"
    assert "id" in data
    assert "created_at" in data


async def test_upload_with_domain(client, auth_headers):
    with patch("app.api.documents.run_ingestion_pipeline", new_callable=AsyncMock):
        response = await _upload(client, auth_headers, domain="training")

    assert response.status_code == 202


async def test_upload_invalid_extension_returns_400(client, auth_headers):
    response = await _upload(client, auth_headers, filename="notes.txt")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_FILE_TYPE"


async def test_upload_invalid_domain_returns_400(client, auth_headers):
    response = await _upload(client, auth_headers, domain="cardio")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "INVALID_DOMAIN"


async def test_upload_oversized_file_returns_400(client, auth_headers):
    """A file exceeding MAX_FILE_SIZE_MB should be rejected."""
    with patch("app.config.settings.MAX_FILE_SIZE_MB", 0):
        response = await _upload(client, auth_headers)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "FILE_TOO_LARGE"


# ---------------------------------------------------------------------------
# List tests
# ---------------------------------------------------------------------------


async def test_list_documents_empty(client, auth_headers):
    response = await client.get("/api/v1/documents", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["documents"] == []
    assert data["total"] == 0


async def test_list_documents_after_upload(client, auth_headers):
    with patch("app.api.documents.run_ingestion_pipeline", new_callable=AsyncMock):
        await _upload(client, auth_headers, filename="book1.pdf")
        await _upload(client, auth_headers, filename="book2.pdf")

    response = await client.get("/api/v1/documents", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    filenames = {d["filename"] for d in data["documents"]}
    assert filenames == {"book1.pdf", "book2.pdf"}


async def test_list_documents_no_auth_returns_401(client):
    response = await client.get("/api/v1/documents")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Get single document tests
# ---------------------------------------------------------------------------


async def test_get_document_by_id(client, auth_headers):
    with patch("app.api.documents.run_ingestion_pipeline", new_callable=AsyncMock):
        upload_res = await _upload(client, auth_headers)
    doc_id = upload_res.json()["id"]

    response = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["filename"] == "test.pdf"
    assert data["status"] == "pending"
    assert data["chunk_count"] == 0


async def test_get_document_not_found_returns_404(client, auth_headers):
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/documents/{fake_id}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------


async def test_delete_document_success(client, auth_headers):
    with patch("app.api.documents.run_ingestion_pipeline", new_callable=AsyncMock):
        upload_res = await _upload(client, auth_headers)
    doc_id = upload_res.json()["id"]

    response = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert response.status_code == 204

    # Confirm it's gone
    get_res = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert get_res.status_code == 404


async def test_delete_nonexistent_returns_404(client, auth_headers):
    fake_id = str(uuid.uuid4())
    response = await client.delete(f"/api/v1/documents/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Resource isolation tests
# ---------------------------------------------------------------------------


async def test_user_cannot_see_other_users_documents(client, db_session, auth_headers):
    """Documents uploaded by user A must not appear in user B's list."""
    # User A uploads a document
    with patch("app.api.documents.run_ingestion_pipeline", new_callable=AsyncMock):
        await _upload(client, auth_headers, filename="private.pdf")

    # Create user B and get their token
    from app.services.auth_service import create_access_token, create_user, hash_password

    user_b = await create_user(
        db_session,
        username="userB",
        email="b@example.com",
        hashed_password=hash_password("password123"),
    )
    headers_b = {"Authorization": f"Bearer {create_access_token(str(user_b.id))}"}

    # User B should see zero documents
    response = await client.get("/api/v1/documents", headers=headers_b)
    assert response.status_code == 200
    assert response.json()["total"] == 0

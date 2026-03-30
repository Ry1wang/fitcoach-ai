"""Integration tests for the Conversation API endpoints."""
import pytest
from httpx import AsyncClient

from app.models.conversation import Conversation
from app.models.message import Message
from app.services.auth_service import create_access_token, create_user, hash_password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_conversation_with_messages(db_session, user_id, title="测试对话"):
    """Insert a conversation with two messages for testing."""
    conv = Conversation(user_id=user_id, title=title)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        content="引体向上怎么练？",
    )
    msg2 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="建议从悬挂开始训练...",
        agent_used="training",
        sources=[{"source_book": "囚徒健身", "chapter": "第5章"}],
        latency_ms=1200,
    )
    db_session.add_all([msg1, msg2])
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


# ---------------------------------------------------------------------------
# List conversations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient, auth_headers):
    res = await client.get("/api/v1/conversations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["conversations"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_conversations_with_data(
    client: AsyncClient, auth_headers, sample_user, db_session
):
    await _create_conversation_with_messages(db_session, sample_user.id, "对话一")
    await _create_conversation_with_messages(db_session, sample_user.id, "对话二")

    res = await client.get("/api/v1/conversations", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    # newest first
    titles = [c["title"] for c in data["conversations"]]
    assert "对话一" in titles
    assert "对话二" in titles


@pytest.mark.asyncio
async def test_list_conversations_no_auth(client: AsyncClient):
    res = await client.get("/api/v1/conversations")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Get conversation detail (with messages)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_conversation_with_messages(
    client: AsyncClient, auth_headers, sample_user, db_session
):
    conv = await _create_conversation_with_messages(db_session, sample_user.id)

    res = await client.get(
        f"/api/v1/conversations/{conv.id}", headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(conv.id)
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["agent_used"] == "training"
    assert data["messages"][1]["sources"] is not None


@pytest.mark.asyncio
async def test_get_conversation_not_found(client: AsyncClient, auth_headers):
    import uuid

    fake_id = uuid.uuid4()
    res = await client.get(
        f"/api/v1/conversations/{fake_id}", headers=auth_headers
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Delete conversation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_conversation(
    client: AsyncClient, auth_headers, sample_user, db_session
):
    conv = await _create_conversation_with_messages(db_session, sample_user.id)

    res = await client.delete(
        f"/api/v1/conversations/{conv.id}", headers=auth_headers
    )
    assert res.status_code == 204

    # Verify it's gone
    res = await client.get(
        f"/api/v1/conversations/{conv.id}", headers=auth_headers
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_not_found(client: AsyncClient, auth_headers):
    import uuid

    fake_id = uuid.uuid4()
    res = await client.delete(
        f"/api/v1/conversations/{fake_id}", headers=auth_headers
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Resource isolation — user A cannot see user B's conversations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resource_isolation(client: AsyncClient, sample_user, db_session):
    # Create conversation for sample_user (user A)
    conv = await _create_conversation_with_messages(db_session, sample_user.id)

    # Create user B
    user_b = await create_user(
        db_session,
        username="userb",
        email="userb@example.com",
        hashed_password=hash_password("password123"),
    )
    token_b = create_access_token(str(user_b.id))
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B should not see user A's conversations
    res = await client.get("/api/v1/conversations", headers=headers_b)
    assert res.status_code == 200
    assert res.json()["total"] == 0

    # User B should get 404 on user A's conversation
    res = await client.get(
        f"/api/v1/conversations/{conv.id}", headers=headers_b
    )
    assert res.status_code == 404

    # User B should not be able to delete user A's conversation
    res = await client.delete(
        f"/api/v1/conversations/{conv.id}", headers=headers_b
    )
    assert res.status_code == 404

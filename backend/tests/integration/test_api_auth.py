import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    res = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "password123",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, sample_user):
    res = await client.post("/api/v1/auth/register", json={
        "username": "another",
        "email": "test@example.com",  # same email as sample_user
        "password": "password123",
    })
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "CONFLICT"


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient):
    res = await client.post("/api/v1/auth/register", json={
        "username": "user",
        "email": "short@example.com",
        "password": "abc",  # < 6 chars
    })
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, sample_user):
    res = await client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "testpass123",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, sample_user):
    res = await client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "wrongpassword",
    })
    assert res.status_code == 401
    assert res.json()["detail"]["error"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    res = await client.post("/api/v1/auth/login", data={
        "username": "nobody@example.com",
        "password": "password123",
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, sample_user, auth_headers):
    res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == sample_user.email
    assert data["username"] == sample_user.username


@pytest.mark.asyncio
async def test_get_me_no_token(client: AsyncClient):
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client: AsyncClient):
    res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_register_then_login_flow(client: AsyncClient):
    """Full flow: register → login → access /me."""
    await client.post("/api/v1/auth/register", json={
        "username": "flowuser",
        "email": "flow@example.com",
        "password": "flowpass123",
    })
    login_res = await client.post("/api/v1/auth/login", data={
        "username": "flow@example.com",
        "password": "flowpass123",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "flow@example.com"

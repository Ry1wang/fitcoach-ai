import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models import Conversation, Document, DocumentChunk, Message, User  # noqa: F401
from app.services.auth_service import create_access_token, create_user, hash_password

# postgres-test is on the same Docker network with explicit `networks: [default]`.
# Inside Docker: postgres-test:5432. Outside Docker: set TEST_DATABASE_URL=localhost:5433/...
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fitcoach:fitcoach_dev@postgres-test:5432/fitcoach_test?ssl=disable",
)


# ---------- Database ----------

@pytest_asyncio.fixture
async def db_session():
    """Per-test engine + session; tables are created and dropped per test run."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


# ---------- HTTP Client ----------

@pytest_asyncio.fixture
async def client(db_session):
    from app.main import app
    from app.deps import get_session

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------- Auth ----------

@pytest_asyncio.fixture
async def sample_user(db_session):
    user = await create_user(
        db_session,
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpass123"),
    )
    return user


@pytest.fixture
def auth_headers(sample_user):
    token = create_access_token(str(sample_user.id))
    return {"Authorization": f"Bearer {token}"}

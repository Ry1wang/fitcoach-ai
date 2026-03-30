import uuid
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=False,
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


# ── Singleton clients ─────────────────────────────────────────────────────

_llm_client: AsyncOpenAI | None = None
_redis_client: aioredis.Redis | None = None


def get_llm_client() -> AsyncOpenAI:
    """Singleton LLM chat client (reuses HTTP connection pool)."""
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _llm_client


def get_redis() -> aioredis.Redis:
    """Singleton Redis client (reuses connection pool)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """Shutdown hook — close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
):
    from app.services.auth_service import decode_access_token, get_user_by_id

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Invalid token payload"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_id(session, uid)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "User not found or inactive"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

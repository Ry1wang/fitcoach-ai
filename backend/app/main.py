import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy import text

from app.api import auth as auth_router
from app.api import chat as chat_router
from app.api import compat as compat_router
from app.api import conversations as conversations_router
from app.api import documents as documents_router
from app.deps import async_session, close_redis, engine, get_redis
from app.services.document_service import reset_stuck_processing_documents

# Ensure ingestion pipeline progress logs (INFO) are visible.
# Uvicorn's default log config leaves application loggers at WARNING;
# without this line the step-by-step chunking / embedding / insert
# messages in pipeline.py are silently swallowed.
logging.getLogger("app.services.pipeline").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify DB and Redis connections on startup; clean up on shutdown."""
    # Database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("✓ Database connection verified")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")

    # Redis
    try:
        r = get_redis()
        await r.ping()
        print("✓ Redis connection verified")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")

    # Recover documents stuck in 'processing' from a previous crash/OOM.
    # This is safe because a fresh uvicorn process cannot have real
    # in-flight ingestion — any such row must be a leftover.
    try:
        async with async_session() as session:
            reset_ids = await reset_stuck_processing_documents(session)
        if reset_ids:
            logger.warning(
                "Reset %d stuck 'processing' document(s) to 'failed': %s",
                len(reset_ids),
                [str(i) for i in reset_ids],
            )
            print(f"✓ Recovered {len(reset_ids)} stuck document(s) → failed")
        else:
            print("✓ No stuck documents to recover")
    except Exception as e:
        print(f"✗ Stuck-document recovery failed: {e}")

    yield

    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="FitCoach AI",
    description="Fitness knowledge assistant powered by RAG + multi-agent architecture",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(documents_router.router, prefix="/api/v1")
app.include_router(chat_router.router, prefix="/api/v1")
app.include_router(conversations_router.router, prefix="/api/v1")
app.include_router(compat_router.router)


@app.get("/health")
async def health_check():
    """Service health check — probes database and Redis."""
    checks = {}

    # Database
    try:
        start = datetime.now(timezone.utc)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        checks["database"] = {"status": "up", "latency_ms": round(latency_ms, 1)}
    except Exception as e:
        checks["database"] = {"status": "down", "error": str(e)}

    # Redis
    try:
        r = get_redis()
        start = datetime.now(timezone.utc)
        await r.ping()
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        checks["redis"] = {"status": "up", "latency_ms": round(latency_ms, 1)}
    except Exception as e:
        checks["redis"] = {"status": "down", "error": str(e)}

    overall = "healthy" if all(c["status"] == "up" for c in checks.values()) else "degraded"
    return {
        "status": overall,
        "services": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

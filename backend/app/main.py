from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy import text

from app.api import auth as auth_router
from app.api import chat as chat_router
from app.api import documents as documents_router
from app.deps import engine, get_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify DB and Redis connections on startup."""
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
        await r.aclose()
        print("✓ Redis connection verified")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")

    yield

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
        await r.aclose()
        checks["redis"] = {"status": "up", "latency_ms": round(latency_ms, 1)}
    except Exception as e:
        checks["redis"] = {"status": "down", "error": str(e)}

    overall = "healthy" if all(c["status"] == "up" for c in checks.values()) else "degraded"
    return {
        "status": overall,
        "services": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

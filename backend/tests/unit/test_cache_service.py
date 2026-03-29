"""Unit tests for CacheService.

All tests use an in-memory MockRedis — no real Redis required.
"""
import pytest

from app.services.cache_service import CacheService


# ---------------------------------------------------------------------------
# Minimal in-memory Redis mock
# ---------------------------------------------------------------------------


class MockRedis:
    """In-memory drop-in for redis.asyncio.Redis, covering just the methods
    that CacheService uses: get, set, incr."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def incr(self, key: str) -> int:
        current = int(self._store.get(key, "0"))
        new_val = current + 1
        self._store[key] = str(new_val)
        return new_val


@pytest.fixture
def redis() -> MockRedis:
    return MockRedis()


@pytest.fixture
def cache(redis) -> CacheService:
    return CacheService(redis, ttl=60)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_cache_miss_returns_none(cache):
    result = await cache.get("如何练引体向上", "user-A")
    assert result is None


async def test_cache_set_then_get_returns_data(cache):
    payload = {"response": "引体向上入门建议", "sources": [], "agent_used": "training"}
    await cache.set("如何练引体向上", "user-A", payload)
    result = await cache.get("如何练引体向上", "user-A")
    assert result is not None
    assert result["response"] == "引体向上入门建议"
    assert result["agent_used"] == "training"


async def test_cache_is_user_scoped(cache):
    """Same query from different users must NOT share cached data."""
    await cache.set("如何练引体向上", "user-A", {"response": "A的回答"})
    result = await cache.get("如何练引体向上", "user-B")
    assert result is None


async def test_cache_key_normalization(cache):
    """Leading/trailing whitespace and case differences should map to the same key."""
    await cache.set("  Hello World  ", "user-X", {"data": 1})
    result = await cache.get("hello world", "user-X")
    assert result is not None
    assert result["data"] == 1


async def test_get_stats_initial_zeros(cache):
    stats = await cache.get_stats()
    assert stats["hit_rate"] == 0.0
    assert stats["total_queries"] == 0


async def test_get_stats_after_hits_and_misses(cache):
    await cache.track_hit()
    await cache.track_hit()
    await cache.track_miss()
    stats = await cache.get_stats()
    assert stats["total_queries"] == 3
    assert abs(stats["hit_rate"] - (2 / 3)) < 1e-4

"""Unit tests for the fixed-window rate limiter."""
import pytest

from app.services.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Minimal async mock for Redis (in-memory)
# ---------------------------------------------------------------------------

class MockPipeline:
    """Collects commands and executes them in sequence."""
    def __init__(self, redis):
        self._redis = redis
        self._commands = []

    def incr(self, key):
        self._commands.append(("incr", key))
        return self

    def expire(self, key, seconds):
        self._commands.append(("expire", key, seconds))
        return self

    async def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == "incr":
                results.append(await self._redis.incr(cmd[1]))
            elif cmd[0] == "expire":
                results.append(True)
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockRedis:
    def __init__(self):
        self._data = {}

    async def incr(self, key):
        self._data[key] = self._data.get(key, 0) + 1
        return self._data[key]

    async def expire(self, key, seconds):
        pass  # TTL not relevant for unit tests

    async def get(self, key):
        return self._data.get(key)

    def pipeline(self, transaction=False):
        return MockPipeline(self)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def redis():
    return MockRedis()


async def test_first_request_allowed(redis):
    limiter = RateLimiter(redis, max_requests=5, window_seconds=60)
    assert await limiter.check("user1") is True


async def test_requests_up_to_limit_allowed(redis):
    limiter = RateLimiter(redis, max_requests=3, window_seconds=60)
    for _ in range(3):
        assert await limiter.check("user1") is True


async def test_request_exceeding_limit_rejected(redis):
    limiter = RateLimiter(redis, max_requests=3, window_seconds=60)
    for _ in range(3):
        await limiter.check("user1")
    assert await limiter.check("user1") is False


async def test_different_users_independent(redis):
    limiter = RateLimiter(redis, max_requests=2, window_seconds=60)
    for _ in range(2):
        await limiter.check("user_a")
    # user_a exhausted, but user_b should still be allowed
    assert await limiter.check("user_a") is False
    assert await limiter.check("user_b") is True


async def test_get_remaining_full(redis):
    limiter = RateLimiter(redis, max_requests=10, window_seconds=60)
    remaining = await limiter.get_remaining("user1")
    assert remaining == 10


async def test_get_remaining_after_requests(redis):
    limiter = RateLimiter(redis, max_requests=5, window_seconds=60)
    await limiter.check("user1")
    await limiter.check("user1")
    remaining = await limiter.get_remaining("user1")
    assert remaining == 3


async def test_get_remaining_at_zero(redis):
    limiter = RateLimiter(redis, max_requests=2, window_seconds=60)
    for _ in range(5):
        await limiter.check("user1")
    remaining = await limiter.get_remaining("user1")
    assert remaining == 0


async def test_key_contains_user_id(redis):
    limiter = RateLimiter(redis, max_requests=10, window_seconds=60)
    key = limiter._key("abc123")
    assert "abc123" in key
    assert key.startswith("ratelimit:")

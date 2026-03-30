"""Fixed-window rate limiter backed by Redis.

Key: ratelimit:{user_id}:{minute_bucket}
Counter increments on each request; TTL = window_seconds so the key
expires automatically after the window ends.

Trade-off: a user can send up to 2× max_requests in a 2-second span
spanning two minute boundaries. This is acceptable for this scale;
upgrade to sliding-window (sorted set) if stricter enforcement is needed.
"""
import time


class RateLimiter:
    def __init__(self, redis, *, max_requests: int = 20, window_seconds: int = 60) -> None:
        self._redis = redis
        self._max = max_requests
        self._window = window_seconds

    def _key(self, user_id: str) -> str:
        bucket = int(time.time()) // self._window
        return f"ratelimit:{user_id}:{bucket}"

    async def check(self, user_id: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        key = self._key(user_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self._window)
            results = await pipe.execute()
        count = results[0]
        return count <= self._max

    async def get_remaining(self, user_id: str) -> int:
        """Return how many requests the user has left in the current window."""
        key = self._key(user_id)
        count = int(await self._redis.get(key) or 0)
        return max(0, self._max - count)

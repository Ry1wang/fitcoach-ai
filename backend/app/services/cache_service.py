"""Redis-backed query response cache.

Cache key: cache:query:{md5(user_id + ":" + normalized_query)}
Scoped per user because retrieval is user-scoped (each user searches their
own documents, so identical queries from different users yield different results).

Only first-message (context-free) queries are cached. Multi-turn queries are
excluded because conversation history changes the expected answer.
"""
import hashlib
import json

_HITS_KEY = "cache:stats:hits"
_MISSES_KEY = "cache:stats:misses"


class CacheService:
    def __init__(self, redis, *, ttl: int = 3600) -> None:
        self._redis = redis
        self._ttl = ttl

    def _make_key(self, query: str, user_id: str) -> str:
        normalized = query.strip().lower()
        raw = f"{user_id}:{normalized}"
        digest = hashlib.md5(raw.encode()).hexdigest()
        return f"cache:query:{digest}"

    async def get(self, query: str, user_id: str) -> dict | None:
        key = self._make_key(query, user_id)
        value = await self._redis.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set(self, query: str, user_id: str, response: dict) -> None:
        key = self._make_key(query, user_id)
        await self._redis.set(
            key,
            json.dumps(response, ensure_ascii=False),
            ex=self._ttl,
        )

    async def track_hit(self) -> None:
        await self._redis.incr(_HITS_KEY)

    async def track_miss(self) -> None:
        await self._redis.incr(_MISSES_KEY)

    async def get_stats(self) -> dict:
        hits = int(await self._redis.get(_HITS_KEY) or 0)
        misses = int(await self._redis.get(_MISSES_KEY) or 0)
        total = hits + misses
        return {
            "hit_rate": round(hits / total, 4) if total > 0 else 0.0,
            "total_queries": total,
        }

"""Embedding generation with retry and batching."""
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

# Module-level singleton to reuse the HTTP connection pool across calls
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.effective_embedding_api_key,
            base_url=settings.effective_embedding_base_url,
        )
    return _client


@retry(
    retry=retry_if_exception_type((APIError, APITimeoutError, RateLimitError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _embed_batch(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Retries on RateLimitError because this runs
    in a background ingestion pipeline where waiting is acceptable (unlike
    call_llm which is user-facing and fails fast on rate limits)."""
    response = await client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def generate_embeddings(
    texts: list[str],
    batch_size: int = 25,
) -> list[list[float]]:
    """Generate embeddings for texts in batches of `batch_size`."""
    client = _get_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings = await _embed_batch(client, batch)
        all_embeddings.extend(embeddings)

    return all_embeddings

"""Retry-wrapped LLM chat completion helper."""
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


@retry(
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def call_llm(
    client: AsyncOpenAI,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Call the chat completion API and return the assistant message content.

    Retries up to 3 times on connection/timeout errors with exponential backoff.
    RateLimitError is NOT retried — callers should handle it (return 503).
    """
    kwargs: dict = {
        "model": settings.LLM_CHAT_MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""

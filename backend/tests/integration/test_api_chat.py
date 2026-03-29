"""Integration tests for POST /api/v1/chat.

These tests use the real test DB but mock the LLM and embedding APIs.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# LLM mock helpers
# ---------------------------------------------------------------------------


def _router_response_mock(agent: str = "training", refined_query: str = "深蹲技术"):
    """Non-streaming LLM response for the router call."""
    content = json.dumps({"agent": agent, "refined_query": refined_query})
    result = MagicMock()
    result.choices[0].message.content = content
    return result


class _FakeStream:
    """Async iterator that yields fake token chunks for streaming LLM calls."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = list(tokens)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._tokens:
            raise StopAsyncIteration
        token = self._tokens.pop(0)
        chunk = MagicMock()
        chunk.choices[0].delta.content = token
        return chunk


def _make_mock_llm_client(
    router_agent: str = "training",
    response_tokens: list[str] | None = None,
):
    """Return a mock AsyncOpenAI client that handles router + streaming calls."""
    if response_tokens is None:
        response_tokens = ["这是", "测试", "回答"]

    router_result = _router_response_mock(agent=router_agent)

    async def fake_create(**kwargs):
        if kwargs.get("stream"):
            return _FakeStream(list(response_tokens))
        return router_result

    mock_client = MagicMock()
    mock_client.chat.completions.create = fake_create
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_chat_no_auth_returns_401(client):
    response = await client.post(
        "/api/v1/chat",
        json={"message": "如何练深蹲"},
    )
    assert response.status_code == 401


async def test_chat_rate_limited_returns_429(client, auth_headers):
    """When the rate limiter rejects the request, the endpoint returns 429."""
    with patch("app.api.chat.RateLimiter") as mock_cls:
        mock_limiter = AsyncMock()
        mock_limiter.check.return_value = False
        mock_cls.return_value = mock_limiter

        response = await client.post(
            "/api/v1/chat",
            json={"message": "如何练深蹲"},
            headers=auth_headers,
        )

    assert response.status_code == 429


async def test_chat_invalid_conversation_id_returns_404(client, auth_headers):
    """A non-existent conversation_id should return 404 before streaming starts."""
    import uuid

    with patch("app.api.chat.RateLimiter") as mock_cls:
        mock_limiter = AsyncMock()
        mock_limiter.check.return_value = True
        mock_cls.return_value = mock_limiter

        response = await client.post(
            "/api/v1/chat",
            json={"message": "test", "conversation_id": str(uuid.uuid4())},
            headers=auth_headers,
        )

    assert response.status_code == 404


async def test_chat_success_returns_sse_events(client, auth_headers):
    """Full happy path: response must contain routing, sources, token, done events."""
    mock_client = _make_mock_llm_client(
        router_agent="training",
        response_tokens=["这是", "测试", "回答"],
    )

    with (
        patch("app.api.chat.RateLimiter") as mock_limiter_cls,
        patch("app.api.chat.get_llm_client", return_value=mock_client),
        patch("app.api.chat.retrieve", new_callable=AsyncMock, return_value=[]),
    ):
        mock_limiter = AsyncMock()
        mock_limiter.check.return_value = True
        mock_limiter_cls.return_value = mock_limiter

        response = await client.post(
            "/api/v1/chat",
            json={"message": "如何练深蹲"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    # Parse SSE events
    event_types = set()
    for line in response.text.splitlines():
        if line.startswith("data: "):
            event = json.loads(line[6:])
            event_types.add(event.get("type"))

    assert "routing" in event_types
    assert "sources" in event_types
    assert "token" in event_types
    assert "done" in event_types


async def test_chat_cache_hit_on_second_identical_query(client, auth_headers):
    """A second identical first-message query should be served from cache."""
    mock_client = _make_mock_llm_client()

    patch_limiter = patch("app.api.chat.RateLimiter")
    patch_llm = patch("app.api.chat.get_llm_client", return_value=mock_client)
    patch_retrieve = patch("app.api.chat.retrieve", new_callable=AsyncMock, return_value=[])

    with patch_limiter as mock_limiter_cls, patch_llm, patch_retrieve:
        mock_limiter = AsyncMock()
        mock_limiter.check.return_value = True
        mock_limiter_cls.return_value = mock_limiter

        # First request
        r1 = await client.post(
            "/api/v1/chat",
            json={"message": "增肌吃什么"},
            headers=auth_headers,
        )
        assert r1.status_code == 200

        # Parse conversation_id from first response
        conv_id = None
        for line in r1.text.splitlines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event.get("type") == "done":
                    conv_id = event.get("conversation_id")

        # Second request — same message, same user, NEW conversation (is_first=True again)
        r2 = await client.post(
            "/api/v1/chat",
            json={"message": "增肌吃什么"},  # identical query
            headers=auth_headers,
        )
        assert r2.status_code == 200

        # Second response should contain cached=True in routing or done event
        cached_flag = False
        for line in r2.text.splitlines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event.get("cached"):
                    cached_flag = True
                    break

        assert cached_flag, "Second identical query should be served from cache"

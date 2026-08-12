from __future__ import annotations

import json

import httpx
import pytest

from miboe.adapters import Environment, make_adapter
from miboe.adapters.anthropic import AnthropicAdapter
from miboe.adapters.base import PreparedRequest
from miboe.adapters.openai import OpenAIAdapter
from miboe.adapters.perplexity import PerplexityAdapter
from miboe.errors import TechnicalRetryableError, ValidationError


@pytest.mark.parametrize(
    ("provider", "sampling"),
    [("openai", None), ("anthropic", {"max_tokens": 64}), ("gemini", None), ("xai", None)],
)
def test_closed_requests_are_single_turn_and_have_no_tools_or_system(
    provider: str, sampling: dict | None
) -> None:
    request = make_adapter(provider).prepare(
        model="exact-2026-01-01",
        prompt="質問",
        environment=Environment.CLOSED,
        sampling=sampling,
    )
    encoded = json.dumps(request.body)
    for forbidden in ("system", "developer", "tools", "previous_response_id"):
        assert forbidden not in encoded
    turns = (
        request.body.get("messages") or request.body.get("input") or request.body.get("contents")
    )
    assert len(turns) == 1
    assert turns[0]["role"] == "user"


def test_provider_sampling_defaults_are_omitted() -> None:
    probes = (
        ("openai", Environment.CLOSED, None),
        ("anthropic", Environment.CLOSED, {"max_tokens": 64}),
        ("gemini", Environment.CLOSED, None),
        ("xai", Environment.CLOSED, None),
        ("perplexity", Environment.NATIVE, None),
    )
    for provider, environment, sampling in probes:
        request = make_adapter(provider).prepare(
            model="exact-2026-01-01",
            prompt="質問",
            environment=environment,
            sampling=sampling,
        )
        encoded = json.dumps(request.body)
        for parameter in ('"temperature"', '"top_p"', '"top_k"', '"seed"'):
            assert parameter not in encoded


@pytest.mark.parametrize(
    "forbidden",
    [
        "developer",
        "system",
        "tools",
        "web_search",
        "memory",
        "rag",
        "retrieval",
        "file_search",
        "files",
        "history",
        "conversation",
    ],
)
def test_closed_audit_rejects_forbidden_state_and_capabilities(forbidden: str) -> None:
    body = {
        "model": "exact-id",
        "input": [{"role": "user", "content": "質問"}],
        "metadata": {forbidden: True},
    }
    request = PreparedRequest("POST", "https://example.test", {}, body)
    with pytest.raises(ValidationError, match="forbidden fields"):
        OpenAIAdapter()._audit_closed(request, Environment.CLOSED)


def test_anthropic_requires_protocol_output_cap() -> None:
    with pytest.raises(ValidationError, match="requires max_tokens"):
        AnthropicAdapter().prepare(
            model="claude-exact", prompt="質問", environment=Environment.CLOSED
        )
    request = AnthropicAdapter().prepare(
        model="claude-exact",
        prompt="質問",
        environment=Environment.CLOSED,
        sampling={"max_tokens": 256},
    )
    assert request.body["max_tokens"] == 256


def test_perplexity_refuses_closed_but_supports_native() -> None:
    adapter = PerplexityAdapter()
    with pytest.raises(ValidationError, match="cannot guarantee CLOSED"):
        adapter.prepare(model="sonar", prompt="質問", environment=Environment.CLOSED)
    assert adapter.prepare(model="sonar", prompt="質問", environment=Environment.NATIVE).body


def test_retryable_http_classification_and_redacted_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-value"
        return httpx.Response(429, json={"error": "rate"}, headers={"set-cookie": "secret"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = make_adapter(
        "openai", api_key="secret-value", client=client, base_url="https://example.test"
    )
    request = PreparedRequest(
        "GET", "https://example.test/v1/models", {"Authorization": "Bearer secret-value"}, None
    )
    with pytest.raises(TechnicalRetryableError) as caught:
        adapter.send(request)
    response = caught.value.provider_response
    assert response.headers["set-cookie"] == "[REDACTED]"

from __future__ import annotations

import json

import httpx
import pytest

from miboe.adapters import Environment, make_adapter
from miboe.adapters.anthropic import AnthropicAdapter
from miboe.adapters.base import PreparedRequest
from miboe.adapters.perplexity import PerplexityAdapter
from miboe.errors import TechnicalRetryableError, ValidationError


@pytest.mark.parametrize("provider", ["openai", "gemini", "xai"])
def test_closed_requests_are_single_turn_and_have_no_tools_or_system(provider: str) -> None:
    request = make_adapter(provider).prepare(
        model="exact-2026-01-01", prompt="質問", environment=Environment.CLOSED
    )
    encoded = json.dumps(request.body)
    for forbidden in ("system", "developer", "tools", "previous_response_id"):
        assert forbidden not in encoded


def test_provider_sampling_defaults_are_omitted() -> None:
    request = make_adapter("xai").prepare(
        model="exact-2026-01-01", prompt="質問", environment=Environment.CLOSED
    )
    assert "temperature" not in request.body
    assert "top_p" not in request.body


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

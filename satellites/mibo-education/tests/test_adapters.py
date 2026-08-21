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
from miboe.qualification import FIRST_PARTY_HOSTS, assert_first_party, build_request_shapes


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


def test_w0_perplexity_closed_diagnostic_is_explicitly_nonstandard() -> None:
    request = PerplexityAdapter().prepare_closed_diagnostic(
        model="sonar", prompt="W0 diagnostic"
    )
    assert request.url == "https://api.perplexity.ai/v1/sonar"
    assert request.body["disable_search"] is True
    assert request.body["stream"] is False
    assert request.body["max_tokens"] == 8192


def test_w0_qualification_shapes_are_first_party_single_turn_and_default_sampling() -> None:
    shapes = build_request_shapes()
    assert set(shapes) == {
        "M01",
        "M02",
        "M03",
        "M04",
        "M05",
        "M05_W0_CLOSED_DIAGNOSTIC",
    }
    for request, audit in shapes.values():
        assert audit["first_party_host"] == FIRST_PARTY_HOSTS[audit["provider"]]
        assert audit["single_user_turn"] is True
        assert audit["system_or_developer_prompt_absent"] is True
        assert audit["tools_absent"] is True
        assert audit["optional_sampling_absent"] is True
        assert audit["reasoning_controls_absent"] is True
        assert audit["non_streaming"] is True
        assert audit["output_cap_value"] == 8192
        assert request.body.get("stream", False) is False

    xai_request, _ = shapes["M04"]
    assert xai_request.url == "https://api.x.ai/v1/responses"
    assert xai_request.body["max_output_tokens"] == 8192
    assert "max_tokens" not in xai_request.body
    assert "messages" not in xai_request.body

    anthropic_request, _ = shapes["M02"]
    assert anthropic_request.body == {
        "model": "claude-opus-5",
        "messages": [
            {"role": "user", "content": "W0 engineering diagnostic. Reply with exactly: OK"}
        ],
        "stream": False,
        "max_tokens": 8192,
    }
    assert "thinking" not in anthropic_request.body
    assert "output_config" not in anthropic_request.body


def test_preserved_request_omits_credential_header_names() -> None:
    request = make_adapter("openai", api_key="unit-test-secret").prepare(
        model="gpt-5.6-sol",
        prompt="W0",
        environment=Environment.CLOSED,
        sampling={"max_output_tokens": 8192},
    )
    assert request.preserved()["headers"] == {"Content-Type": "application/json"}


def test_w0_qualification_rejects_third_party_router() -> None:
    request = PreparedRequest(
        "POST",
        "https://router.example/v1/responses",
        {},
        {"model": "gpt-5.6-sol"},
    )
    with pytest.raises(ValidationError, match="first-party HTTPS endpoint"):
        assert_first_party(request, "openai")


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

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .adapters import Environment, make_adapter
from .adapters.base import PreparedRequest
from .adapters.perplexity import PerplexityAdapter
from .errors import ValidationError
from .util import sha256_bytes

QUALIFICATION_PROMPT = "W0 engineering diagnostic. Reply with exactly: OK"
FIRST_PARTY_HOSTS = {
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
    "gemini": "generativelanguage.googleapis.com",
    "xai": "api.x.ai",
    "perplexity": "api.perplexity.ai",
}
OPTIONAL_SAMPLING_FIELDS = {
    "temperature",
    "top_p",
    "topP",
    "top_k",
    "topK",
    "seed",
}
REASONING_FIELDS = {
    "reasoning",
    "reasoning_effort",
    "effort",
    "thinking",
    "thinkingConfig",
    "thinking_level",
    "thinkingLevel",
}


@dataclass(frozen=True)
class QualificationTarget:
    series_id: str
    provider: str
    requested_model: str | None
    environment: Environment
    output_cap_parameter: str


TARGETS = (
    QualificationTarget(
        "M01", "openai", "gpt-5.6-sol", Environment.CLOSED, "max_output_tokens"
    ),
    QualificationTarget(
        "M02", "anthropic", "claude-opus-5", Environment.CLOSED, "max_tokens"
    ),
    QualificationTarget("M03", "gemini", "gemini-3.6-flash", Environment.CLOSED, "maxOutputTokens"),
    QualificationTarget(
        "M04", "xai", "grok-4.5", Environment.CLOSED, "max_output_tokens"
    ),
    QualificationTarget("M05", "perplexity", "sonar", Environment.NATIVE, "max_tokens"),
)


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_recursive_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_recursive_keys(item) for item in value))
    return set()


def assert_first_party(request: PreparedRequest, provider: str) -> None:
    parsed = urlparse(request.url)
    if parsed.scheme != "https" or parsed.hostname != FIRST_PARTY_HOSTS[provider]:
        raise ValidationError(
            f"{provider} qualification must use first-party HTTPS endpoint; got {request.url}"
        )


def audit_qualification_shape(
    request: PreparedRequest,
    *,
    provider: str,
    environment: Environment,
    output_cap_parameter: str,
    allow_disable_search: bool = False,
) -> dict[str, Any]:
    assert_first_party(request, provider)
    body = request.body or {}
    keys = _recursive_keys(body)
    forbidden_state = keys.intersection(
        {
            "system",
            "developer",
            "instructions",
            "system_instruction",
            "systemInstruction",
            "tools",
            "previous_response_id",
            "history",
            "conversation",
            "conversation_id",
            "files",
            "file_ids",
            "file_search",
            "retrieval",
            "rag",
            "memory",
        }
    )
    if forbidden_state:
        raise ValidationError(f"forbidden qualification state present: {sorted(forbidden_state)}")
    turns = body.get("messages") or body.get("input") or body.get("contents")
    if not isinstance(turns, list) or len(turns) != 1 or turns[0].get("role") != "user":
        raise ValidationError("qualification request must contain exactly one user turn")
    sampling_found = sorted(keys.intersection(OPTIONAL_SAMPLING_FIELDS))
    reasoning_found = sorted(keys.intersection(REASONING_FIELDS))
    if sampling_found:
        raise ValidationError(f"optional sampling fields present: {sampling_found}")
    if reasoning_found:
        raise ValidationError(f"reasoning override fields present: {reasoning_found}")
    if body.get("stream", False) is not False:
        raise ValidationError("qualification request must be non-streaming")
    if output_cap_parameter not in keys:
        raise ValidationError(f"output cap field is missing: {output_cap_parameter}")
    if allow_disable_search:
        if body.get("disable_search") is not True:
            raise ValidationError("M05 CLOSED diagnostic must set disable_search=true")
    elif "disable_search" in keys:
        raise ValidationError("disable_search belongs only to the W0 M05 diagnostic")
    return {
        "provider": provider,
        "environment": environment.value,
        "first_party_host": FIRST_PARTY_HOSTS[provider],
        "single_user_turn": True,
        "system_or_developer_prompt_absent": True,
        "history_absent": True,
        "tools_absent": "tools" not in keys,
        "web_search_configuration_absent": not keys.intersection(
            {"web_search", "web_search_options", "search_mode"}
        ),
        "files_retrieval_rag_memory_absent": not keys.intersection(
            {"files", "file_ids", "file_search", "retrieval", "rag", "memory"}
        ),
        "optional_sampling_absent": True,
        "reasoning_controls_absent": True,
        "non_streaming": True,
        "output_cap_parameter": output_cap_parameter,
        "output_cap_value": 8192,
        "serialized_request_sha256": sha256_bytes(request.body_bytes),
    }


def build_request_shapes() -> dict[str, tuple[PreparedRequest, dict[str, Any]]]:
    shapes: dict[str, tuple[PreparedRequest, dict[str, Any]]] = {}
    sampling = {
        "openai": {"max_output_tokens": 8192},
        "anthropic": {"max_tokens": 8192},
        "gemini": {"maxOutputTokens": 8192},
        "xai": {"max_output_tokens": 8192},
        "perplexity": {"max_tokens": 8192},
    }
    for target in TARGETS:
        if target.requested_model is None:
            continue
        request = make_adapter(target.provider).prepare(
            model=target.requested_model,
            prompt=QUALIFICATION_PROMPT,
            environment=target.environment,
            sampling=sampling[target.provider],
        )
        audit = audit_qualification_shape(
            request,
            provider=target.provider,
            environment=target.environment,
            output_cap_parameter=target.output_cap_parameter,
        )
        shapes[target.series_id] = (request, audit)
    diagnostic = PerplexityAdapter().prepare_closed_diagnostic(
        model="sonar", prompt=QUALIFICATION_PROMPT
    )
    shapes["M05_W0_CLOSED_DIAGNOSTIC"] = (
        diagnostic,
        audit_qualification_shape(
            diagnostic,
            provider="perplexity",
            environment=Environment.CLOSED,
            output_cap_parameter="max_tokens",
            allow_disable_search=True,
        ),
    )
    return shapes

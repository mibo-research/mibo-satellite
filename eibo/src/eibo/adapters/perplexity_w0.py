"""Explicit W0-only Agent API surface; legacy PerplexityAdapter stays unchanged."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from eibo.artifacts import load_yaml
from eibo.errors import ProviderError, ValidationError
from eibo.util import sha256_bytes, sha256_file

from .base import Environment, NormalizedResponse, PreparedRequest, ProviderResponse
from .perplexity import PerplexityAdapter

PROFILE_PATH = "waves/W0/perplexity-agent-profile-v1.yaml"
PROFILE_ID = "EIBO-W0-PERPLEXITY-AGENT-V1"
MODEL_ID = "perplexity/sonar"


def load_w0_agent_profile(module_root: Path) -> dict[str, Any]:
    path = module_root / PROFILE_PATH
    value = load_yaml(path)
    required = {
        "schema_version": "1.0",
        "profile_id": PROFILE_ID,
        "scope": "W0_ONLY",
        "official_longitudinal_data": False,
        "w01_authorized": False,
        "legacy_requested_model": "sonar",
        "requested_model": MODEL_ID,
        "endpoint": "https://api.perplexity.ai/v1/agent",
        "metadata_endpoint": "https://api.perplexity.ai/v1/models",
        "input_item_type": "message",
        "max_output_tokens": 8192,
        "effort_override": None,
        "native_tools": [{"type": "web_search"}],
        "no_search_mapping": "OMIT_TOOLS_AND_EFFORT",
        "model_fallback_permitted": False,
        "legacy_comparability": "NOT_ESTABLISHED",
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise ValidationError("invalid W0 Perplexity Agent API profile")
    return {**value, "profile_sha256": sha256_file(path)}


class PerplexityAgentW0Adapter(PerplexityAdapter):
    """Never registered as the default adapter for any official Wave."""

    w0_profile_id = PROFILE_ID
    w0_output_cap_parameter = "max_output_tokens"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.base_url != "https://api.perplexity.ai" or self.client.follow_redirects:
            raise ValidationError("W0 Perplexity requires its first-party host without redirects")

    def _prepare(
        self, *, model: str, prompt: str, environment: Environment,
        sampling: dict[str, Any], native_options: dict[str, Any],
    ) -> PreparedRequest:
        if model != MODEL_ID or sampling != {"max_output_tokens": 8192} or native_options:
            raise ValidationError("W0 Perplexity model, output cap, or options violate profile")
        body: dict[str, Any] = {
            "model": model,
            "input": [{"type": "message", "role": "user", "content": prompt}],
            "stream": False,
            "max_output_tokens": 8192,
        }
        if environment is Environment.NATIVE:
            body["tools"] = [{"type": "web_search"}]
        return PreparedRequest("POST", f"{self.base_url}/v1/agent", self.headers, body)

    def prepare_closed_diagnostic(
        self, *, model: str, prompt: str, max_tokens: int = 8192
    ) -> PreparedRequest:
        if max_tokens != 8192:
            raise ValidationError("W0 diagnostic requires an 8192 output cap")
        request = self._prepare(
            model=model, prompt=prompt, environment=Environment.CLOSED,
            sampling={"max_output_tokens": 8192}, native_options={},
        )
        self.qualification_audit(request, diagnostic=True)
        return request

    def qualification_audit(
        self, request: PreparedRequest, *, diagnostic: bool = False
    ) -> dict[str, Any]:
        from eibo.qualification import audit_qualification_shape

        body = request.body or {}
        expected_keys = {"model", "input", "stream", "max_output_tokens"}
        turns = body.get("input")
        if not diagnostic:
            expected_keys.add("tools")
        if (
            request.method != "POST"
            or request.url != "https://api.perplexity.ai/v1/agent"
            or set(body) != expected_keys
            or body.get("model") != MODEL_ID
            or type(body.get("max_output_tokens")) is not int
            or body["max_output_tokens"] != 8192
            or body.get("stream") is not False
            or not isinstance(turns, list) or len(turns) != 1
            or not isinstance(turns[0], dict) or set(turns[0]) != {"type", "role", "content"}
            or turns[0].get("type") != "message"
            or turns[0].get("role") != "user" or not isinstance(turns[0].get("content"), str)
            or (not diagnostic and body.get("tools") != [{"type": "web_search"}])
        ):
            raise ValidationError("W0 Perplexity request violates the explicit Agent API profile")
        # Reuse the strict common audit; remove only the already-validated NATIVE tool.
        audited_body = {key: value for key, value in body.items() if key != "tools"}
        audit = audit_qualification_shape(
            replace(request, body=audited_body), provider=self.provider,
            environment=Environment.CLOSED if diagnostic else Environment.NATIVE,
            output_cap_parameter="max_output_tokens",
        )
        return {
            **audit,
            "serialized_request_sha256": sha256_bytes(request.body_bytes),
            "tools_absent": diagnostic,
            "web_search_configuration_absent": diagnostic,
            "w0_profile_id": PROFILE_ID,
            "observation_surface": "PERPLEXITY_AGENT_API_W0_ONLY",
            "legacy_comparability": "NOT_ESTABLISHED",
            "official_longitudinal_data": False,
            "no_search_mapping": "OMIT_TOOLS_AND_EFFORT" if diagnostic else None,
            "legacy_disable_search_field_sent": False,
            "fallback_models_absent": True,
        }

    def send(self, request: PreparedRequest) -> ProviderResponse:
        if request.method == "GET":
            if request.url != "https://api.perplexity.ai/v1/models":
                raise ValidationError("W0 Perplexity metadata endpoint is not allowed")
        else:
            self.qualification_audit(request, diagnostic="tools" not in (request.body or {}))
        response = super().send(request)
        if 300 <= response.status_code < 400:
            error = ProviderError("W0 Perplexity redirect refused; no fallback attempted")
            error.provider_response = response  # type: ignore[attr-defined]
            raise error
        return response

    def _models_request(self) -> PreparedRequest:
        return PreparedRequest("GET", f"{self.base_url}/v1/models", self.headers, None)

    def normalize(self, body: dict[str, Any]) -> NormalizedResponse:
        texts: list[str] = []
        refusals: list[str] = []
        outputs = body.get("output") or []
        for item in outputs:
            if isinstance(item, dict) and item.get("type") == "message":
                for block in item.get("content") or []:
                    if block.get("type") == "output_text":
                        texts.append(str(block.get("text") or ""))
                    elif block.get("type") == "refusal":
                        refusals.append(str(block.get("refusal") or ""))
        reason = (body.get("incomplete_details") or {}).get("reason") or body.get("status")
        return NormalizedResponse(
            "\n".join(texts or refusals), reason, body.get("id"), body.get("model"),
            body.get("usage") or {},
            {
                "refusal": refusals,
                "output_item_types": [item.get("type") for item in outputs],
                "provider_configuration": {
                    key: body[key] for key in (
                        "model", "effort", "tools", "instructions", "service_tier",
                        "previous_response_id", "max_output_tokens", "incomplete_details",
                        "status", "error", "usage",
                    ) if key in body
                },
            },
        )

    def qualification_response_errors(
        self, body: dict[str, Any], *, diagnostic: bool = False
    ) -> list[str]:
        errors = []
        if not isinstance(body.get("id"), str) or not body["id"]:
            errors.append("response identity metadata missing")
        if body.get("status") not in {"completed", "incomplete"} or body.get("error"):
            errors.append("nonterminal or failed provider response")
        if not isinstance(body.get("usage"), dict) or not isinstance(body.get("output"), list):
            errors.append("usage or output metadata missing")
        if body.get("model") != MODEL_ID:
            errors.append("returned exact model identity mismatch")
        if any(body.get(key) for key in ("effort", "profile", "models", "previous_response_id")):
            errors.append("unexpected provider preset, fallback list, or conversation state")
        allowed_tools = set() if diagnostic else {"web_search"}
        if any(tool.get("type") not in allowed_tools for tool in body.get("tools") or []):
            errors.append("unexpected provider-returned tool configuration")
        allowed_output_types = {"message", "reasoning"} | (
            set() if diagnostic else {"search_results", "web_search_call"}
        )
        if any(item.get("type") not in allowed_output_types for item in body.get("output") or []):
            errors.append("unexpected tool or search activity in provider trace")
        if diagnostic:
            usage = body.get("usage") or {}

            def activity(value: Any) -> bool:
                if isinstance(value, dict):
                    return any(activity(item) for item in value.values())
                if isinstance(value, list):
                    return any(activity(item) for item in value)
                return bool(value)

            if (
                activity(usage.get("tool_calls_details"))
                or activity((usage.get("cost") or {}).get("tool_calls_cost"))
                or activity((usage.get("cost") or {}).get("tool_calls_cost_details"))
                or body.get("citations") or body.get("search_results")
                or any(
                    block.get("annotations")
                    for item in body.get("output") or [] if item.get("type") == "message"
                    for block in item.get("content") or []
                )
            ):
                errors.append("search/tool evidence found in no-search diagnostic")
        return errors

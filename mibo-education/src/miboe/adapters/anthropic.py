from __future__ import annotations

from typing import Any

from miboe.errors import ValidationError

from .base import Environment, NormalizedResponse, PreparedRequest, ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    provider, api_key_env = "anthropic", "ANTHROPIC_API_KEY"
    base_url_env, default_base_url = "MIBOE_ANTHROPIC_BASE_URL", "https://api.anthropic.com"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _prepare(
        self,
        *,
        model: str,
        prompt: str,
        environment: Environment,
        sampling: dict[str, Any],
        native_options: dict[str, Any],
    ) -> PreparedRequest:
        if "max_tokens" not in sampling:
            raise ValidationError(
                "Anthropic requires max_tokens; the protocol must explicitly provide it"
            )
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        body.update(sampling)
        if environment is Environment.NATIVE:
            body.update(native_options)
        return PreparedRequest("POST", f"{self.base_url}/v1/messages", self.headers, body)

    def normalize(self, body: dict[str, Any]) -> NormalizedResponse:
        text = "\n".join(
            str(value.get("text", ""))
            for value in body.get("content", [])
            if value.get("type") == "text"
        )
        return NormalizedResponse(
            text,
            body.get("stop_reason"),
            body.get("id"),
            body.get("model"),
            body.get("usage") or {},
            {"stop_reason": body.get("stop_reason")},
        )

    def _models_request(self) -> PreparedRequest:
        return PreparedRequest("GET", f"{self.base_url}/v1/models", self.headers, None)

    def _parse_models(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [value for value in body.get("data", []) if isinstance(value, dict)]

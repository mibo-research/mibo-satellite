from __future__ import annotations

from typing import Any

from .base import Environment, NormalizedResponse, PreparedRequest, ProviderAdapter


class PerplexityAdapter(ProviderAdapter):
    provider, api_key_env = "perplexity", "PERPLEXITY_API_KEY"
    base_url_env, default_base_url = "MIBOE_PERPLEXITY_BASE_URL", "https://api.perplexity.ai"
    closed_guarantee = False

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _prepare(
        self,
        *,
        model: str,
        prompt: str,
        environment: Environment,
        sampling: dict[str, Any],
        native_options: dict[str, Any],
    ) -> PreparedRequest:
        body: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        body.update(sampling)
        if environment is Environment.NATIVE:
            body.update(native_options)
        return PreparedRequest("POST", f"{self.base_url}/chat/completions", self.headers, body)

    def normalize(self, body: dict[str, Any]) -> NormalizedResponse:
        choice = (body.get("choices") or [{}])[0]
        text = str((choice.get("message") or {}).get("content") or "")
        safety = {"citations": body.get("citations"), "search_results": body.get("search_results")}
        return NormalizedResponse(
            text,
            choice.get("finish_reason"),
            body.get("id"),
            body.get("model"),
            body.get("usage") or {},
            safety,
        )

    def _models_request(self) -> PreparedRequest:
        return PreparedRequest("GET", f"{self.base_url}/models", self.headers, None)

    def _parse_models(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        values = body.get("data", body.get("models", []))
        return [value for value in values if isinstance(value, dict)]

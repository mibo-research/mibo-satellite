from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .base import Environment, NormalizedResponse, PreparedRequest, ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    provider, api_key_env = "openai", "OPENAI_API_KEY"
    base_url_env, default_base_url = "MIBOE_OPENAI_BASE_URL", "https://api.openai.com"

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
        body: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "store": False,
            "stream": False,
        }
        body.update(sampling)
        if environment is Environment.NATIVE:
            body.update(native_options)
        return PreparedRequest("POST", f"{self.base_url}/v1/responses", self.headers, body)

    def normalize(self, body: dict[str, Any]) -> NormalizedResponse:
        text: list[str] = []
        safety: dict[str, Any] = {}
        for item in body.get("output", []):
            for content in item.get("content", []) if isinstance(item, dict) else []:
                if content.get("type") == "output_text":
                    text.append(str(content.get("text", "")))
                elif content.get("type") == "refusal":
                    text.append(str(content.get("refusal", "")))
                    safety["refusal"] = True
        return NormalizedResponse(
            "\n".join(text),
            body.get("status"),
            body.get("id"),
            body.get("model"),
            body.get("usage") or {},
            safety,
        )

    def _models_request(self) -> PreparedRequest:
        return PreparedRequest("GET", f"{self.base_url}/v1/models", self.headers, None)

    def model_metadata_requests(self, model: str) -> tuple[PreparedRequest, ...]:
        model_path = quote(model, safe="-._")
        return (
            self._models_request(),
            PreparedRequest(
                "GET", f"{self.base_url}/v1/models/{model_path}", self.headers, None
            ),
        )

    def _parse_models(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [value for value in body.get("data", []) if isinstance(value, dict)]

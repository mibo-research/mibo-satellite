from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .base import Environment, NormalizedResponse, PreparedRequest, ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    provider, api_key_env = "gemini", "GEMINI_API_KEY"
    base_url_env = "MIBOE_GEMINI_BASE_URL"
    default_base_url = "https://generativelanguage.googleapis.com"

    @property
    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _prepare(
        self,
        *,
        model: str,
        prompt: str,
        environment: Environment,
        sampling: dict[str, Any],
        native_options: dict[str, Any],
    ) -> PreparedRequest:
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if sampling:
            body["generationConfig"] = sampling
        if environment is Environment.NATIVE:
            body.update(native_options)
        model_path = quote(model.removeprefix("models/"), safe="-._")
        return PreparedRequest(
            "POST",
            f"{self.base_url}/v1beta/models/{model_path}:generateContent",
            self.headers,
            body,
        )

    def normalize(self, body: dict[str, Any]) -> NormalizedResponse:
        candidates = body.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        parts = (candidate.get("content") or {}).get("parts", [])
        text = "\n".join(str(value["text"]) for value in parts if "text" in value)
        safety = {
            "promptFeedback": body.get("promptFeedback"),
            "safetyRatings": candidate.get("safetyRatings"),
        }
        finish = candidate.get("finishReason") if candidates else "PROMPT_BLOCKED"
        return NormalizedResponse(
            text,
            finish,
            body.get("responseId"),
            body.get("modelVersion"),
            body.get("usageMetadata") or {},
            safety,
        )

    def _models_request(self) -> PreparedRequest:
        return PreparedRequest(
            "GET", f"{self.base_url}/v1beta/models?pageSize=1000", self.headers, None
        )

    def _parse_models(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        return [value for value in body.get("models", []) if isinstance(value, dict)]

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from miboe.errors import ProviderError, TechnicalRetryableError, ValidationError
from miboe.util import canonical_json_bytes, sanitized_headers


class Environment(StrEnum):
    CLOSED = "CLOSED"
    NATIVE = "NATIVE"


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any] | None

    @property
    def body_bytes(self) -> bytes:
        return b"" if self.body is None else canonical_json_bytes(self.body)

    def preserved(self) -> dict[str, Any]:
        credential_headers = {"authorization", "x-api-key", "x-goog-api-key", "cookie"}
        return {
            "method": self.method,
            "url": self.url,
            "headers": {
                key: value
                for key, value in sanitized_headers(self.headers).items()
                if key.lower() not in credential_headers
            },
            "body": self.body,
        }


@dataclass(frozen=True)
class ProviderResponse:
    status_code: int
    headers: dict[str, str]
    body_bytes: bytes
    body: dict[str, Any] | None


@dataclass(frozen=True)
class NormalizedResponse:
    text: str
    finish_reason: str | None
    response_id: str | None
    returned_model: str | None
    usage: dict[str, Any]
    safety: dict[str, Any]


class ProviderAdapter(ABC):
    provider: str
    api_key_env: str
    base_url_env: str
    default_base_url: str
    closed_guarantee = True
    retryable_statuses = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.getenv(self.api_key_env, "")
        self.base_url = (base_url or os.getenv(self.base_url_env) or self.default_base_url).rstrip(
            "/"
        )
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def require_key(self) -> None:
        if not self.api_key:
            raise ProviderError(f"{self.api_key_env} is not set")

    def prepare(
        self,
        *,
        model: str,
        prompt: str,
        environment: Environment,
        sampling: dict[str, Any] | None = None,
        native_options: dict[str, Any] | None = None,
    ) -> PreparedRequest:
        if environment is Environment.CLOSED and not self.closed_guarantee:
            raise ValidationError(f"{self.provider} cannot guarantee CLOSED operation")
        if environment is Environment.CLOSED and native_options:
            raise ValidationError("native_options are forbidden in CLOSED")
        request = self._prepare(
            model=model,
            prompt=prompt,
            environment=environment,
            sampling=dict(sampling or {}),
            native_options=dict(native_options or {}),
        )
        self._audit_closed(request, environment)
        return request

    def _audit_closed(self, request: PreparedRequest, environment: Environment) -> None:
        if environment is not Environment.CLOSED or request.body is None:
            return
        forbidden = {
            "system",
            "developer",
            "system_instruction",
            "systemInstruction",
            "instructions",
            "tools",
            "tool_choice",
            "previous_response_id",
            "web_search",
            "web_search_options",
            "browse",
            "browsing",
            "memory",
            "rag",
            "retrieval",
            "file_search",
            "file_ids",
            "files",
            "attachments",
            "history",
            "conversation",
            "conversation_id",
            "input_file",
        }

        def keys(value: Any) -> set[str]:
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()

        found = forbidden.intersection(keys(request.body))
        if found:
            raise ValidationError(f"CLOSED request has forbidden fields: {sorted(found)}")
        messages = request.body.get("messages") or request.body.get("input")
        if isinstance(messages, list):
            roles = [value.get("role") for value in messages if isinstance(value, dict)]
            if len(messages) != 1 or roles != ["user"]:
                raise ValidationError("CLOSED request must have exactly one user turn")
        contents = request.body.get("contents")
        if isinstance(contents, list) and (len(contents) != 1 or contents[0].get("role") != "user"):
            raise ValidationError("CLOSED Gemini request must have exactly one user content")

    def send(self, request: PreparedRequest) -> ProviderResponse:
        self.require_key()
        try:
            response = self.client.request(
                request.method,
                request.url,
                headers=request.headers,
                content=request.body_bytes or None,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TechnicalRetryableError(f"{self.provider} transport failure: {exc}") from exc
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        preserved = ProviderResponse(
            response.status_code,
            sanitized_headers(dict(response.headers)),
            response.content,
            parsed if isinstance(parsed, dict) else None,
        )
        if response.status_code in self.retryable_statuses:
            error = TechnicalRetryableError(
                f"{self.provider} technical HTTP {response.status_code}",
                status_code=response.status_code,
            )
            error.provider_response = preserved  # type: ignore[attr-defined]
            raise error
        if response.status_code >= 400:
            error = ProviderError(f"{self.provider} non-retryable HTTP {response.status_code}")
            error.provider_response = preserved  # type: ignore[attr-defined]
            raise error
        if preserved.body is None:
            error = ProviderError(f"{self.provider} success response is not a JSON object")
            error.provider_response = preserved  # type: ignore[attr-defined]
            raise error
        return preserved

    def list_models(self) -> list[dict[str, Any]]:
        self.require_key()
        response = self.send(self._models_request())
        return self._parse_models(response.body or {})

    def model_metadata_requests(self, model: str) -> tuple[PreparedRequest, ...]:
        """Return first-party metadata requests needed to qualify an exact model ID."""
        return (self._models_request(),)

    def metadata_identifies_model(
        self, model: str, bodies: tuple[dict[str, Any], ...]
    ) -> bool:
        """Confirm that captured provider metadata names the requested exact model."""
        expected = model.removeprefix("models/")
        for body in bodies:
            candidates = [body, *self._parse_models(body)]
            for candidate in candidates:
                value = candidate.get("id") or candidate.get("name")
                if isinstance(value, str) and value.removeprefix("models/") == expected:
                    return True
        return False

    @abstractmethod
    def _prepare(
        self,
        *,
        model: str,
        prompt: str,
        environment: Environment,
        sampling: dict[str, Any],
        native_options: dict[str, Any],
    ) -> PreparedRequest: ...

    @abstractmethod
    def normalize(self, body: dict[str, Any]) -> NormalizedResponse: ...

    @abstractmethod
    def _models_request(self) -> PreparedRequest: ...

    @abstractmethod
    def _parse_models(self, body: dict[str, Any]) -> list[dict[str, Any]]: ...

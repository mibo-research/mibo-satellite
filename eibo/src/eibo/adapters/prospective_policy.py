"""Conservative response semantics for the prospective four-provider transport."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
TECHNICAL_CODES = {
    "rate_limit_error",
    "rate_limit_exceeded",
    "resource_exhausted",
    "too_many_requests",
    "overloaded_error",
    "api_error",
    "server_error",
    "internal",
    "internal_server_error",
    "unavailable",
    "service_unavailable",
    "deadline_exceeded",
    "bad_gateway",
    "gateway_timeout",
}


def has_observation(provider: str, body: dict[str, Any]) -> bool:
    if provider == "anthropic":
        return isinstance(body.get("content"), list) and bool(body.get("stop_reason"))
    if provider == "gemini":
        feedback = body.get("promptFeedback")
        return isinstance(body.get("candidates"), list) or (
            isinstance(feedback, dict) and bool(feedback.get("blockReason"))
        )
    return body.get("status") in ("completed", "incomplete") and isinstance(
        body.get("output"), list
    )


def explicit_technical_failure(status: int, body: dict[str, Any]) -> bool:
    # An error status by itself is not enough: a partial, unfamiliar or recoverable
    # scientific response cannot be treated as a confirmed failed generation.
    error = body.get("error")
    if (
        status not in RETRY_STATUSES
        or set(body) - {"error", "type", "request_id", "requestId"}
        or not isinstance(error, dict)
    ):
        return False
    codes = {str(error[key]).lower() for key in ("type", "status", "code") if error.get(key)}
    return bool(codes & TECHNICAL_CODES) and codes <= TECHNICAL_CODES | {str(status)}


def retry_at(
    provider: str, headers: dict[str, str], body: dict[str, Any], received: datetime
) -> datetime:
    value = headers.get("retry-after", "")
    seconds = 120.0
    if value:
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            seconds = max(seconds, float(value))
        else:
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is not None:
                    seconds = max(seconds, (stamp - received).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    error = body.get("error")
    if provider == "gemini" and isinstance(error, dict):
        details = error.get("details")
        for entry in details if isinstance(details, list) else []:
            delay = entry.get("retryDelay") if isinstance(entry, dict) else None
            if isinstance(delay, str) and re.fullmatch(r"\d+(?:\.\d+)?s", delay):
                seconds = max(seconds, float(delay[:-1]))
    # A malformed/huge delay must never turn into a short wait by overflow.
    if not math.isfinite(seconds) or seconds > 24 * 3600:
        return datetime.max.replace(tzinfo=UTC)
    return received + timedelta(seconds=seconds)

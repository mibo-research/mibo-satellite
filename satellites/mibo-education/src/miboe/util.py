from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ImmutabilityError, ValidationError

SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "PERPLEXITY_API_KEY",
)
SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(rb"(?i)(api[_-]?key|authorization)\s*[\"']?\s*[:=]\s*[\"']?[^\s\"']{12,}"),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def ensure_no_secrets(data: bytes, *, context: str) -> None:
    for name in SECRET_ENV_NAMES:
        value = os.getenv(name, "").encode()
        if len(value) >= 8 and value in data:
            raise ValidationError(f"secret-redaction failure in {context}: {name} value found")
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise ValidationError(
                f"secret-redaction failure in {context}: credential pattern found"
            )


def sanitized_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive = {"authorization", "x-api-key", "x-goog-api-key", "cookie", "set-cookie"}
    return {
        key: "[REDACTED]" if key.lower() in sensitive else value for key, value in headers.items()
    }


def write_immutable(
    path: Path, data: bytes, *, allow_sensitive_scientific_data: bool = False
) -> None:
    """Create once and fsync. Existing scientific records are never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not allow_sensitive_scientific_data:
        ensure_no_secrets(data, context=str(path))
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ImmutabilityError(f"refusing to overwrite immutable artifact: {path}") from exc


def write_derived(path: Path, data: bytes) -> None:
    """Atomically rebuild an L1/QC derivative; never use for L0."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_secrets(data, context=str(path))
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

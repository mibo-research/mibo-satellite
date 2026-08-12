from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .adapters import make_adapter
from .artifacts import WaveManifest, load_registry
from .errors import ImmutabilityError, ModelResolutionError, ValidationError
from .util import artifact_hash, canonical_json_bytes, load_json, utc_now, write_immutable

ALIAS_PATTERN = re.compile(r"(^|[-_/])(latest|current|auto)([-_/]|$)", re.IGNORECASE)


def _listed_id(provider: str, value: dict[str, Any]) -> str | None:
    candidate = value.get("id") or value.get("name")
    if not isinstance(candidate, str):
        return None
    return candidate.removeprefix("models/") if provider == "gemini" else candidate


def resolve_models(
    manifest: WaveManifest,
    requested: dict[str, str],
    evidence: dict[str, str],
    *,
    verify_live: bool = True,
    adapter_factory: Any = make_adapter,
) -> dict[str, Any]:
    if manifest.model_lock_path.exists():
        raise ImmutabilityError(f"model lock already exists: {manifest.model_lock_path}")
    registry = load_registry(manifest.registry_path)
    series = {value["series_id"]: value for value in registry["series"]}
    if not requested or set(requested) - series.keys():
        raise ModelResolutionError("requested mappings are empty or contain unknown series")
    live_cache: dict[str, dict[str, dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    for series_id in sorted(requested):
        exact = requested[series_id]
        entry = series[series_id]
        provider = entry["provider"]
        if not exact.strip() or ALIAS_PATTERN.search(exact):
            raise ModelResolutionError(f"alias or blank model is forbidden: {exact!r}")
        if exact == series_id:
            raise ModelResolutionError(
                f"permanent series ID cannot be used as an exact Wave model ID: {series_id}"
            )
        if verify_live:
            if provider not in live_cache:
                listed = adapter_factory(provider).list_models()
                live_cache[provider] = {
                    model_id: value
                    for value in listed
                    if (model_id := _listed_id(provider, value)) is not None
                }
            if exact not in live_cache[provider]:
                raise ModelResolutionError(
                    f"{provider} did not list exact model {exact!r}; no substitution was made"
                )
            metadata = live_cache[provider][exact]
        else:
            if manifest.official:
                raise ModelResolutionError("official model locks require live verification")
            metadata = {"verification": "disabled for engineering only"}
        rows.append(
            {
                "series_id": series_id,
                "provider": provider,
                "requested_model": exact,
                "live_verified": verify_live,
                "pinning_evidence": evidence.get(series_id),
                "pinning_verified": bool(evidence.get(series_id)),
                "provider_metadata": metadata,
            }
        )
    core = {
        "schema_version": "1.0",
        "wave_id": manifest.wave_id,
        "registry_sha256": registry["registry_sha256"],
        "resolved_at": utc_now(),
        "models": rows,
    }
    lock = {**core, "model_lock_sha256": artifact_hash(core)}
    write_immutable(manifest.model_lock_path, canonical_json_bytes(lock) + b"\n")
    return lock


def load_model_lock(path: Path) -> dict[str, Any]:
    try:
        lock = load_json(path)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"cannot load model lock {path}: {exc}") from exc
    claimed = lock.pop("model_lock_sha256", None)
    actual = artifact_hash(lock)
    lock["model_lock_sha256"] = claimed
    if claimed != actual:
        raise ValidationError("model lock hash mismatch")
    rows = lock.get("models")
    if not isinstance(rows, list) or not rows:
        raise ValidationError("model lock contains no models")
    ids = [value.get("series_id") for value in rows]
    if len(ids) != len(set(ids)):
        raise ValidationError("model lock contains duplicate series")
    if any(value.get("series_id") == value.get("requested_model") for value in rows):
        raise ValidationError("model lock conflates permanent series and exact Wave model IDs")
    return lock

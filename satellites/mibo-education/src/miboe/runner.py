from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapters import Environment, make_adapter
from .artifacts import Battery, WaveManifest
from .deviations import log_deviation
from .errors import ImmutabilityError, ProviderError, TechnicalRetryableError, ValidationError
from .preflight import preflight
from .scheduling import validate_bindings
from .util import (
    artifact_hash,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    utc_now,
    write_immutable,
)


def seal_wave(
    wave_dir: Path,
    manifest: WaveManifest,
    battery: Battery,
    lock: dict[str, Any],
    schedule: dict[str, Any],
) -> dict[str, Any]:
    core = {
        "schema_version": "1.0",
        "wave_id": manifest.wave_id,
        "site_id": manifest.site_id,
        "OFFICIAL_LONGITUDINAL_DATA": manifest.official,
        "sealed_at": utc_now(),
        "protocol_version": manifest.protocol_version,
        "manifest_sha256": manifest.content_sha256,
        "battery_sha256": battery.content_sha256,
        "model_lock_sha256": lock["model_lock_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
    }
    proposed = {**core, "seal_sha256": artifact_hash(core)}
    path = wave_dir / "WAVE_STARTED.json"
    if path.exists():
        existing = load_json(path)
        fields = (
            "wave_id",
            "site_id",
            "OFFICIAL_LONGITUDINAL_DATA",
            "protocol_version",
            "manifest_sha256",
            "battery_sha256",
            "model_lock_sha256",
            "schedule_sha256",
        )
        for field in fields:
            if existing.get(field) != proposed.get(field):
                raise ImmutabilityError(f"sealed Wave input changed: {field}")
        claimed = existing.pop("seal_sha256", None)
        if claimed != artifact_hash(existing):
            raise ImmutabilityError("Wave seal hash mismatch")
        existing["seal_sha256"] = claimed
        return existing
    write_immutable(path, canonical_json_bytes(proposed) + b"\n")
    return proposed


def _save_response(stem: Path, response: Any) -> None:
    body_hash = sha256_bytes(response.body_bytes)
    # L0 must retain the exact scientific response even when QC later quarantines sensitive content.
    write_immutable(
        Path(f"{stem}.response.body"),
        response.body_bytes,
        allow_sensitive_scientific_data=True,
    )
    core = {
        "captured_at": utc_now(),
        "status_code": response.status_code,
        "headers": response.headers,
        "body_sha256": body_hash,
        "body_length": len(response.body_bytes),
    }
    envelope = {**core, "response_envelope_sha256": artifact_hash(core)}
    write_immutable(Path(f"{stem}.response.json"), canonical_json_bytes(envelope) + b"\n")


def run_wave(
    *,
    manifest: WaveManifest,
    battery: Battery,
    lock: dict[str, Any],
    schedule: dict[str, Any],
    max_observations: int | None = None,
    ignore_planned_time: bool = False,
    adapter_factory: Any = make_adapter,
    sleep: Any = time.sleep,
    now: datetime | None = None,
) -> dict[str, int]:
    validate_bindings(manifest, battery, lock, schedule)
    report = preflight(manifest, write_report=False)
    if not report["passed"]:
        raise ValidationError("preflight failed: " + "; ".join(report["errors"]))
    if ignore_planned_time and manifest.official:
        raise ValidationError("official Wave cannot ignore planned time")
    current = now or datetime.now(UTC)
    if manifest.official and not manifest.start <= current <= manifest.end:
        raise ValidationError("official execution is outside the registered field window")
    wave_dir = manifest.source.parent
    seal_wave(wave_dir, manifest, battery, lock, schedule)
    items = {item.item_id: item for item in battery.items}
    stats = {"completed": 0, "technical_failure": 0, "already_reconciled": 0, "not_due": 0}
    selected = 0
    for row in sorted(schedule["rows"], key=lambda value: value["execution_position"]):
        observation_dir = wave_dir / "L0_raw" / row["observation_id"]
        completion_path = observation_dir / "completion.json"
        if completion_path.exists():
            stats["already_reconciled"] += 1
            continue
        planned = datetime.fromisoformat(row["planned_start_utc"])
        if not ignore_planned_time and planned > current:
            stats["not_due"] += 1
            continue
        if max_observations is not None and selected >= max_observations:
            break
        selected += 1
        item = items[row["item_id"]]
        if item.prompt_sha256 != row["prompt_sha256"]:
            raise ImmutabilityError(f"Frozen prompt drift: {item.item_id}")
        provider = row["provider"]
        adapter = adapter_factory(provider)
        for attempt in range(1, manifest.max_attempts + 1):
            attempt_id = f"{row['observation_id']}-A{attempt:02d}"
            stem = observation_dir / attempt_id
            request_path = Path(f"{stem}.request.json")
            body_path = Path(f"{stem}.request.body")
            if request_path.exists() or body_path.exists():
                raise ImmutabilityError(
                    f"incomplete prior attempt requires human adjudication: {attempt_id}"
                )
            request = adapter.prepare(
                model=row["requested_model"],
                prompt=item.prompt,
                environment=Environment(manifest.environment),
                sampling=manifest.sampling.get(provider),
                native_options=manifest.native_options.get(provider),
            )
            body = request.body_bytes
            request_core = {
                "schema_version": "1.0",
                "attempt_id": attempt_id,
                "intended_observation_id": row["observation_id"],
                "attempt_number": attempt,
                "prepared_at": utc_now(),
                "site_id": manifest.site_id,
                "wave_id": manifest.wave_id,
                "provider": provider,
                "series_id": row["series_id"],
                "requested_model": row["requested_model"],
                "environment": manifest.environment,
                "prompt_sha256": item.prompt_sha256,
                "request": request.preserved(),
                "request_body_sha256": sha256_bytes(body),
                "request_body_length": len(body),
            }
            request_record = {**request_core, "request_record_sha256": artifact_hash(request_core)}
            write_immutable(body_path, body)
            write_immutable(request_path, canonical_json_bytes(request_record) + b"\n")
            try:
                response = adapter.send(request)
            except (TechnicalRetryableError, ProviderError) as exc:
                captured = getattr(exc, "provider_response", None)
                if captured is not None:
                    _save_response(stem, captured)
                retryable = isinstance(exc, TechnicalRetryableError)
                error_core = {
                    "attempt_id": attempt_id,
                    "recorded_at": utc_now(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "retry_eligible": retryable,
                    "status_code": getattr(exc, "status_code", None),
                }
                error_record = {**error_core, "error_sha256": artifact_hash(error_core)}
                write_immutable(
                    Path(f"{stem}.error.json"), canonical_json_bytes(error_record) + b"\n"
                )
                if retryable and attempt < manifest.max_attempts:
                    sleep(manifest.retry_delays_minutes[attempt - 1] * 60)
                    continue
                completion_core = {
                    "schema_version": "1.0",
                    "observation_id": row["observation_id"],
                    "status": "TECHFAIL",
                    "scientifically_completed": False,
                    "attempts": attempt,
                    "reconciled_at": utc_now(),
                    "last_error_type": type(exc).__name__,
                }
                completion = {
                    **completion_core,
                    "completion_sha256": artifact_hash(completion_core),
                }
                write_immutable(completion_path, canonical_json_bytes(completion) + b"\n")
                stats["technical_failure"] += 1
                break
            else:
                _save_response(stem, response)
                normalized = adapter.normalize(response.body or {})
                completion_core = {
                    "schema_version": "1.0",
                    "observation_id": row["observation_id"],
                    "status": "OBSERVED",
                    "scientifically_completed": True,
                    "completed_at": utc_now(),
                    "attempts": attempt,
                    "provider": provider,
                    "series_id": row["series_id"],
                    "requested_model": row["requested_model"],
                    "returned_model": normalized.returned_model,
                    "item_id": item.item_id,
                    "replication_number": row["replication_number"],
                    "prompt_sha256": item.prompt_sha256,
                    "request_sha256": sha256_bytes(body),
                    "response_sha256": sha256_bytes(response.body_bytes),
                    "response_text": normalized.text,
                    "finish_reason": normalized.finish_reason,
                    "provider_response_id": normalized.response_id,
                    "usage": normalized.usage,
                    "safety": normalized.safety,
                }
                completion = {
                    **completion_core,
                    "completion_sha256": artifact_hash(completion_core),
                }
                write_immutable(
                    completion_path,
                    canonical_json_bytes(completion) + b"\n",
                    allow_sensitive_scientific_data=True,
                )
                returned = (normalized.returned_model or "").removeprefix("models/")
                if returned and returned != row["requested_model"]:
                    log_deviation(
                        wave_dir,
                        code="RETURNED_MODEL_MISMATCH",
                        severity="material",
                        observation_id=row["observation_id"],
                        description="Provider-reported model differs from exact requested model",
                        details={
                            "requested_model": row["requested_model"],
                            "returned_model": normalized.returned_model,
                        },
                    )
                stats["completed"] += 1
                break
    return stats

from __future__ import annotations

from typing import Any

from .adapters import Environment, make_adapter
from .artifacts import (
    Battery,
    WaveManifest,
    load_battery,
    load_registry,
    load_scientific_artifact_registry,
)
from .models import load_model_lock
from .scheduling import load_schedule, validate_bindings
from .util import artifact_hash, canonical_json_bytes, utc_now, write_derived


def preflight(manifest: WaveManifest, *, write_report: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    battery: Battery | None = None
    lock: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    registry: dict[str, Any] | None = None
    try:
        battery = load_battery(manifest.battery_path)
    except Exception as exc:
        errors.append(str(exc))
    try:
        registry = load_registry(manifest.registry_path)
    except Exception as exc:
        errors.append(str(exc))
    try:
        lock = load_model_lock(manifest.model_lock_path)
    except Exception as exc:
        errors.append(str(exc))
    try:
        schedule = load_schedule(manifest.schedule_path)
    except Exception as exc:
        errors.append(str(exc))
    if battery and lock and schedule:
        try:
            validate_bindings(manifest, battery, lock, schedule)
        except Exception as exc:
            errors.append(str(exc))
    if registry and lock:
        if lock.get("registry_sha256") != registry.get("registry_sha256"):
            errors.append("model-series registry changed after exact model resolution")
        if lock.get("wave_id") != manifest.wave_id:
            errors.append("model lock belongs to a different Wave")

    if manifest.official:
        if manifest.status != "FROZEN" or not manifest.approved:
            errors.append("official Wave Manifest must be FROZEN and approved")
        if (
            manifest.wave_id == "MIBO-EDU-W01"
            and manifest.start.isoformat() != "2026-09-01T00:00:00+00:00"
        ):
            errors.append("W01 anchor must be 2026-09-01T00:00:00Z")
        if (
            not battery
            or not battery.approved
            or not battery.official_eligible
            or battery.expected_count != 70
        ):
            errors.append("official Wave requires approved, longitudinal-eligible 70-item EBB-JA")
        if not registry or registry.get("approved") is not True:
            errors.append("official model-series registry is not approved")
        missing_approvals = sorted(key for key, value in manifest.approvals.items() if not value)
        if missing_approvals:
            errors.append(f"missing Wave approvals: {missing_approvals}")
        if not manifest.scientific_artifacts:
            errors.append("official Wave has no scientific artifact bindings")
        for name, path in manifest.scientific_artifacts.items():
            if not path.is_file():
                errors.append(f"scientific artifact missing: {name} ({path})")
        if manifest.scientific_registry_path is None:
            errors.append("official Wave has no scientific artifact freeze registry")
        else:
            try:
                science_registry = load_scientific_artifact_registry(
                    manifest.scientific_registry_path
                )
                blocked = sorted(
                    artifact_id
                    for artifact_id, value in science_registry["artifacts"].items()
                    if value["status"] != "FROZEN" or not value["approved"]
                )
                if blocked:
                    errors.append(f"scientific artifacts are not Frozen and approved: {blocked}")
            except Exception as exc:
                errors.append(str(exc))
        if manifest.random_seed.startswith("UNSET"):
            errors.append("Wave random seed has not been supplied by the implementation package")
        if lock:
            for model in lock["models"]:
                if not model.get("live_verified") or not model.get("pinning_verified"):
                    errors.append(
                        f"exact model is not live/pinning verified: {model.get('series_id')}"
                    )
    else:
        if battery and battery.official_eligible:
            warnings.append("pilot battery is marked longitudinal-eligible; verify classification")

    if lock and battery and battery.items:
        for model in lock["models"]:
            provider = model["provider"]
            try:
                make_adapter(provider).prepare(
                    model=model["requested_model"],
                    prompt=battery.items[0].prompt,
                    environment=Environment(manifest.environment),
                    sampling=manifest.sampling.get(provider),
                    native_options=manifest.native_options.get(provider),
                )
            except Exception as exc:
                errors.append(f"{provider} request preflight failed: {exc}")

    core = {
        "schema_version": "1.0",
        "wave_id": manifest.wave_id,
        "generated_at": utc_now(),
        "passed": not errors,
        "official_longitudinal_data": manifest.official,
        "manifest_sha256": manifest.content_sha256,
        "battery_sha256": battery.content_sha256 if battery else None,
        "model_lock_sha256": lock.get("model_lock_sha256") if lock else None,
        "schedule_sha256": schedule.get("schedule_sha256") if schedule else None,
        "errors": errors,
        "warnings": warnings,
    }
    report = {**core, "preflight_sha256": artifact_hash(core)}
    if write_report:
        write_derived(
            manifest.source.parent / "preflight.json", canonical_json_bytes(report) + b"\n"
        )
    return report

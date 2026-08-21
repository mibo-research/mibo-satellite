from __future__ import annotations

import random
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from .artifacts import Battery, WaveManifest
from .errors import ValidationError
from .util import artifact_hash, canonical_json_bytes, load_json, write_immutable


def create_schedule(
    manifest: WaveManifest, battery: Battery, lock: dict[str, Any]
) -> dict[str, Any]:
    if manifest.schedule_path.exists():
        raise ValidationError(f"schedule already exists: {manifest.schedule_path}")
    rng = random.Random(manifest.random_seed)
    strata: dict[str, list[Any]] = defaultdict(list)
    for item in battery.items:
        strata[item.stratum].append(item)
    models = sorted(lock["models"], key=lambda row: row["series_id"])
    duration = manifest.end - manifest.start
    rows: list[dict[str, Any]] = []
    sequence = 0
    for replication in range(1, manifest.replications + 1):
        fraction = (
            0.5 if manifest.replications == 1 else (replication - 1) / (manifest.replications - 1)
        )
        center = manifest.start + duration * fraction
        for stratum in sorted(strata):
            block = [(item, model) for item in strata[stratum] for model in models]
            rng.shuffle(block)
            for block_position, (item, model) in enumerate(block, start=1):
                sequence += 1
                maximum_jitter = min(900.0, duration.total_seconds() / 100)
                planned = center + timedelta(seconds=rng.uniform(-maximum_jitter, maximum_jitter))
                planned = max(manifest.start, min(manifest.end, planned))
                short_site = manifest.site_id.removeprefix("MIBO-SITE-")
                observation_id = (
                    f"{manifest.wave_id}-{short_site}-{model['series_id']}-"
                    f"{item.item_id}-R{replication:02d}"
                )
                rows.append(
                    {
                        "generation_sequence": sequence,
                        "observation_id": observation_id,
                        "site_id": manifest.site_id,
                        "replication_number": replication,
                        "stratum": stratum,
                        "block_position": block_position,
                        "item_id": item.item_id,
                        "prompt_sha256": item.prompt_sha256,
                        "series_id": model["series_id"],
                        "provider": model["provider"],
                        "requested_model": model["requested_model"],
                        "environment": manifest.environment,
                        "planned_start_utc": planned.isoformat(),
                    }
                )
    rows.sort(key=lambda row: (row["planned_start_utc"], row["generation_sequence"]))
    for position, row in enumerate(rows, start=1):
        row["execution_position"] = position
    core = {
        "schema_version": "1.0",
        "wave_id": manifest.wave_id,
        "manifest_sha256": manifest.content_sha256,
        "battery_sha256": battery.content_sha256,
        "model_lock_sha256": lock["model_lock_sha256"],
        "randomization_method": "stratified-block-randomized-v1",
        "random_seed": manifest.random_seed,
        "field_window_start": manifest.start.isoformat(),
        "field_window_end": manifest.end.isoformat(),
        "rows": rows,
    }
    schedule = {**core, "schedule_sha256": artifact_hash(core)}
    write_immutable(manifest.schedule_path, canonical_json_bytes(schedule) + b"\n")
    return schedule


def load_schedule(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"cannot load schedule {path}: {exc}") from exc
    claimed = value.pop("schedule_sha256", None)
    actual = artifact_hash(value)
    value["schedule_sha256"] = claimed
    if claimed != actual:
        raise ValidationError("schedule hash mismatch")
    ids = [row.get("observation_id") for row in value.get("rows", [])]
    if len(ids) != len(set(ids)):
        raise ValidationError("schedule contains duplicate Observation IDs")
    return value


def validate_bindings(
    manifest: WaveManifest, battery: Battery, lock: dict[str, Any], schedule: dict[str, Any]
) -> None:
    checks = {
        "wave_id": manifest.wave_id,
        "manifest_sha256": manifest.content_sha256,
        "battery_sha256": battery.content_sha256,
        "model_lock_sha256": lock["model_lock_sha256"],
    }
    for field, expected in checks.items():
        if schedule.get(field) != expected:
            raise ValidationError(f"schedule binding mismatch: {field}")
    expected_rows = len(battery.items) * len(lock["models"]) * manifest.replications
    if len(schedule.get("rows", [])) != expected_rows:
        raise ValidationError(f"schedule row count is not {expected_rows}")

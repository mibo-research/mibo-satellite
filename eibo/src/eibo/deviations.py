from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import artifact_hash, canonical_json_bytes, utc_now, write_immutable


def log_deviation(
    wave_dir: Path,
    *,
    code: str,
    description: str,
    severity: str,
    observation_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> Path:
    core = {
        "schema_version": "1.0",
        "recorded_at": utc_now(),
        "code": code,
        "severity": severity,
        "description": description,
        "observation_id": observation_id,
        "details": details or {},
    }
    record = {**core, "deviation_sha256": artifact_hash(core)}
    directory = wave_dir / "deviations"
    number = len(list(directory.glob("*.json"))) + 1 if directory.exists() else 1
    path = directory / f"deviation-{number:05d}.json"
    write_immutable(path, canonical_json_bytes(record) + b"\n")
    return path

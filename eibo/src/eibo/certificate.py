from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ValidationError
from .util import (
    artifact_hash,
    canonical_json_bytes,
    load_json,
    sha256_file,
    utc_now,
    write_immutable,
)


def create_certificate(
    wave_dir: Path,
    *,
    manifest_sha256: str,
    battery_sha256: str,
    model_lock_sha256: str,
    schedule_sha256: str,
) -> dict[str, Any]:
    report_path = wave_dir / "qc" / "report.json"
    if not report_path.exists():
        raise ValidationError("QC report is missing")
    report = load_json(report_path)
    if not report.get("passed"):
        raise ValidationError("QC did not pass or planned observations are unreconciled")
    canonical = wave_dir / "L1_canonical" / "observations.jsonl"
    if sha256_file(canonical) != report["canonical_sha256"]:
        raise ValidationError("L1 canonical data changed after QC")
    raw_hashes = {
        str(path.relative_to(wave_dir)): sha256_file(path)
        for path in sorted((wave_dir / "L0_raw").rglob("*"))
        if path.is_file()
    }
    core = {
        "schema_version": "1.0",
        "wave_id": report["wave_id"],
        "certified_at": utc_now(),
        "completion_classification": report["completion_classification"],
        "manifest_sha256": manifest_sha256,
        "battery_sha256": battery_sha256,
        "model_lock_sha256": model_lock_sha256,
        "schedule_sha256": schedule_sha256,
        "qc_report_sha256": report["qc_report_sha256"],
        "canonical_sha256": report["canonical_sha256"],
        "L0_artifact_count": len(raw_hashes),
        "L0_manifest_sha256": artifact_hash(raw_hashes),
    }
    certificate = {**core, "certificate_sha256": artifact_hash(core)}
    write_immutable(
        wave_dir / "wave-completion-certificate.json", canonical_json_bytes(certificate) + b"\n"
    )
    return certificate

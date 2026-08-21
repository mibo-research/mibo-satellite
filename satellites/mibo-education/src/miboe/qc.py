from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .artifacts import Battery, WaveManifest
from .scheduling import validate_bindings
from .util import (
    artifact_hash,
    canonical_json,
    canonical_json_bytes,
    ensure_no_secrets,
    load_json,
    sha256_file,
    utc_now,
    write_derived,
)


def _hashed_record(path: Path, field: str) -> str | None:
    try:
        record = load_json(path)
        claimed = record.pop(field)
        return None if artifact_hash(record) == claimed else f"{path}: {field} mismatch"
    except (OSError, ValueError, KeyError) as exc:
        return f"{path}: malformed record: {exc}"


def generate_canonical(
    wave_dir: Path, manifest: WaveManifest, schedule: dict[str, Any]
) -> tuple[Path, str, int]:
    lines: list[str] = []
    for row in sorted(schedule["rows"], key=lambda value: value["execution_position"]):
        path = wave_dir / "L0_raw" / row["observation_id"] / "completion.json"
        if not path.exists():
            continue
        completion = load_json(path)
        record = {
            "observation_id": row["observation_id"],
            "site_id": row["site_id"],
            "wave_id": manifest.wave_id,
            "OFFICIAL_LONGITUDINAL_DATA": manifest.official,
            "execution_position": row["execution_position"],
            "planned_start_utc": row["planned_start_utc"],
            "stratum": row["stratum"],
            "item_id": row["item_id"],
            "replication_number": row["replication_number"],
            "provider": row["provider"],
            "series_id": row["series_id"],
            "requested_model": row["requested_model"],
            "environment": row["environment"],
            "prompt_sha256": row["prompt_sha256"],
            "status": completion["status"],
            "scientifically_completed": completion["scientifically_completed"],
            "attempts": completion["attempts"],
            "completed_at": completion.get("completed_at") or completion.get("reconciled_at"),
            "returned_model": completion.get("returned_model"),
            "response_text": completion.get("response_text"),
            "finish_reason": completion.get("finish_reason"),
            "usage": completion.get("usage", {}),
            "safety": completion.get("safety", {}),
            "request_sha256": completion.get("request_sha256"),
            "response_sha256": completion.get("response_sha256"),
            "completion_sha256": completion["completion_sha256"],
        }
        lines.append(canonical_json(record))
    data = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
    path = wave_dir / "L1_canonical" / "observations.jsonl"
    write_derived(path, data)
    return path, sha256_file(path), len(lines)


def run_qc(
    manifest: WaveManifest, battery: Battery, lock: dict[str, Any], schedule: dict[str, Any]
) -> dict[str, Any]:
    validate_bindings(manifest, battery, lock, schedule)
    wave_dir = manifest.source.parent
    errors: list[str] = []
    warnings: list[str] = []
    counts: Counter[str] = Counter()
    expected = {row["observation_id"]: row for row in schedule["rows"]}
    raw_root = wave_dir / "L0_raw"
    actual = (
        {path.name for path in raw_root.iterdir() if path.is_dir()} if raw_root.exists() else set()
    )
    if actual - expected.keys():
        errors.append(f"unexpected L0 observations: {sorted(actual - expected.keys())}")
    for observation_id, row in expected.items():
        directory = raw_root / observation_id
        completion_path = directory / "completion.json"
        if not completion_path.exists():
            counts["MISSING"] += 1
            continue
        problem = _hashed_record(completion_path, "completion_sha256")
        if problem:
            errors.append(problem)
            continue
        completion = load_json(completion_path)
        counts[completion.get("status", "INVALID")] += 1
        if completion.get("scientifically_completed"):
            if completion.get("prompt_sha256") != row["prompt_sha256"]:
                errors.append(f"{observation_id}: prompt hash differs from schedule")
            if completion.get("requested_model") != row["requested_model"]:
                errors.append(f"{observation_id}: requested model differs from lock")
            returned = (completion.get("returned_model") or "").removeprefix("models/")
            if returned and returned != row["requested_model"]:
                warnings.append(f"{observation_id}: returned model mismatch requires review")
        for body_path in directory.glob("*.body"):
            try:
                ensure_no_secrets(body_path.read_bytes(), context=str(body_path))
            except Exception as exc:
                errors.append(str(exc))
        for meta_path in directory.glob("*.request.json"):
            problem = _hashed_record(meta_path, "request_record_sha256")
            if problem:
                errors.append(problem)
            record = load_json(meta_path)
            body_path = Path(str(meta_path).replace(".request.json", ".request.body"))
            if not body_path.exists() or sha256_file(body_path) != record.get(
                "request_body_sha256"
            ):
                errors.append(f"{meta_path}: request body hash mismatch")
            if manifest.environment == "CLOSED":
                body = (record.get("request") or {}).get("body") or {}
                forbidden = {
                    "system",
                    "system_instruction",
                    "systemInstruction",
                    "instructions",
                    "tools",
                    "tool_choice",
                    "previous_response_id",
                }
                if forbidden.intersection(body):
                    errors.append(f"{meta_path}: forbidden CLOSED fields")
        for meta_path in directory.glob("*.response.json"):
            problem = _hashed_record(meta_path, "response_envelope_sha256")
            if problem:
                errors.append(problem)
            record = load_json(meta_path)
            body_path = Path(str(meta_path).replace(".response.json", ".response.body"))
            if not body_path.exists() or sha256_file(body_path) != record.get("body_sha256"):
                errors.append(f"{meta_path}: response body hash mismatch")
    if any("secret-redaction" in error for error in errors):
        canonical_path = wave_dir / "L1_canonical" / "observations.jsonl"
        canonical_hash = None
        records = 0
    else:
        canonical_path, canonical_hash, records = generate_canonical(wave_dir, manifest, schedule)
    intended = len(expected)
    observed = counts["OBSERVED"]
    reconciled = sum(counts.values()) == intended
    proportion = observed / intended if intended else 0
    if observed == intended:
        classification = "complete"
    elif reconciled and proportion >= 0.90:
        classification = "complete_with_documented_missing"
    elif reconciled and observed:
        classification = "partially_completed"
    else:
        classification = "not_completed"
    deviations = (
        list((wave_dir / "deviations").glob("*.json")) if (wave_dir / "deviations").exists() else []
    )
    core = {
        "schema_version": "1.0",
        "wave_id": manifest.wave_id,
        "generated_at": utc_now(),
        "passed": not errors and reconciled,
        "completion_classification": classification,
        "intended_observations": intended,
        "status_counts": dict(counts),
        "canonical_records": records,
        "canonical_path": str(canonical_path),
        "canonical_sha256": canonical_hash,
        "deviation_count": len(deviations),
        "errors": errors,
        "warnings": warnings,
    }
    report = {**core, "qc_report_sha256": artifact_hash(core)}
    write_derived(wave_dir / "qc" / "report.json", canonical_json_bytes(report) + b"\n")
    return report

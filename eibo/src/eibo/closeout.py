"""Offline, append-only assessment of the four-provider W0 evidence set.

This is not a Q2/Q3 gate writer, a Wave certificate, or permission to execute.
It never opens a credential store, creates an adapter, or sends a provider request.
The existing secret validator scans evidence before it is included in this report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import ValidationError
from .util import (
    artifact_hash,
    canonical_json_bytes,
    ensure_no_secrets,
    load_json,
    sha256_file,
    utc_now,
    write_immutable,
)

ITEM_IDS = tuple(f"E{domain}-01" for domain in range(1, 8))
MODELS = {
    "M01": "gpt-5.6-sol",
    "M02": "claude-opus-5",
    "M03": "gemini-3.6-flash",
    "M05": "perplexity/sonar",
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValidationError(reason)


def evidence_path(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and bool(relative), "empty evidence reference")
    parts = PurePosixPath(relative)
    require(
        not parts.is_absolute()
        and ".." not in parts.parts
        and "\\" not in relative
        and ":" not in relative,
        "evidence reference must be a confined relative path",
    )
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), "evidence file missing/escaped")
    return path


def verify_reference(root: Path, reference: dict[str, Any]) -> Path:
    path = evidence_path(root, reference["path"])
    ensure_no_secrets(path.read_bytes(), context="W0 closeout input")
    require(sha256_file(path) == reference["sha256"], "evidence file hash mismatch")
    return path


def read_reference(root: Path, reference: dict[str, Any]) -> dict[str, Any]:
    value = load_json(verify_reference(root, reference))
    require(isinstance(value, dict), "evidence record must be an object")
    require(value.get("official_longitudinal_data") is False, "official evidence is forbidden")
    return value


def verify_archive(root: Path, entries: list[dict[str, Any]]) -> int:
    require(bool(entries), "empty checksum archive")
    # Historical Windows checksum manifests used backslash separators. Interpret
    # those paths portably without rewriting the original manifest or any bytes.
    entries = [
        {**row, "path": PurePosixPath(row["path"].replace("\\", "/")).as_posix()} for row in entries
    ]
    paths = [row["path"] for row in entries]
    require(len(paths) == len(set(paths)), "duplicate checksum archive path")
    for row in entries:
        path = verify_reference(root, row)
        if "bytes" in row:
            require(path.stat().st_size == row["bytes"], "archive byte count mismatch")
    return len(entries)


def check_items(rows: list[dict[str, Any]], model: str) -> dict[str, dict[str, Any]]:
    items = {row["item_id"]: row for row in rows}
    require(len(items) == len(rows), "duplicate completed cell")
    require(set(items).issubset(ITEM_IDS), "unexpected W0 item")
    for row in rows:
        require(row.get("returned_model") == model, "returned model identity mismatch")
        require(row.get("returned_identity_matches_requested", True) is True, "identity failed")
    return items


def assess_closeout(evidence_root: Path, sources_path: Path) -> dict[str, Any]:
    """Validate pinned provenance and assess completeness without altering any input."""
    sources = load_json(sources_path)
    require(sources.get("official_longitudinal_data") is False, "W0 sources must be non-official")
    require(set(sources["providers"]) == set(MODELS), "exactly the four authorized series required")
    summary = read_reference(evidence_root, sources["summary"])
    require(summary.get("archive_integrity_qc_passed") is True, "initial archive QC failed")
    archive = read_reference(evidence_root, sources["archive"])
    initial_count = verify_archive(evidence_root, archive["entries"])
    prior = read_reference(evidence_root, sources["prior_integrity"])
    prior_count = verify_archive(
        evidence_root,
        [{"path": path, "sha256": digest} for path, digest in prior["entries"].items()],
    )
    qc_path = verify_reference(evidence_root, sources["recovery_qc"])
    qc = read_reference(evidence_root, sources["recovery_qc"])
    require(qc.get("archive_integrity_qc_passed") is True, "recovery archive QC failed")
    verify_archive(qc_path.parent, qc["entries"])
    assessed = {}
    for series, model in MODELS.items():
        refs = sources["providers"][series]
        q1 = read_reference(evidence_root, refs["q1"])
        q2 = read_reference(evidence_root, refs["q2"])
        for record in (q1, q2):
            require(record.get("series_id") == series, "series identity mismatch")
            require(record.get("requested_model") == model, "requested model mismatch")
            require(record.get("substitution_attempted") is False, "model substitution detected")
        require(q1.get("passed") is True, "Q1 did not pass")
        require(q1.get("ordinary_requests_attempted") == 1, "Q1 ordinary-request count is not one")
        require(q1.get("returned_model") == model, "Q1 returned identity mismatch")
        require(q1.get("metadata_complete") is True, "Q1 metadata incomplete")
        if series == "M05":
            require(
                q1.get("qualification_profile_sha256")
                == sources["m05_profile_sha256"]
                == q2.get("qualification_profile_sha256"),
                "M05 profile binding mismatch",
            )
        original = check_items(q2["item_results"], model)
        if series == "M03":
            failures = refs.get("original_technical_failures", {})
            require(
                set(failures) == set(ITEM_IDS) - set(original),
                "original technical-failure coverage mismatch",
            )
            for reference in failures.values():
                failed = load_json(verify_reference(evidence_root, reference))
                require(
                    failed.get("status_code") in {408, 409, 425, 429, 500, 502, 503, 504},
                    "a scientific response cannot be replaced by a recovery",
                )
        merged = dict(original)
        recovery_refs = refs.get("recoveries", [])
        for reference in recovery_refs:
            recovery = read_reference(evidence_root, reference)
            require(series == "M03", "only documented Google recoveries are permitted")
            require(recovery.get("recovery_qualified") is True, "recovery did not qualify")
            require(recovery.get("returned_model") == model, "recovery model mismatch")
            item = recovery["item_id"]
            require(
                item in ITEM_IDS and item not in merged, "recovery would replace a completed cell"
            )
            merged[item] = recovery
        require(set(merged) == set(ITEM_IDS), "seven-domain completion is incomplete")
        if series == "M03":
            require(
                q2["status"] == "FAILED_CLOSED" and q2["passed"] is False,
                "historical Google failed result must remain unchanged",
            )
            require(
                len(original) == 5 and len(recovery_refs) == 2, "Google recovery lineage changed"
            )
        else:
            require(q2.get("passed") is True and not recovery_refs, "original Q2 did not pass")
        diagnostics = check_items(q2.get("closed_diagnostic_results", []), model)
        require(
            set(diagnostics) == (set(ITEM_IDS) if series == "M05" else set()),
            "diagnostic coverage mismatch",
        )
        assessed[series] = {
            "requested_model": model,
            "Q1": "PASSED",
            "original_Q2": q2["status"],
            "original_completed_items": len(original),
            "separate_recovery_items": len(recovery_refs),
            "completed_items_including_separate_recovery": len(merged),
            "non_official_no_search_diagnostics": len(diagnostics),
            "assessment": "COMPLETE_WITH_SEPARATE_RECOVERY" if recovery_refs else "COMPLETE",
            "refusals_observed": sum(bool(r.get("refusal_observed")) for r in merged.values()),
            "provider_blocks_observed": sum(
                bool(r.get("provider_block_observed")) for r in merged.values()
            ),
            "truncations_observed": sum(
                bool(r.get("truncation_or_output_cap_stop_observed")) for r in merged.values()
            ),
        }
    core = {
        "schema_version": "1.0",
        "recorded_at": utc_now(),
        "scope": "W0_FOUR_PROVIDER_Q1_Q2_EVIDENCE_CLOSEOUT_ONLY",
        "official_longitudinal_data": False,
        "FOUR_PROVIDER_EVIDENCE_COMPLETE": True,
        "machine_assessment_only": True,
        "human_closeout_acceptance": "PENDING_EXPLICIT_HUMAN_RECORD",
        "providers": assessed,
        "initial_archive_files_verified": initial_count,
        "prior_files_verified": prior_count,
        "sources_sha256": sha256_file(sources_path),
        "old_results_and_gates_modified": False,
        "new_Q2_or_Q3_gate_created": False,
        "Q3_CORE_35": "NOT_RUN_M04_COST_HOLD",
        "W0_READY": False,
        "W01_READY": False,
        "wave_completion_certificate": "NOT_CREATED",
        "execution_permitted": False,
        "provider_requests_sent": 0,
        "xai_requests_sent": 0,
        "W01": "NOT_RUN",
    }
    return {**core, "assessment_sha256": artifact_hash(core)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = assess_closeout(args.evidence_root, args.sources)
    write_immutable(args.output, canonical_json_bytes(report) + b"\n")
    print(json.dumps({"FOUR_PROVIDER_EVIDENCE_COMPLETE": True, "output": str(args.output)}))


if __name__ == "__main__":
    main()

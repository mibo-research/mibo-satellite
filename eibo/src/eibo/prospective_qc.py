"""Read-only integrity and classification audit of a prospective runtime archive."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .prospective_runtime import EXCLUDED_HEADERS, GOOGLE_GAP, MAX_MICRO_USD, PRIMARY
from .util import artifact_hash, ensure_no_secrets, sha256_file


def _require(condition: bool, error: str) -> None:
    if not condition:
        raise ValidationError(f"prospective QC: {error}")


def _load_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    ensure_no_secrets(data, context="prospective archive record")
    row = json.loads(data)
    _require(
        artifact_hash({k: v for k, v in row.items() if k != "record_sha256"})
        == row.get("record_sha256"),
        f"{path.name} hash mismatch",
    )
    return row


def verify_run(output: Path) -> dict[str, Any]:
    claim = _load_record(output / "execution-claim.json")
    report = _load_record(output / "report.json")
    _require(
        claim["OFFICIAL_LONGITUDINAL_DATA"] is report["OFFICIAL_LONGITUDINAL_DATA"] is False,
        "not a synthetic archive",
    )
    anchor, target, hard = (
        datetime.fromisoformat(claim[key]) for key in ("anchor", "target", "deadline")
    )
    rows = [json.loads(line) for line in (output / "observations.jsonl").read_bytes().splitlines()]
    _require(
        len({r["id"] for r in rows}) == len(rows) == report["planned"],
        "canonical plan count or uniqueness",
    )
    counts = Counter(row["status"] for row in rows)
    _require(counts == report["status_counts"], "canonical status counts")
    _require(sum(r["primary"] for r in rows) == report["primary"], "primary count mismatch")
    directories = {r.parent.name for r in (output / "L0").glob("*/completion.json")}
    _require(
        directories == {r["id"] for r in rows if r["status"] != "NOT_SENT"},
        "completion files do not match canonical results",
    )
    for row in rows:
        _require(row["OFFICIAL_LONGITUDINAL_DATA"] is False, "official data in synthetic archive")
        _require(row["primary"] == (row["status"] in PRIMARY), "invalid primary flag")
        if row["status"] == "NOT_SENT":
            continue
        completion = _load_record(output / "L0" / row["id"] / "completion.json")
        _require(
            completion == {k: v for k, v in row.items() if k != "OFFICIAL_LONGITUDINAL_DATA"},
            "canonical row differs from completion",
        )
        if row["scientifically_completed"]:
            received = datetime.fromisoformat(row["received_at"])
            sent = datetime.fromisoformat(row["dispatched_at"])
            _require(anchor <= sent < hard and received >= sent, "invalid observed timestamps")
            _require(
                (received > hard) == (row["status"] == "LATE_NONPRIMARY"),
                "late response classification mismatch",
            )
            if row["primary"]:
                _require(
                    (received > target) == (row["status"] == "PRIMARY_TARGET_OVERRUN"),
                    "target-overrun classification mismatch",
                )
            stem = output / "L0" / row["id"] / f"attempt-{row['reserved_attempts']}"
            _require(
                sha256_file(stem.with_suffix(".response.body")) == row["response_sha256"],
                "completion response hash mismatch",
            )
            _require(
                sha256_file(stem.with_suffix(".request.body")) == row["request_sha256"],
                "completion request hash mismatch",
            )

    charges: list[dict[str, Any]] = []
    google = []
    for path in output.rglob("*.*.json"):
        suffix = path.name.split(".")[-2]
        if suffix not in {"intent", "result", "request", "response"}:
            continue
        row = _load_record(path)
        if suffix == "intent":
            charges.append(row)
            stamp = datetime.fromisoformat(row["admitted_at"])
            _require(anchor <= stamp < hard, "admission outside window")
        elif suffix in {"request", "response"}:
            _require(not EXCLUDED_HEADERS.intersection(row["headers"]), "credential header")
            body = path.with_suffix(".body")
            ensure_no_secrets(body.read_bytes(), context="prospective archive body")
            _require(sha256_file(body) == row["body_sha256"], "wire body hash mismatch")
            if suffix == "response":
                _require(
                    path.with_name(path.name.replace(".response.json", ".intent.json")).is_file(),
                    "response missing prior admission",
                )
        if suffix in {"result", "response"} and row.get("dispatched_at"):
            sent = datetime.fromisoformat(row["dispatched_at"])
            _require(anchor <= sent < hard, "dispatch outside window")
            if path.parent.parent.name == "L0":
                intent = _load_record(
                    path.with_name(path.name.replace(f".{suffix}.json", ".intent.json"))
                )
                if intent["series"] == "M03":
                    google.append(sent)

    committed = 0
    methods: dict[str, Counter[str]] = {"POST": Counter(), "GET": Counter()}
    retries: Counter[str] = Counter()
    cell_attempts: Counter[str] = Counter()
    for i, row in enumerate(sorted(charges, key=lambda v: v["number"]), 1):
        _require(row["number"] == i, "nonconsecutive attempt receipts")
        committed += row["reserve_micro_USD"]
        _require(
            0 < committed <= MAX_MICRO_USD and row["committed_micro_USD"] == committed,
            "inconsistent budget reservation",
        )
        methods[row["method"]][row["series"]] += 1
        if row["method"] == "POST":
            cell_attempts[row["cell"]] += 1
            _require(cell_attempts[row["cell"]] == row["cell_attempt"] <= 2, "cell attempt ceiling")
            if row["cell_attempt"] == 2:
                retries[row["series"]] += 1
    _require(committed == report["committed_micro_USD"], "final reservation mismatch")
    for method, limit, total in (("POST", 770, 3080), ("GET", 3, 12)):
        _require(
            methods[method] == report[f"{method.lower()}_by_series"], "attempt counts mismatch"
        )
        _require(
            all(n <= limit for n in methods[method].values()) and methods[method].total() <= total,
            "attempt ceiling exceeded",
        )
    _require(
        retries == report["retries_by_series"]
        and retries.total() <= 280
        and all(n <= 70 for n in retries.values()),
        "retry counts or ceiling mismatch",
    )
    google.sort()
    gaps = [b - a for a, b in zip(google, google[1:], strict=False)]
    _require(all(gap >= GOOGLE_GAP for gap in gaps), "Google pacing below 65 seconds")
    return {
        "integrity_passed": True,
        "canonical_sha256": sha256_file(output / "observations.jsonl"),
        "admission_receipts": len(charges),
        "minimum_google_start_gap_seconds": min(gaps).total_seconds() if gaps else None,
        "primary": report["primary"],
        "late_nonprimary": counts["LATE_NONPRIMARY"],
        "unobserved": sum(not r["scientifically_completed"] for r in rows),
    }

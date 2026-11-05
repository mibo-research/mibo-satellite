"""Offline-only retiming of the full EIBO-F01 fixture; never an execution lock."""

from __future__ import annotations

import argparse
import json
import os
import socket
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import offline_capacity12 as original

from eibo.artifacts import load_scientific_artifact_registry
from eibo.errors import ValidationError
from eibo.scheduling import create_schedule
from eibo.util import (
    SECRET_ENV_NAMES,
    artifact_hash,
    load_json,
    sha256_bytes,
    sha256_file,
)

REPLICATIONS = 10
REFERENCE_CENTER_SPACING_MINUTES = 120
CANDIDATE_CENTER_SPACING_MINUTES = 108
METHOD = "OFFLINE_ONLY_PRESERVE_SEEDED_ORDER_SHIFT_ROUND_CENTERS_108_MINUTES"


def retime(rows):
    """Shift every release in a replication equally; retain jitters and tie order."""
    shifted = []
    for row in rows:
        n = row["replication_number"]
        if type(n) is not int or not 1 <= n <= REPLICATIONS:
            raise ValidationError("offline retiming requires replication numbers 1–10")
        old = datetime.fromisoformat(row["planned_start_utc"])
        offset = (n - 1) * (REFERENCE_CENTER_SPACING_MINUTES - CANDIDATE_CENTER_SPACING_MINUTES)
        new = old - timedelta(minutes=offset)
        if not original.ANCHOR <= new <= original.ANCHOR + timedelta(seconds=original.TARGET):
            raise ValidationError("retimed release outside unchanged 18-hour target window")
        shifted.append({**row, "planned_start_utc": new.isoformat()})
    # The timing adjustment must not change the existing order even across rounds.
    if any(
        a["planned_start_utc"] > b["planned_start_utc"]
        for a, b in zip(shifted, shifted[1:], strict=False)
    ):
        raise ValidationError("offline retiming would change the randomized order")
    return shifted


def candidate_schedule(manifest, battery, lock):
    if (
        manifest.official
        or manifest.approved
        or manifest.protocol_version != "OFFLINE_SYNTHETIC_ONLY"
        or manifest.replications != REPLICATIONS
        or manifest.start != original.ANCHOR
        or manifest.end - manifest.start != timedelta(seconds=original.TARGET)
    ):
        raise ValidationError("candidate applies only to the full non-official synthetic fixture")
    reference = create_schedule(
        replace(
            manifest,
            schedule_path=manifest.schedule_path.with_name("unshifted-schedule-fixture.json"),
        ),
        battery,
        lock,
    )
    core = {key: value for key, value in reference.items() if key != "schedule_sha256"}
    core.update(
        rows=retime(reference["rows"]),
        randomization_method=METHOD,
        source_schedule_sha256=reference["schedule_sha256"],
        candidate_center_spacing_minutes=CANDIDATE_CENTER_SPACING_MINUTES,
        official_longitudinal_data=False,
    )
    schedule = {**core, "schedule_sha256": artifact_hash(core)}
    original.save(manifest.schedule_path, schedule)
    return schedule


def compare_traces(reference, candidate):
    assert len(reference) == len(candidate) == 2800
    starts_by_item = defaultdict(list)
    starts_google = []
    timing_fields = {
        "planned_start_elapsed_seconds",
        "dispatch_elapsed_seconds",
        "response_elapsed_seconds",
    }
    for before, after in zip(reference, candidate, strict=True):
        assert {k: v for k, v in before.items() if k not in timing_fields} == {
            k: v for k, v in after.items() if k not in timing_fields
        }, "release change altered order, scientific inputs, or mock outputs"
        start = after["dispatch_elapsed_seconds"]
        starts_by_item[after["series_id"], after["item_id"]].append(
            (after["replication_number"], start)
        )
        if after["series_id"] == "M03":
            starts_google.append(start)
        shift = (
            60
            * (after["replication_number"] - 1)
            * (REFERENCE_CENTER_SPACING_MINUTES - CANDIDATE_CENTER_SPACING_MINUTES)
        )
        assert (
            abs(
                before["planned_start_elapsed_seconds"]
                - after["planned_start_elapsed_seconds"]
                - shift
            )
            < 1e-6
        )
        assert 0 <= after["planned_start_elapsed_seconds"] <= start < original.DEADLINE
    assert len(starts_by_item) == 280 and len(starts_google) == 700
    for rows in starts_by_item.values():
        assert [n for n, _ in rows] == list(range(1, 11))
        assert all(a[1] < b[1] for a, b in zip(rows, rows[1:], strict=False))
    return min(b - a for a, b in zip(starts_google, starts_google[1:], strict=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_output_directory", type=Path)
    parser.add_argument("--compare-to", required=True, type=Path, help="read-only run-01 directory")
    args = parser.parse_args()
    directory = args.new_output_directory.resolve()
    reference_dir = args.compare_to.resolve()
    if directory == reference_dir or directory.is_relative_to(reference_dir):
        parser.error("candidate output must not be inside the reference archive")
    for name in SECRET_ENV_NAMES:
        try:
            del os.environ[name]
        except KeyError:
            pass
    with (
        patch.object(socket, "getaddrinfo", original.forbidden_network),
        patch.object(socket.socket, "connect", original.forbidden_network),
        patch.object(socket.socket, "connect_ex", original.forbidden_network),
        patch.object(socket.socket, "sendto", original.forbidden_network),
    ):
        registry_path = original.ROOT / "protocol/scientific-artifacts.yaml"
        load_scientific_artifact_registry(registry_path)
        reference_report_path = reference_dir / "report.json"
        reference_trace_path = reference_dir / "baseline/virtual-trace.json"
        reference_index_path = reference_dir / "archive-checksums.json"
        index = load_json(reference_index_path)
        for relpath, digest in index.items():
            assert sha256_file(reference_dir / relpath) == digest
        reference_report = load_json(reference_report_path)
        reference_trace = load_json(reference_trace_path)
        harness_sha = sha256_bytes(Path(original.__file__).read_bytes().replace(b"\r\n", b"\n"))
        assert harness_sha == reference_report["fixture_script_canonical_sha256"]
        assert reference_report["official_longitudinal_data"] is False
        assert reference_report["provider_network_attempts"] == 0
        assert reference_report["baseline"]["trace_sha256"] == sha256_file(reference_trace_path)
        assert reference_report["baseline"]["latency_assumption_seconds_per_serial_attempt"] == 1
        assert reference_report["baseline"]["baseline_target_passed"] is False
        reference_end = reference_report["baseline"]["last_response_elapsed_seconds"]
        assert reference_end == reference_trace[-1]["response_elapsed_seconds"]
        directory.mkdir(parents=True, exist_ok=False)
        with patch.object(original, "create_schedule", candidate_schedule):
            candidate = original.baseline(directory / "candidate")
        trace = load_json(directory / "candidate/virtual-trace.json")
        gap = compare_traces(reference_trace, trace)
        assert gap == candidate["minimum_Google_start_gap_seconds"] >= 65
        last = candidate["last_response_elapsed_seconds"]
        result = {
            "method": METHOD,
            "reference_fixture_canonical_sha256": harness_sha,
            "candidate_fixture_canonical_sha256": sha256_bytes(
                Path(__file__).read_bytes().replace(b"\r\n", b"\n")
            ),
            "frozen_battery_file_sha256": sha256_file(original.BATTERY),
            "frozen_prompt_lock_file_sha256": sha256_file(
                original.BATTERY.with_suffix(".prompt-lock.json")
            ),
            "reference_report_sha256": sha256_file(reference_report_path),
            "reference_archive_checksums_sha256": sha256_file(reference_index_path),
            "reference_archived_files_verified": len(index),
            "reference_last_response_elapsed_seconds": reference_end,
            "unchanged_target_seconds": original.TARGET,
            "unchanged_hard_deadline_seconds": original.DEADLINE,
            "replications": REPLICATIONS,
            "same_order_prompts_request_and_response_hashes": True,
            "last_candidate_center_minutes": (REPLICATIONS - 1) * CANDIDATE_CENTER_SPACING_MINUTES,
            "target_margin_seconds": round(original.TARGET - last, 6),
            "improvement_seconds": round(reference_end - last, 6),
            "candidate": candidate,
            "official_longitudinal_data": False,
            "provider_network_attempts": 0,
            "xai": "NOT_RUN",
            "W01": "NOT_RUN",
            "official_lock_or_certificate_created": False,
            "FUTURE_OFFICIAL_EXECUTION_READY": False,
        }
        original.save(directory / "report.json", result)
        original.save(
            directory / "archive-checksums.json",
            {
                p.relative_to(directory).as_posix(): sha256_file(p)
                for p in sorted(directory.rglob("*"))
                if p.is_file()
            },
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

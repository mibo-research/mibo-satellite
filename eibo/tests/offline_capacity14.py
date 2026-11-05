"""Run the prospective runtime on the archived retimed plan and synthetic faults."""

from __future__ import annotations

import argparse
import json
import os
import socket
from collections import Counter
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import offline_capacity12 as fixtures

from eibo.artifacts import load_battery, load_manifest, load_scientific_artifact_registry
from eibo.models import load_model_lock
from eibo.prospective_qc import verify_run
from eibo.prospective_runtime import HARD, SERIES, TARGET, Cell, bind_four_provider_schedule
from eibo.prospective_runtime import run_offline as run
from eibo.qualification import FIRST_PARTY_HOSTS
from eibo.scheduling import load_schedule
from eibo.util import SECRET_ENV_NAMES, load_json, sha256_bytes, sha256_file

HOST_TO_SERIES = {FIRST_PARTY_HOSTS[provider]: sid for sid, provider in SERIES.items()}
OUTCOMES = {"M01": "refusal", "M02": "cap", "M03": "block", "M05": "short"}
MICRO_USD = 100_000


class VirtualClock:
    def __init__(self, start=fixtures.ANCHOR):
        self.current = start

    def now(self):
        return self.current

    def sleep(self, seconds):
        self.current += timedelta(seconds=seconds)

    @property
    def elapsed(self):
        return (self.current - fixtures.ANCHOR).total_seconds()


def build_cell(sid, number=1, replication=1, due=0):
    items = load_battery(fixtures.BATTERY).items
    item = items[number - 1]
    return Cell(
        f"FAULT-{sid}-{item.item_id}-R{replication:02d}",
        sid,
        item.item_id,
        replication,
        fixtures.MODELS[sid],
        item.prompt,
        item.prompt_sha256,
        fixtures.ANCHOR + timedelta(seconds=due),
    )


def full_volume(output, reference):
    reference_report = load_json(reference / "report.json")
    index = load_json(reference / "archive-checksums.json")
    assert sha256_file(reference / "report.json") == index["report.json"]
    battery = load_battery(fixtures.BATTERY)
    panels = {}
    for env in fixtures.PANELS:
        directory = reference / "candidate" / env
        manifest = load_manifest(directory / "manifest.json")
        for path in (manifest.source, manifest.model_lock_path, manifest.schedule_path):
            assert sha256_file(path) == index[path.relative_to(reference).as_posix()]
        assert not manifest.official and manifest.protocol_version == "OFFLINE_SYNTHETIC_ONLY"
        panels[env] = (
            manifest,
            load_model_lock(manifest.model_lock_path),
            load_schedule(manifest.schedule_path),
        )
    cells = bind_four_provider_schedule(battery, panels, fixtures.ANCHOR)
    trace_path = reference / "candidate/virtual-trace.json"
    assert sha256_file(trace_path) == reference_report["candidate"]["trace_sha256"]
    expected = load_json(trace_path)
    clock = VirtualClock()
    dispatches = []
    count = Counter()

    def response(request):
        n = len(dispatches)
        previous = expected[n]
        cell = cells[n]
        sid = HOST_TO_SERIES[request.url.host]
        assert request.method == "POST" and "cookie" not in request.headers
        assert sid == previous["series_id"] == cell.series
        assert cell.id == previous["observation_id"]
        assert sha256_bytes(request.content) == previous["request_sha256"]
        body = json.loads(request.content)
        assert fixtures.exact_prompt(sid, body) == cell.prompt
        count[sid] += 1
        outcome = OUTCOMES[sid] if count[sid] == 1 else "ordinary"
        payload = fixtures.canonical_json_bytes(fixtures.fake_response(sid, n + 1, outcome))
        assert sha256_bytes(payload) == previous["response_sha256"]
        dispatched = clock.elapsed
        clock.sleep(1)
        dispatches.append(
            {
                "id": cell.id,
                "series": sid,
                "dispatched_seconds": dispatched,
                "received_seconds": clock.elapsed,
                "outcome": outcome,
            }
        )
        return httpx.Response(
            200, content=payload, headers={"Set-Cookie": fixtures.SYNTHETIC_MARKER}
        )

    summary = run(
        output=output,
        cells=cells,
        anchor=fixtures.ANCHOR,
        transport=httpx.MockTransport(response),
        cost_bounds_micro_usd={(sid, "POST"): MICRO_USD for sid in SERIES},
        now=clock.now,
        sleep=clock.sleep,
    )
    qc = verify_run(output)
    assert len(dispatches) == summary["primary"] == qc["primary"] == 2800
    assert summary["status_counts"] == {"PRIMARY_WITHIN_TARGET": 2800}
    assert qc["minimum_google_start_gap_seconds"] == 65
    assert summary["post_by_series"] == dict.fromkeys(SERIES, 700)
    assert summary["retries_by_series"] == summary["get_by_series"] == {}
    assert summary["committed_micro_USD"] == 2800 * MICRO_USD
    assert not summary["provider_holds"] and summary["global_hold"] is None
    assert clock.elapsed <= TARGET.total_seconds()
    assert (
        abs(clock.elapsed - reference_report["candidate"]["last_response_elapsed_seconds"]) < 1e-6
    )
    fixtures.save(output / "virtual-trace.json", dispatches)
    return {
        "runtime": summary,
        "QC": qc,
        "virtual_last_response_elapsed_seconds": clock.elapsed,
        "margin_seconds": round(TARGET.total_seconds() - clock.elapsed, 6),
        "reference_report_sha256": sha256_file(reference / "report.json"),
        "reference_archive_index_sha256": sha256_file(reference / "archive-checksums.json"),
        "all_wire_request_and_response_hashes_match_reference": True,
    }


def fault(output, scenario):
    """Each case enters the same admission transport, runner, and QC as the full run."""
    clock = VirtualClock()
    sid = "M03" if scenario in {"retry_advice", "retry_deadline"} else "M01"
    cells = [build_cell(sid, 1), build_cell(sid, 2)]
    cost = {(sid, "POST"): MICRO_USD}
    metadata = ()
    if scenario == "metadata_cap":
        metadata = ((sid, 0),) * 4
        cost[sid, "GET"] = MICRO_USD
    if scenario == "unknown_cost":
        cells.append(build_cell("M05", 1))
        cost["M05", "POST"] = None
    if scenario == "cost_cap":
        cost[sid, "POST"] = 500_000_000
    if scenario == "cutoff":
        clock.current += HARD
    if scenario in {"late", "retry_deadline", "at_hard"}:
        clock.current += HARD - timedelta(seconds=1)
    calls = []

    def response(request):
        calls.append((request.method, clock.elapsed))
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": fixtures.MODELS[sid]}]})
        if scenario == "ambiguous" and len(calls) == 1:
            raise httpx.ReadTimeout("synthetic response loss")
        if scenario in {"retry_advice", "retry_deadline", "two_failures"} and (
            len(calls) == 1 or scenario == "two_failures"
        ):
            body = {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [{"retryDelay": "180s"}],
                }
            }
            return httpx.Response(429, json=body, headers={"Retry-After": "150"})
        if scenario == "not_technical":
            return httpx.Response(429, json={"error": {"type": "content_policy_violation"}})
        if scenario == "late":
            clock.sleep(2)
        if scenario == "at_hard":
            clock.sleep(1)
        status = 503 if scenario == "scientific_503" else 200
        body = fixtures.fake_response(sid, len(calls), "refusal" if status == 503 else "ordinary")
        return httpx.Response(status, json=body)

    kwargs = {
        "output": output,
        "cells": cells,
        "anchor": fixtures.ANCHOR,
        "transport": httpx.MockTransport(response),
        "cost_bounds_micro_usd": cost,
        "now": clock.now,
        "sleep": clock.sleep,
        "metadata": metadata,
    }
    summary = run(**kwargs)
    qc = verify_run(output)
    before = list(calls)
    try:
        run(**{**kwargs, "transport": httpx.MockTransport(response)})
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing archive was accepted for replay")
    assert calls == before
    return {"runtime": summary, "QC": qc, "mock_wire_calls": calls}


FAULTS = {
    "cutoff": ([], {"NOT_SENT": 2}, 0),
    "late": ([("POST", 86399)], {"LATE_NONPRIMARY": 1, "NOT_SENT": 1}, 1),
    "at_hard": ([("POST", 86399)], {"PRIMARY_TARGET_OVERRUN": 1, "NOT_SENT": 1}, 1),
    "retry_deadline": ([("POST", 86399)], {"NO_SLOT_BEFORE_DEADLINE": 2}, 1),
    "ambiguous": (
        [("POST", 0), ("POST", 0)],
        {"AMBIGUOUS_SEND_HOLD": 1, "PRIMARY_WITHIN_TARGET": 1},
        2,
    ),
    "unknown_cost": ([], {"NOT_SENT": 3}, 0),
    "cost_cap": ([("POST", 0)], {"PRIMARY_WITHIN_TARGET": 1, "COST_LIMIT": 1}, 1),
    "metadata_cap": ([("GET", 0)] * 3, {"NOT_SENT": 2}, 3),
    "retry_advice": ([("POST", 0), ("POST", 180), ("POST", 245)], {"PRIMARY_WITHIN_TARGET": 2}, 3),
    "scientific_503": ([("POST", 0), ("POST", 0)], {"PRIMARY_WITHIN_TARGET": 2}, 2),
    "not_technical": ([("POST", 0)], {"UNCONFIRMED_RESPONSE_HOLD": 1, "NOT_SENT": 1}, 1),
    "two_failures": (
        [("POST", 0), ("POST", 150), ("POST", 300), ("POST", 450)],
        {"TECHFAIL": 2},
        4,
    ),
}


def verify_fault(result, scenario):
    wire, statuses, admissions = FAULTS[scenario]
    assert result["mock_wire_calls"] == wire
    assert result["runtime"]["status_counts"] == statuses
    assert result["QC"]["integrity_passed"]
    assert result["QC"]["admission_receipts"] == admissions
    if scenario == "ambiguous":
        assert result["runtime"]["committed_micro_USD"] == 2 * MICRO_USD
        assert result["runtime"]["retries_by_series"] == {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_output_directory", type=Path)
    parser.add_argument("--compare-to", required=True, type=Path)
    args = parser.parse_args()
    output = args.new_output_directory.resolve()
    reference = args.compare_to.resolve()
    if output.is_relative_to(reference):
        parser.error("cannot write into the reference archive")
    for name in SECRET_ENV_NAMES:
        try:
            del os.environ[name]
        except KeyError:
            pass
    with (
        patch.object(socket, "getaddrinfo", fixtures.forbidden_network),
        patch.object(socket.socket, "connect", fixtures.forbidden_network),
        patch.object(socket.socket, "connect_ex", fixtures.forbidden_network),
        patch.object(socket.socket, "sendto", fixtures.forbidden_network),
    ):
        load_scientific_artifact_registry(fixtures.ROOT / "protocol/scientific-artifacts.yaml")
        output.mkdir(parents=True, exist_ok=False)
        result = {
            "scope": "PROSPECTIVE_PRODUCTION_CODE_WITH_SYNTHETIC_TRANSPORT",
            "OFFICIAL_LONGITUDINAL_DATA": False,
            "FUTURE_OFFICIAL_EXECUTION_READY": False,
            "provider_network_attempts": 0,
            "W01": "NOT_RUN",
            "xai": "NOT_RUN",
            "implementation_sha256_canonical_lf": {
                path: sha256_bytes((fixtures.ROOT / path).read_bytes().replace(b"\r\n", b"\n"))
                for path in (
                    "src/eibo/prospective_runtime.py",
                    "src/eibo/prospective_qc.py",
                    "src/eibo/adapters/prospective_policy.py",
                    "tests/offline_capacity14.py",
                )
            },
            "full_volume": full_volume(output / "full-volume", reference),
        }
        results = {}
        for scenario in FAULTS:
            results[scenario] = fault(output / "faults" / scenario, scenario)
            verify_fault(results[scenario], scenario)
        result["faults"] = results
        fixtures.save(output / "report.json", result)
        fixtures.save(
            output / "archive-checksums.json",
            {
                p.relative_to(output).as_posix(): sha256_file(p)
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

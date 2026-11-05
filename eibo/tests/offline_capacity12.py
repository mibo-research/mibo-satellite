"""Manual, offline-only EIBO-F01 engineering exercise. Not an official runner.

Run with the module's dev Python: python tests/offline_capacity12.py NEW_OUTPUT_DIRECTORY
All network traffic is intercepted. No provider credentials or live metadata are used.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Condition
from unittest.mock import patch

import httpx

from eibo.adapters import make_adapter
from eibo.adapters.perplexity_w0 import PerplexityAgentW0Adapter
from eibo.artifacts import load_battery, load_manifest, load_scientific_artifact_registry
from eibo.closeout import MODELS
from eibo.errors import ImmutabilityError, ProviderError
from eibo.live_qualification import SAMPLING
from eibo.models import resolve_models
from eibo.qc import run_qc
from eibo.qualification import FIRST_PARTY_HOSTS, assert_first_party
from eibo.rehearsal4 import PROVIDERS, ControlledAdapter, retry_after
from eibo.runner import run_wave
from eibo.scheduling import create_schedule, load_schedule
from eibo.util import (
    SECRET_ENV_NAMES,
    artifact_hash,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    sha256_file,
    write_immutable,
)

ROOT = Path(__file__).resolve().parents[1]
BATTERY = ROOT / "battery/ebb-ja-v1.0.yaml"
ANCHOR = datetime(2000, 1, 3, tzinfo=UTC)  # Virtual reference only, never a Wave date.
TARGET = 18 * 3600
DEADLINE = 24 * 3600
MOCK_LATENCY = 1
PANELS = {"CLOSED": ("M01", "M02", "M03"), "NATIVE": ("M05",)}
SYNTHETIC_MARKER = "offline-fixture-value"
AUTH_HEADERS = {"authorization", "x-api-key", "x-goog-api-key", "cookie", "set-cookie"}


def save(path, value):
    write_immutable(path, canonical_json_bytes(value) + b"\n")


def panel(path, environment, series, *, k=10, hours=18):
    manifest = {
        "status": "ENGINEERING",
        "approved": False,
        "wave_id": f"OFFLINE-FIXTURE-{environment}",
        "site_id": "MIBO-SITE-OFFLINE-FIXTURE",
        "official_longitudinal_data": False,
        "protocol_version": "OFFLINE_SYNTHETIC_ONLY",
        "battery": str(BATTERY),
        "model_registry": "registry.json",
        "model_lock": "synthetic-model-fixture.json",
        "schedule": "synthetic-schedule-fixture.json",
        "environment": environment,
        "replications": k,
        "random_seed": f"OFFLINE-CAPACITY-12-{environment}",
        "field_window": {
            "start": ANCHOR.isoformat(),
            "end": (ANCHOR + timedelta(hours=hours)).isoformat(),
        },
        "sampling": {PROVIDERS[sid]: SAMPLING[sid] for sid in series},
        "max_technical_attempts": 2,
        "retry_delays_minutes": [2],
    }
    save(path / "manifest.json", manifest)
    save(
        path / "registry.json",
        {
            "approved": False,
            "series": [{"series_id": sid, "provider": PROVIDERS[sid]} for sid in series],
        },
    )
    loaded = load_manifest(path / "manifest.json")
    battery = load_battery(BATTERY)
    lock = resolve_models(loaded, {sid: MODELS[sid] for sid in series}, {}, verify_live=False)
    assert all(not row["live_verified"] and not row["pinning_verified"] for row in lock["models"])
    schedule = create_schedule(loaded, battery, lock)
    assert load_schedule(loaded.schedule_path) == schedule
    return loaded, battery, lock, schedule


def fake_response(sid, number, outcome="ordinary"):
    model = MODELS[sid]
    text = "SYNTHETIC; NOT A SCIENTIFIC RESPONSE"
    base = {"id": f"synthetic-{sid}-{number}", "model": model, "usage": {"output_tokens": 8}}
    if sid == "M02":
        return {
            **base,
            "stop_reason": "max_tokens" if outcome == "cap" else "end_turn",
            "content": [{"type": "text", "text": text}],
        }
    if sid == "M03":
        base = {
            "responseId": base["id"],
            "modelVersion": model,
            "usageMetadata": {"candidatesTokenCount": 8},
        }
        if outcome == "block":
            return {**base, "promptFeedback": {"blockReason": "SAFETY"}}
        return {
            **base,
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}],
        }
    content = {"type": "output_text", "text": "短" if outcome == "short" else text}
    if outcome == "refusal":
        content = {"type": "refusal", "refusal": text}
    return {**base, "status": "completed", "output": [{"type": "message", "content": [content]}]}


def exact_prompt(sid, body):
    if sid == "M01":
        return body["input"][0]["content"][0]["text"]
    if sid == "M02":
        return body["messages"][0]["content"]
    if sid == "M03":
        return body["contents"][0]["parts"][0]["text"]
    return body["input"][0]["content"]


def make_mock(sid, handler):
    provider = PROVIDERS[sid]
    client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False
    )
    options = {
        "client": client,
        "api_key": SYNTHETIC_MARKER,
        "base_url": f"https://{FIRST_PARTY_HOSTS[provider]}",
    }
    adapter = (
        PerplexityAgentW0Adapter(**options) if sid == "M05" else make_adapter(provider, **options)
    )
    return client, adapter


class MockAdmission:
    """Test-only clock and accounting. No provider-rate or cost claims."""

    def __init__(self):
        self.clock = 0.0
        self.google_last = float("-inf")
        self.post = Counter()
        self.retries = Counter()
        self.get = Counter()
        self.committed = Decimal(0)
        self.holds = set()

    def admit(self, sid, *, due=0, retry=False, cell="", cost=Decimal("0.10"), method="POST"):
        assert sid in PROVIDERS
        self.clock = max(self.clock, due)
        if method == "POST" and sid == "M03":
            self.clock = max(self.clock, self.google_last + 65)
        reason = None
        if self.clock >= DEADLINE:
            reason = "HARD_DEADLINE"
        elif cell in self.holds:
            reason = "AMBIGUOUS_SEND_HOLD"
        elif cost is None:
            reason = "COST_BOUND_UNKNOWN"
        elif self.committed + cost > Decimal(500):
            reason = "COST_CEILING"
        elif method == "POST" and (self.post[sid] >= 770 or self.post.total() >= 3080):
            reason = "POST_CEILING"
        elif method == "GET" and (self.get[sid] >= 3 or self.get.total() >= 12):
            reason = "GET_CEILING"
        elif retry and (self.retries[sid] >= 70 or self.retries.total() >= 280):
            reason = "RETRY_CEILING"
        if reason:
            raise ProviderError(reason)
        self.committed += cost
        if method == "GET":
            self.get[sid] += 1
        else:
            self.post[sid] += 1
            if retry:
                self.retries[sid] += 1
            if sid == "M03":
                self.google_last = self.clock
        return self.clock


class WireAudit:
    def send(self, adapter, request):
        assert_first_party(request, adapter.provider)
        assert request.method == "POST"
        assert not adapter.client.follow_redirects

        def audit(wire):
            assert wire.content == request.body_bytes and str(wire.url) == request.url

        adapter.client.event_hooks["request"] = [audit]
        return adapter.send(request)


def run_panel(fixture, adapters, **kwargs):
    manifest, battery, lock, schedule = fixture
    return run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        now=manifest.end,
        adapter_factory=adapters.__getitem__,
        **kwargs,
    )


def l0_hashes(directory):
    return {
        p.relative_to(directory).as_posix(): sha256_file(p)
        for p in directory.rglob("*")
        if p.is_file() and "L0_raw" in p.relative_to(directory).parts
    }


def baseline(directory):
    fixtures = {env: panel(directory / env, env, series) for env, series in PANELS.items()}
    # A second use of the real scheduler tests row-level determinism and does not dispatch.
    for env, series in PANELS.items():
        duplicate = panel(directory / "schedule-reproducibility" / env, env, series)
        assert duplicate[3]["rows"] == fixtures[env][3]["rows"]
    rows = sorted(
        (row for _, _, _, schedule in fixtures.values() for row in schedule["rows"]),
        key=lambda r: (r["planned_start_utc"], r["execution_position"], r["environment"]),
    )
    expected = {
        (sid, item.item_id, n)
        for sid in PROVIDERS
        for item in fixtures["CLOSED"][1].items
        for n in range(1, 11)
    }
    assert len(rows) == 2800
    assert len({row["observation_id"] for row in rows}) == 2800
    assert {(r["series_id"], r["item_id"], r["replication_number"]) for r in rows} == expected
    assert {r["environment"] for r in rows if r["series_id"] == "M05"} == {"NATIVE"}
    planned = [
        (datetime.fromisoformat(r["planned_start_utc"]) - ANCHOR).total_seconds() for r in rows
    ]
    assert all(0 <= when <= TARGET for when in planned)
    prompt_hashes = {item.item_id: item.prompt_sha256 for item in fixtures["CLOSED"][1].items}
    admissions, condition, trace = MockAdmission(), Condition(), []
    first_outcome = {"M01": "refusal", "M02": "cap", "M03": "block", "M05": "short"}
    stopped = False

    def receive(sid, request):
        env = "NATIVE" if sid == "M05" else "CLOSED"
        with condition:
            assert condition.wait_for(
                lambda: (
                    stopped or len(trace) >= len(rows) or rows[len(trace)]["environment"] == env
                ),
                timeout=30,
            ), "mock panel coordination timed out"
            assert not stopped and len(trace) < len(rows)
            index = len(trace)
            row = rows[index]
            assert row["series_id"] == sid
            assert row["requested_model"] == MODELS[sid]
            assert (
                prompt_hashes[row["item_id"]]
                == row["prompt_sha256"]
                == sha256_bytes(exact_prompt(sid, json.loads(request.content)).encode("utf-8"))
            )
            start = admissions.admit(sid, due=planned[index], cell=row["observation_id"])
            admissions.clock += MOCK_LATENCY
            outcome = first_outcome[sid] if admissions.post[sid] == 1 else "ordinary"
            body = fake_response(sid, index + 1, outcome)
            trace.append(
                {
                    "observation_id": row["observation_id"],
                    "series_id": sid,
                    "item_id": row["item_id"],
                    "replication_number": row["replication_number"],
                    "environment": env,
                    "planned_start_elapsed_seconds": planned[index],
                    "dispatch_elapsed_seconds": start,
                    "response_elapsed_seconds": admissions.clock,
                    "synthetic_outcome": outcome,
                    "request_sha256": sha256_bytes(request.content),
                    "response_sha256": artifact_hash(body),
                }
            )
            condition.notify_all()
            return httpx.Response(
                200,
                content=canonical_json_bytes(body),
                headers={"Set-Cookie": SYNTHETIC_MARKER, "Authorization": SYNTHETIC_MARKER},
            )

    clients = []
    adapters = {}
    for sid, provider in PROVIDERS.items():
        client, adapter = make_mock(sid, lambda req, sid=sid: receive(sid, req))
        clients.append(client)
        adapters[provider] = ControlledAdapter(adapter, sid, WireAudit())

    def run(env):
        nonlocal stopped
        try:
            return run_panel(fixtures[env], adapters)
        except BaseException:
            with condition:
                stopped = True
                condition.notify_all()
            raise

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {env: pool.submit(run, env) for env in PANELS}
            stats = {env: job.result() for env, job in futures.items()}
        assert len(trace) == 2800
        assert admissions.post == dict.fromkeys(PROVIDERS, 700)
        assert not admissions.retries
        assert stats["CLOSED"]["completed"] == 2100 and stats["NATIVE"]["completed"] == 700
        assert not any(s["technical_failure"] or s["not_due"] for s in stats.values())
        before = l0_hashes(directory)
        assert len(before) == 2800 * 5
        qcs = {}
        traced = {record["observation_id"]: record for record in trace}
        for env, (manifest, battery, lock, schedule) in fixtures.items():
            replay = run_panel(fixtures[env], adapters)
            assert replay["already_reconciled"] == len(schedule["rows"])
            assert replay["completed"] == 0
            qcs[env] = qc = run_qc(manifest, battery, lock, schedule)
            assert qc["passed"] and not qc["warnings"]
            assert qc["status_counts"] == {"OBSERVED": len(schedule["rows"])}
            assert sha256_file(Path(qc["canonical_path"])) == qc["canonical_sha256"]
            for line in Path(qc["canonical_path"]).read_bytes().splitlines():
                record = json.loads(line)
                row = traced[record["observation_id"]]
                assert record["OFFICIAL_LONGITUDINAL_DATA"] is False
                assert record["attempts"] == 1
                assert record["returned_model"] == MODELS[row["series_id"]]
                assert record["request_sha256"] == row["request_sha256"]
                assert record["response_sha256"] == row["response_sha256"]
                raw = manifest.source.parent / "L0_raw" / record["observation_id"]
                for suffix, field in (
                    ("request", "request_record_sha256"),
                    ("response", "response_envelope_sha256"),
                ):
                    meta = load_json(raw / f"{record['observation_id']}-A01.{suffix}.json")
                    assert meta.pop(field) == artifact_hash(meta)
                    headers = meta["request"]["headers"] if suffix == "request" else meta["headers"]
                    assert not AUTH_HEADERS.intersection(key.lower() for key in headers)
                    assert SYNTHETIC_MARKER not in json.dumps(meta)
        assert len(trace) == 2800 and l0_hashes(directory) == before
    finally:
        for client in clients:
            client.close()
    starts = [row["dispatch_elapsed_seconds"] for row in trace if row["series_id"] == "M03"]
    gap = min(b - a for a, b in zip(starts, starts[1:], strict=False))
    assert gap >= 65
    assert all(row["dispatch_elapsed_seconds"] < DEADLINE for row in trace)
    save(directory / "virtual-trace.json", trace)
    return {
        "scope": "SYNTHETIC_OFFLINE_ONLY",
        "scheduled": len(rows),
        "completed": len(trace),
        "by_series": {
            sid: {
                "completed": admissions.post[sid],
                "completed_by_18h": sum(
                    r["response_elapsed_seconds"] <= TARGET for r in trace if r["series_id"] == sid
                ),
                "last_response_elapsed_seconds": max(
                    r["response_elapsed_seconds"] for r in trace if r["series_id"] == sid
                ),
                "synthetic_outcomes": dict(
                    Counter(r["synthetic_outcome"] for r in trace if r["series_id"] == sid)
                ),
            }
            for sid in PROVIDERS
        },
        "baseline_target_passed": admissions.clock <= TARGET,
        "baseline_hard_window_passed": admissions.clock <= DEADLINE,
        "last_response_elapsed_seconds": admissions.clock,
        "minimum_Google_start_gap_seconds": gap,
        "latency_assumption_seconds_per_serial_attempt": MOCK_LATENCY,
        "test_only_mock_reserved_USD": str(admissions.committed),
        "scientific_outcome_retries": admissions.retries.total(),
        "L0_files_verified": len(before),
        "repeat_scheduler_rows_identical": True,
        "replay_additional_dispatches": 0,
        "QC": {
            env: {
                key: qc[key]
                for key in (
                    "passed",
                    "status_counts",
                    "canonical_records",
                    "canonical_sha256",
                    "qc_report_sha256",
                )
            }
            for env, qc in qcs.items()
        },
        "trace_sha256": sha256_file(directory / "virtual-trace.json"),
    }


def forbidden_network(*_args, **_kwargs):
    raise AssertionError("outbound network forbidden in offline exercise")


def fault_runner(directory, case):
    """Exercise the real runner's first cell through synthetic failures."""
    sid = "M03"
    fixture = panel(directory, "CLOSED", (sid,), k=1)
    manifest, battery, lock, schedule = fixture
    row = schedule["rows"][0]
    cell = row["observation_id"]
    ledger = MockAdmission()
    wire_trace, stops, sleeps = [], [], []
    cooldown = 0.0

    def receive(request):
        assert request.method == "POST"
        wire_trace.append(
            {
                "elapsed": ledger.clock,
                "request_sha256": sha256_bytes(request.content),
            }
        )
        if case == "crash":
            raise RuntimeError("synthetic interrupted send")
        if case == "ambiguous":
            raise httpx.ReadTimeout("synthetic lost response")
        if len(wire_trace) == 1 and case in {"retry", "deadline_retry"}:
            return httpx.Response(
                429,
                headers={"Retry-After": "150"},
                json={"error": {"details": [{"retryDelay": "180s"}]}},
            )
        if case == "late":
            ledger.clock += 2
        return httpx.Response(200, json=fake_response(sid, len(wire_trace)))

    class FaultGuard(WireAudit):
        def send(self, adapter, request):
            nonlocal cooldown
            try:
                ledger.admit(
                    sid,
                    due=cooldown,
                    retry=bool(wire_trace),
                    cell=cell,
                    cost=None if case == "unknown_cost" else Decimal("0.10"),
                )
            except ProviderError as exc:
                stops.append(str(exc))
                raise
            # An immutable test receipt precedes the simulated send, including lost responses.
            save(
                directory / f"synthetic-dispatch-{len(wire_trace) + 1}.json",
                {
                    "cell": cell,
                    "elapsed": ledger.clock,
                    "request_sha256": sha256_bytes(request.body_bytes),
                    "official_longitudinal_data": False,
                },
            )
            try:
                return super().send(adapter, request)
            except Exception as exc:
                captured = getattr(exc, "provider_response", None)
                if captured is not None:
                    cooldown = ledger.clock + retry_after(captured, ANCHOR.timestamp())
                if isinstance(exc.__cause__, httpx.ReadTimeout):
                    ledger.holds.add(cell)
                raise

    def sleep(seconds):
        sleeps.append(seconds)
        ledger.clock += seconds

    if case in {"late", "deadline_retry"}:
        ledger.clock = DEADLINE - 1
    if case == "deadline_first":
        ledger.clock = DEADLINE
    client, adapter = make_mock(sid, receive)
    adapters = {PROVIDERS[sid]: ControlledAdapter(adapter, sid, FaultGuard())}
    try:
        if case == "crash":
            try:
                run_panel(fixture, adapters, max_observations=1, sleep=sleep)
            except RuntimeError as exc:
                assert str(exc) == "synthetic interrupted send"
            else:
                raise AssertionError("crash fixture must interrupt execution")
            initial = l0_hashes(directory)
            try:
                run_panel(fixture, adapters, max_observations=1, sleep=sleep)
            except ImmutabilityError:
                pass
            else:
                raise AssertionError("incomplete attempt was automatically repeated")
            assert len(wire_trace) == 1 and l0_hashes(directory) == initial
            return {"wire_attempts": 1, "restart_refused_existing_attempt": True}
        stats = run_panel(fixture, adapters, max_observations=1, sleep=sleep)
    finally:
        client.close()

    raw = directory / "L0_raw" / cell
    completion = load_json(raw / "completion.json")
    qc = run_qc(manifest, battery, lock, schedule)
    assert qc["status_counts"]["MISSING"] == 69
    assert not qc["errors"]
    if case in {"retry", "deadline_retry"}:
        first = load_json(raw / f"{cell}-A01.response.json")
        assert first["status_code"] == 429
        assert first["body_sha256"] == sha256_file(raw / f"{cell}-A01.response.body")
        assert sleeps == [120]
    if case == "retry":
        assert [r["elapsed"] for r in wire_trace] == [0, 180]
        assert stats["completed"] == 1 and completion["scientifically_completed"] is True
        assert completion["attempts"] == 2 and not stops
    elif case == "late":
        assert len(wire_trace) == 1 and not stops
        assert wire_trace[0]["elapsed"] == DEADLINE - 1 and ledger.clock == DEADLINE + 1
        assert completion["status"] == "OBSERVED"  # Existing runner lacks timing classification.
        response_path = raw / f"{cell}-A01.response.body"
        assert completion["response_sha256"] == sha256_file(response_path)
        save(
            directory / "test-only-lateness.json",
            {
                "observation_id": cell,
                "response_elapsed_seconds": ledger.clock,
                "classification": "LATE_NONPRIMARY",
                "production_runner_emitted_label": False,
                "official_longitudinal_data": False,
            },
        )
    else:
        expected = {
            "deadline_first": ("HARD_DEADLINE", 0),
            "deadline_retry": ("HARD_DEADLINE", 1),
            "unknown_cost": ("COST_BOUND_UNKNOWN", 0),
            "ambiguous": ("AMBIGUOUS_SEND_HOLD", 1),
        }
        reason, count = expected[case]
        assert stops == [reason] and len(wire_trace) == count
        assert completion["status"] == "TECHFAIL" and stats["technical_failure"] == 1
        if case == "ambiguous":
            assert sleeps == [120]  # The generic runner offered a retry; mock guard blocked it.
    result = {
        "wire_attempts": len(wire_trace),
        "wire_trace": wire_trace,
        "guard_stop_reasons": stops,
        "runner_retry_sleep_seconds": sleeps,
        "runner_completion_status": completion["status"],
        "QC_missing": qc["status_counts"]["MISSING"],
    }
    if case == "late":
        result["test_only_classification"] = "LATE_NONPRIMARY"
        result["production_runner_emitted_lateness_label"] = False
    return result


def faults(directory):
    def blocked(ledger, expected, **kwargs):
        before = ledger.committed, ledger.post.total(), ledger.get.total(), ledger.retries.total()
        try:
            ledger.admit("M01", **kwargs)
        except ProviderError as exc:
            assert str(exc) == expected
        else:
            raise AssertionError(f"mock admission unexpectedly passed: {expected}")
        assert before == (
            ledger.committed,
            ledger.post.total(),
            ledger.get.total(),
            ledger.retries.total(),
        )

    ledger = MockAdmission()
    ledger.committed = Decimal("499.95")
    blocked(ledger, "COST_CEILING")
    ledger = MockAdmission()
    ledger.post["M01"] = 770
    blocked(ledger, "POST_CEILING")
    ledger = MockAdmission()
    ledger.post.update(dict.fromkeys(PROVIDERS, 770))
    blocked(ledger, "POST_CEILING")
    ledger = MockAdmission()
    ledger.retries["M01"] = 70
    blocked(ledger, "RETRY_CEILING", retry=True)
    ledger = MockAdmission()
    ledger.retries.update(dict.fromkeys(PROVIDERS, 70))
    blocked(ledger, "RETRY_CEILING", retry=True)
    ledger = MockAdmission()
    ledger.get["M01"] = 3
    blocked(ledger, "GET_CEILING", method="GET")
    ledger = MockAdmission()
    ledger.get.update(dict.fromkeys(PROVIDERS, 3))
    blocked(ledger, "GET_CEILING", method="GET")
    return {
        "mock_admission_only_ceiling_cases": 7,
        "runner_and_mock_admission_cases": {
            case: fault_runner(directory / case, case)
            for case in (
                "retry",
                "deadline_first",
                "deadline_retry",
                "late",
                "unknown_cost",
                "ambiguous",
                "crash",
            )
        },
        "test_only_controls_not_implemented_by_generic_runner": [
            "mixed_panel_pacing",
            "retry_after",
            "hard_deadline_at_every_attempt",
            "late_nonprimary_classification",
            "currency_and_attempt_admission",
            "ambiguous_send_retry_exclusion",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_output_directory", type=Path)
    args = parser.parse_args()
    directory = args.new_output_directory.resolve()
    # Process-local only. Do not load dotenv, inherited provider credentials or the registry.
    for name in SECRET_ENV_NAMES:
        try:
            del os.environ[name]
        except KeyError:
            pass
    directory.mkdir(parents=True, exist_ok=False)
    with (
        patch.object(socket, "getaddrinfo", forbidden_network),
        patch.object(socket.socket, "connect", forbidden_network),
        patch.object(socket.socket, "connect_ex", forbidden_network),
        patch.object(socket.socket, "sendto", forbidden_network),
    ):
        registry_path = ROOT / "protocol/scientific-artifacts.yaml"
        load_scientific_artifact_registry(registry_path)
        result = {
            "fixture_script_canonical_sha256": sha256_bytes(
                Path(__file__).read_bytes().replace(b"\r\n", b"\n")
            ),
            "scientific_registry_file_sha256": sha256_file(registry_path),
            "frozen_battery_file_sha256": sha256_file(BATTERY),
            "frozen_prompt_lock_file_sha256": sha256_file(BATTERY.with_suffix(".prompt-lock.json")),
            "official_longitudinal_data": False,
            "provider_network_attempts": 0,
            "xai": "NOT_RUN",
            "W01": "NOT_RUN",
            "official_certificate_issued": False,
            "baseline": baseline(directory / "baseline"),
            "faults": faults(directory / "faults"),
            "FUTURE_OFFICIAL_EXECUTION_READY": False,
        }
        save(directory / "report.json", result)
        save(
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

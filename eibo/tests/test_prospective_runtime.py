from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import offline_capacity12 as fixtures
import offline_capacity14 as dry
import pytest

from eibo import prospective_runtime as runtime
from eibo.errors import ValidationError
from eibo.prospective_qc import verify_run
from eibo.util import load_json


@pytest.mark.parametrize("scenario", tuple(dry.FAULTS))
def test_prospective_transport_fault_matrix(tmp_path: Path, scenario: str) -> None:
    output = tmp_path / "run"
    dry.verify_fault(dry.fault(output, scenario), scenario)
    if scenario == "ambiguous":
        cell = output / "L0" / dry.build_cell("M01").id
        completion = load_json(cell / "completion.json")
        assert completion["reserved_attempts"] == 1
        assert not (cell / "attempt-2.request.json").exists()
        assert (cell / "attempt-1.intent.json").exists()
    elif scenario == "late":
        cell = output / "L0" / dry.build_cell("M01").id
        assert (cell / "attempt-1.response.body").exists()
        completion = load_json(cell / "completion.json")
        assert completion["scientifically_completed"] is True
        assert completion["primary"] is False
    elif scenario == "cost_cap":
        intent = load_json(next(output.rglob("*.intent.json")))
        assert intent["committed_micro_USD"] == runtime.MAX_MICRO_USD
        assert intent["budget_warning"] is True


@pytest.mark.parametrize(
    ("counter", "value", "method", "cell", "reason"),
    [
        ("post", {"M01": 770}, "POST", "A", "POST_ATTEMPT_LIMIT"),
        ("post", {"M02": 1100, "M03": 1000, "M05": 980}, "POST", "A", "POST_ATTEMPT_LIMIT"),
        ("get", {"M01": 3}, "GET", None, "METADATA_ATTEMPT_LIMIT"),
        ("get", {"M02": 4, "M03": 4, "M05": 4}, "GET", None, "METADATA_ATTEMPT_LIMIT"),
        ("retries", {"M01": 70}, "POST", "A", "RETRY_ATTEMPT_LIMIT"),
        ("retries", {"M02": 100, "M03": 100, "M05": 80}, "POST", "A", "RETRY_ATTEMPT_LIMIT"),
        ("attempts", {"A": 2}, "POST", "A", "CELL_ATTEMPT_LIMIT"),
        ("post", {"M02": 3092}, "GET", None, "HTTP_ATTEMPT_LIMIT"),
    ],
)
def test_attempt_ceiling_reserves_nothing_on_denial(
    tmp_path: Path,
    counter: str,
    value: dict,
    method: str,
    cell: str | None,
    reason: str,
) -> None:
    clock = dry.VirtualClock()
    guard = runtime.Admission(fixtures.ANCHOR, {("M01", method): 1}, clock.now, clock.sleep)
    getattr(guard, counter).update(value)
    if counter == "retries":
        guard.attempts["A"] = 1
    intent = tmp_path / "intent.json"
    with pytest.raises(runtime.Hold, match=reason):
        guard.reserve("M01", method, cell, intent)
    assert not intent.exists()
    assert guard.committed == 0


@pytest.mark.parametrize("value", [None, 0, -1, True, 500_000_001])
def test_invalid_cost_is_not_assumed_free(value: int | None) -> None:
    clock = dry.VirtualClock()
    guard = runtime.Admission(fixtures.ANCHOR, {("M05", "POST"): value}, clock.now, clock.sleep)
    with pytest.raises(runtime.Hold, match="COST_BOUND_UNKNOWN_OR_INVALID"):
        guard.bound("M05", "POST")


def test_boundary_rechecks_deadline_after_durable_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "run"
    clock = dry.VirtualClock(fixtures.ANCHOR + runtime.HARD - timedelta(seconds=1))
    real_save = runtime.save

    def delayed_save(path, row):
        result = real_save(path, row)
        if path.name.endswith(".intent.json"):
            clock.sleep(1)
        return result

    monkeypatch.setattr(runtime, "save", delayed_save)
    report = runtime.run_offline(
        output=output,
        cells=[dry.build_cell("M01")],
        anchor=fixtures.ANCHOR,
        transport=httpx.MockTransport(fixtures.forbidden_network),
        cost_bounds_micro_usd={("M01", "POST"): 1},
        now=clock.now,
        sleep=clock.sleep,
    )
    assert report["status_counts"] == {"HARD_DEADLINE": 1}
    assert report["committed_micro_USD"] == 1
    assert verify_run(output)["admission_receipts"] == 1
    assert not list(output.rglob("*.response.body"))


def test_clock_rollback_holds_next_send_and_preserves_received_body(tmp_path: Path) -> None:
    output = tmp_path / "run"
    clock = dry.VirtualClock()

    def response(_request):
        clock.sleep(-1)
        return httpx.Response(200, json=fixtures.fake_response("M01", 1))

    report = runtime.run_offline(
        output=output,
        cells=[dry.build_cell("M01"), dry.build_cell("M01", 2)],
        anchor=fixtures.ANCHOR,
        transport=httpx.MockTransport(response),
        cost_bounds_micro_usd={("M01", "POST"): 1},
        now=clock.now,
        sleep=clock.sleep,
    )
    assert report["status_counts"] == {"CLOCK_ROLLBACK": 1, "NOT_SENT": 1}
    assert len(list(output.rglob("*.response.body"))) == 1
    assert verify_run(output)["primary"] == 0


def test_no_live_or_unscoped_transport_can_enter(tmp_path: Path) -> None:
    clock = dry.VirtualClock()
    with (
        httpx.HTTPTransport(retries=0) as live,
        pytest.raises(
            ValidationError,
            match="live transport is disabled",
        ),
    ):
        runtime.run_offline(
            output=tmp_path / "run",
            cells=[],
            anchor=fixtures.ANCHOR,
            transport=live,
            cost_bounds_micro_usd={},
            now=clock.now,
            sleep=clock.sleep,
        )
    assert not (tmp_path / "run").exists()


def test_qc_rejects_altered_primary_flag_and_l0(tmp_path: Path) -> None:
    output = tmp_path / "run"
    dry.fault(output, "late")
    canonical = output / "observations.jsonl"
    original = canonical.read_bytes()
    rows = [json.loads(line) for line in original.splitlines()]
    rows[0]["primary"] = True
    canonical.write_bytes(b"".join(fixtures.canonical_json_bytes(r) + b"\n" for r in rows))
    with pytest.raises(ValidationError, match="primary count"):
        verify_run(output)
    canonical.write_bytes(original)
    response = next(output.rglob("*.response.body"))
    response.write_bytes(b"{}")
    with pytest.raises(ValidationError, match="response hash mismatch"):
        verify_run(output)


def test_response_with_credential_marker_is_not_archived_or_hashed(tmp_path: Path) -> None:
    output = tmp_path / "run"
    clock = dry.VirtualClock()
    marker = b"sk-" + b"synthetic-test-marker-not-a-key"
    report = runtime.run_offline(
        output=output,
        cells=[dry.build_cell("M01"), dry.build_cell("M01", 2)],
        anchor=fixtures.ANCHOR,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=marker)),
        cost_bounds_micro_usd={("M01", "POST"): 1},
        now=clock.now,
        sleep=clock.sleep,
    )
    assert report["status_counts"] == {"REDACTION_HOLD": 1, "NOT_SENT": 1}
    assert not list(output.rglob("*.response.body"))
    result = load_json(next(output.rglob("*.result.json")))
    assert "body_sha256" not in result
    assert result["body_length"] == len(marker)
    assert verify_run(output)["unobserved"] == 2


def test_provider_hold_does_not_substitute_or_send_another_cell_for_it(tmp_path: Path) -> None:
    output = tmp_path / "run"
    clock = dry.VirtualClock()
    hosts = []

    def response(request):
        hosts.append(request.url.host)
        if request.url.host == "api.openai.com":
            return httpx.Response(401, json={"error": {"type": "invalid_api_key"}})
        return httpx.Response(200, json=fixtures.fake_response("M02", 1))

    result = runtime.run_offline(
        output=output,
        cells=[dry.build_cell("M01"), dry.build_cell("M01", 2), dry.build_cell("M02")],
        anchor=fixtures.ANCHOR,
        transport=httpx.MockTransport(response),
        cost_bounds_micro_usd={("M01", "POST"): 1, ("M02", "POST"): 1},
        now=clock.now,
        sleep=clock.sleep,
    )
    assert hosts == ["api.openai.com", "api.anthropic.com"]
    assert result["post_by_series"] == {"M01": 1, "M02": 1}
    assert result["status_counts"] == {
        "UNCONFIRMED_RESPONSE_HOLD": 1,
        "NOT_SENT": 1,
        "PRIMARY_WITHIN_TARGET": 1,
    }
    assert verify_run(output)["primary"] == 1

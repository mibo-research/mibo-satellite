from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from miboe.adapters import make_adapter
from miboe.errors import ValidationError
from miboe.live_qualification import (
    FIRST_PARTY_HOSTS,
    SERIES_IDS,
    run_dress_rehearsal,
    run_provider_qualification_set,
    run_smoke_qualification,
)
from miboe.util import artifact_hash, canonical_json_bytes, sha256_file, write_immutable

ROOT = Path(__file__).parents[1]
MODELS = {
    "M01": "gpt-5.6-sol",
    "M02": "claude-opus-5",
    "M03": "gemini-3.6-flash",
    "M04": "grok-4.5",
    "M05": "sonar",
}
PROVIDERS = {
    "M01": "openai",
    "M02": "anthropic",
    "M03": "gemini",
    "M04": "xai",
    "M05": "perplexity",
}


def test_live_plan_freezes_nonofficial_seven_item_and_core_35_shapes() -> None:
    plan = yaml.safe_load(
        (ROOT / "waves/W0/live-qualification-plan.yaml").read_text(encoding="utf-8")
    )
    assert plan["official_longitudinal_data"] is False
    assert plan["qualification_item_ids"] == [f"E{i}-01" for i in range(1, 8)]
    assert plan["core_35_rehearsal"]["expected_observations"] == 35
    assert plan["core_35_rehearsal"]["closed_panel_observations"] == 28
    assert plan["core_35_rehearsal"]["native_mirror_observations"] == 7
    assert plan["governance"]["ethics_or_governance_determination"] is False
    assert plan["governance"]["agent_approval_permitted"] is False


def _response_body(provider: str, model: str) -> dict[str, Any]:
    if provider in {"openai", "xai"}:
        return {
            "id": f"resp-{provider}",
            "model": model,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "OK"}],
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "system_fingerprint": "fp_test" if provider == "xai" else None,
        }
    if provider == "anthropic":
        return {
            "id": "msg-anthropic",
            "model": model,
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    if provider == "gemini":
        return {
            "responseId": "gemini-response",
            "modelVersion": model,
            "candidates": [
                {
                    "content": {"parts": [{"text": "OK"}]},
                    "finishReason": "STOP",
                    "safetyRatings": [],
                }
            ],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
    return {
        "id": "sonar-response",
        "model": model,
        "choices": [
            {"message": {"content": "OK"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "citations": [],
        "search_results": [],
    }


def _mock_factory(
    calls: Counter[str], *, credentials: bool = True, fail_provider: str | None = None
):
    adapters: dict[str, Any] = {}

    def factory(provider: str):
        if provider in adapters:
            return adapters[provider]
        series_id = next(key for key, value in PROVIDERS.items() if value == provider)
        model = MODELS[series_id]

        def handler(request: httpx.Request) -> httpx.Response:
            calls[f"{provider}:{request.method}:{request.url.path}"] += 1
            if provider == fail_provider:
                return httpx.Response(400, json={"error": "qualification failure"})
            if request.method == "GET":
                if provider == "gemini":
                    return httpx.Response(200, json={"name": f"models/{model}"})
                if request.url.path.rstrip("/").endswith(model):
                    return httpx.Response(200, json={"id": model})
                return httpx.Response(200, json={"data": [{"id": model}]})
            body = json.loads(request.content)
            requested = body.get("model", model)
            return httpx.Response(200, json=_response_body(provider, requested))

        adapters[provider] = make_adapter(
            provider,
            api_key="unit-test-credential-value" if credentials else "",
            base_url=f"https://{FIRST_PARTY_HOSTS[provider]}",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        return adapters[provider]

    return factory


def _seed_gate(output_root: Path, stage: str, series_id: str) -> None:
    result_path = output_root / "seed" / f"{stage}-{series_id}.result.json"
    result = {
        "stage": stage,
        "series_id": series_id,
        "requested_model": MODELS[series_id],
        "returned_model": MODELS[series_id],
        "passed": True,
        "official_longitudinal_data": False,
    }
    write_immutable(result_path, canonical_json_bytes(result) + b"\n")
    core = {
        "schema_version": "1.0",
        "stage": stage,
        "series_id": series_id,
        "passed": True,
        "official_longitudinal_data": False,
        "qualified_at": "2026-08-15T00:00:00.000Z",
        "requested_model": MODELS[series_id],
        "returned_model": MODELS[series_id],
        "result_path": str(result_path.resolve()),
        "result_sha256": sha256_file(result_path),
    }
    gate = {**core, "gate_sha256": artifact_hash(core)}
    path = output_root / "gates" / f"{stage}-{series_id}.json"
    write_immutable(path, canonical_json_bytes(gate) + b"\n")


def test_q1_xai_uses_responses_cap_and_one_ordinary_request(tmp_path: Path) -> None:
    calls: Counter[str] = Counter()
    report = run_smoke_qualification(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M04"],
        adapter_factory=_mock_factory(calls),
        run_id="Q1-XAI",
    )
    assert report["passed"] is True
    assert calls["xai:POST:/v1/responses"] == 1
    result = report["results"]["M04"]
    assert result["ordinary_requests_attempted"] == 1
    assert result["returned_model"] == "grok-4.5"
    request = json.loads(
        (tmp_path / "Q1/Q1-XAI/M04/ordinary-smoke.request.body").read_text()
    )
    assert request["max_output_tokens"] == 8192
    assert "max_tokens" not in request
    assert "messages" not in request
    envelope = json.loads(
        (tmp_path / "Q1/Q1-XAI/M04/ordinary-smoke.request.json").read_text()
    )
    assert "Authorization" not in envelope["headers"]


def test_q1_does_not_call_provider_without_credential(tmp_path: Path) -> None:
    calls: Counter[str] = Counter()
    report = run_smoke_qualification(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M01"],
        adapter_factory=_mock_factory(calls, credentials=False),
        run_id="Q1-NO-CREDENTIAL",
    )
    assert report["passed"] is False
    assert report["results"]["M01"]["status"] == "BLOCKED_CREDENTIAL_MISSING"
    assert not calls


def test_q1_m02_refuses_unresolved_core_family_without_call(tmp_path: Path) -> None:
    def forbidden_factory(provider: str):
        raise AssertionError(f"adapter must not be created for unresolved {provider}")

    report = run_smoke_qualification(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M02"],
        adapter_factory=forbidden_factory,
        run_id="Q1-M02-BLOCKED",
    )
    assert report["passed"] is False
    assert report["results"]["M02"]["status"] == "BLOCKED_CORE_SERIES_UNRESOLVED"


def test_q1_provider_failure_does_not_substitute_or_block_other_series(
    tmp_path: Path,
) -> None:
    calls: Counter[str] = Counter()
    report = run_smoke_qualification(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M01", "M03"],
        adapter_factory=_mock_factory(calls, fail_provider="openai"),
        run_id="Q1-ISOLATED-FAILURE",
    )
    assert report["passed"] is False
    assert report["results"]["M01"]["passed"] is False
    assert report["results"]["M01"]["substitution_attempted"] is False
    assert report["results"]["M03"]["passed"] is True
    assert report["results"]["M03"]["requested_model"] == "gemini-3.6-flash"
    assert calls["openai:POST:/v1/responses"] == 0
    assert calls[
        "gemini:POST:/v1beta/models/gemini-3.6-flash:generateContent"
    ] == 1


def test_q2_refuses_provider_without_q1_gate(tmp_path: Path) -> None:
    def forbidden_factory(provider: str):
        raise AssertionError(f"Q2 must not contact {provider} before Q1")

    report = run_provider_qualification_set(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M03"],
        adapter_factory=forbidden_factory,
        run_id="Q2-BLOCKED",
    )
    assert report["passed"] is False
    assert report["results"]["M03"]["status"] == "BLOCKED_Q1_NOT_PASSED"


def test_q2_m05_runs_native_and_nonofficial_closed_sets(tmp_path: Path) -> None:
    calls: Counter[str] = Counter()
    factory = _mock_factory(calls)
    q1 = run_smoke_qualification(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M05"],
        adapter_factory=factory,
        run_id="Q1-M05",
    )
    assert q1["passed"] is True
    q2 = run_provider_qualification_set(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M05"],
        adapter_factory=factory,
        run_id="Q2-M05",
    )
    assert q2["passed"] is True
    result = q2["results"]["M05"]
    assert len(result["item_results"]) == 7
    assert len(result["closed_diagnostic_results"]) == 7
    assert all(
        value["classification"] == "NON_OFFICIAL_W0_ONLY"
        and value["disable_search"] is True
        for value in result["closed_diagnostic_results"]
    )
    assert calls["perplexity:POST:/v1/sonar"] == 15


def test_q2_claude_opus_records_output_cap_evidence_without_speculation(
    tmp_path: Path,
) -> None:
    _seed_gate(tmp_path, "Q1", "M02")
    calls: Counter[str] = Counter()
    report = run_provider_qualification_set(
        module_root=ROOT,
        output_root=tmp_path,
        series_ids=["M02"],
        adapter_factory=_mock_factory(calls),
        run_id="Q2-OPUS",
    )
    assert report["passed"] is True
    evidence = report["results"]["M02"]["opus_5_output_cap_evidence"]
    assert evidence["max_tokens"] == 8192
    assert evidence["stop_reason_max_tokens_count"] == 0
    assert evidence["material_constraint_interpretation"] == "HUMAN_REVIEW_REQUIRED"
    assert calls["anthropic:POST:/v1/messages"] == 7


def test_q3_refuses_when_any_q2_gate_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="required Q2 gates are missing"):
        run_dress_rehearsal(module_root=ROOT, output_root=tmp_path)
    assert not (tmp_path / "Q3").exists()


def test_q3_core_35_uses_production_flow_and_remains_nonofficial(tmp_path: Path) -> None:
    for series_id in SERIES_IDS:
        _seed_gate(tmp_path, "Q2", series_id)
    calls: Counter[str] = Counter()
    report = run_dress_rehearsal(
        module_root=ROOT,
        output_root=tmp_path,
        adapter_factory=_mock_factory(calls),
        run_id="Q3-CORE-35",
        sleep=lambda _: None,
    )
    assert report["passed"] is True
    assert report["completed_observations"] == 35
    assert report["official_longitudinal_data"] is False
    assert report["panels"]["closed"]["stats"]["completed"] == 28
    assert report["panels"]["native"]["stats"]["completed"] == 7
    for panel in ("closed", "native"):
        panel_root = tmp_path / "Q3/Q3-CORE-35" / panel
        assert (panel_root / "schedule.json").is_file()
        assert (panel_root / "qc/report.json").is_file()
        assert (panel_root / "wave-completion-certificate.json").is_file()
        canonical = (panel_root / "L1_canonical/observations.jsonl").read_text().splitlines()
        assert canonical
        assert all(json.loads(line)["OFFICIAL_LONGITUDINAL_DATA"] is False for line in canonical)

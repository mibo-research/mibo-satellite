from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from eibo.adapters import make_adapter
from eibo.adapters.base import ProviderResponse
from eibo.adapters.perplexity_w0 import PerplexityAgentW0Adapter, load_w0_agent_profile
from eibo.artifacts import load_battery
from eibo.errors import ValidationError
from eibo.qualification import FIRST_PARTY_HOSTS
from eibo.rehearsal4 import (
    DECISIONS,
    LIMITS,
    MODELS,
    PROPOSAL,
    PROVIDERS,
    Budget,
    authorization,
    first_party_factory,
    load_credentials,
    native_guard,
    retry_after,
    run_rehearsal,
)
from eibo.scheduling import create_schedule
from eibo.util import artifact_hash, canonical_json_bytes, load_json, sha256_file

ROOT = Path(__file__).parents[1]


class Clock:
    value = 1000.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


@pytest.fixture
def authorized(tmp_path, monkeypatch):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))
        return {"path": path.relative_to(tmp_path).as_posix(), "sha256": sha256_file(path)}

    assessment = write(tmp_path / "assessment.json", {"FOUR_PROVIDER_EVIDENCE_COMPLETE": True})
    owner = {"actor_type": "HUMAN", "name": "Test operator", "role": "Protocol Owner"}
    auth = {
        "proposal_id": PROPOSAL,
        "official_longitudinal_data": False,
        "plan_sha256": sha256_file(ROOT / "operations/prospective-four-provider/plan.draft.yaml"),
        "implementation_files_sha256": {
            p.relative_to(ROOT).as_posix(): sha256_file(p)
            for p in (ROOT / "src/eibo").rglob("*.py")
        },
        "M05_profile_sha256": load_w0_agent_profile(ROOT)["profile_sha256"],
        "assessment": assessment,
        "receipts": {},
    }
    for key, decision in DECISIONS.items():
        core = {
            "decision": decision,
            "official_longitudinal_data": False,
            "plan_snapshot_sha256": auth["plan_sha256"],
            "decided_by": owner,
            "W01_execution_authorized": False,
            "xai_execution_authorized": False,
            "limits": LIMITS,
            "observer_site_declaration": {"country": "JP"},
            "institutional_IRB_approval_claimed": False,
            "assessment_file_sha256": assessment["sha256"],
        }
        auth["receipts"][key] = write(
            tmp_path / "decisions" / f"{key}.json", {**core, "receipt_sha256": artifact_hash(core)}
        )
    path = tmp_path / "authorization.json"

    def persist():
        path.write_bytes(
            canonical_json_bytes({**auth, "authorization_sha256": artifact_hash(auth)})
        )

    persist()
    monkeypatch.setattr(
        "eibo.rehearsal4.assess_closeout", lambda *args: {"FOUR_PROVIDER_EVIDENCE_COMPLETE": True}
    )
    return tmp_path, path, auth, persist


def response_body(provider, model, mode):
    if provider in {"openai", "perplexity"}:
        return {
            "id": "response-1",
            "model": model,
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    if provider == "anthropic":
        return {
            "id": "message-1",
            "model": model,
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": (
                "max_tokens"
                if mode == "truncated"
                else "refusal"
                if mode == "refusal"
                else "end_turn"
            ),
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    return {
        "modelVersion": model,
        "responseId": "response-1",
        "candidates": [
            {
                "content": {"parts": [{"text": "OK"}]},
                "finishReason": "SAFETY" if mode == "block" else "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    }


def mock_factory(clock, calls, *, mode="normal"):
    def factory(provider):
        assert provider in PROVIDERS.values() and provider != "xai"
        sid = next(k for k, value in PROVIDERS.items() if value == provider)
        model = MODELS[sid]

        def handle(request):
            previous_posts = sum(c["method"] == "POST" for c in calls)
            body = json.loads(request.content) if request.content else None
            calls.append(
                {
                    "provider": provider,
                    "method": request.method,
                    "time": clock.now(),
                    "body": body,
                    "url": str(request.url),
                }
            )
            if request.method == "GET":
                if mode == "metadata_failure" and provider == "gemini":
                    return httpx.Response(200, json={"name": "models/not-the-model"})
                if mode == "metadata_deadline":
                    clock.value += 7300
                value = (
                    {"name": f"models/{model}"}
                    if provider == "gemini"
                    else {"id": model}
                    if request.url.path.endswith(model)
                    else {"data": [{"id": model}]}
                )
                return httpx.Response(200, json=value, headers={"Set-Cookie": "test-cookie"})
            count = sum(c["provider"] == provider and c["method"] == "POST" for c in calls)
            if provider == "gemini" and mode == "retry_once" and count == 1:
                return httpx.Response(
                    429,
                    json={"error": {"details": [{"retryDelay": "9s"}]}},
                    headers={"Retry-After": "130"},
                )
            if provider == "openai" and mode == "persistent_503":
                return httpx.Response(503, json={"error": "unavailable"})
            value = response_body(provider, "wrong-model" if mode == "identity" else model, mode)
            if mode == "unexpected_tool" and provider == "perplexity":
                value["output"].append({"type": "code_execution_call"})
            if mode == "secret" and previous_posts == 0:
                value = response_body(provider, model, mode)
                if "output" in value:
                    value["output"][0]["content"][0]["text"] = "test-private-credential-value"
                elif "content" in value:
                    value["content"][0]["text"] = "test-private-credential-value"
                else:
                    value["candidates"][0]["content"]["parts"][0]["text"] = (
                        "test-private-credential-value"
                    )
            if mode == "last_response_after_deadline" and previous_posts == 27:
                clock.value += 7300
            status = 429 if mode == "completed_429" else 200
            return httpx.Response(status, json=value, headers={"Set-Cookie": "test-cookie"})

        options = {
            "api_key": "unit-test-credential-value",
            "client": httpx.Client(transport=httpx.MockTransport(handle)),
            "base_url": f"https://{FIRST_PARTY_HOSTS[provider]}",
        }
        return (
            PerplexityAgentW0Adapter(**options)
            if provider == "perplexity"
            else make_adapter(provider, **options)
        )

    return factory


def execute(authorized, mode="normal", guard=None):
    output, path, _, _ = authorized
    clock, calls = Clock(), []
    result = run_rehearsal(
        root=ROOT,
        output=output,
        authorization_path=path,
        guard=guard or (lambda: None),
        factory=mock_factory(clock, calls, mode=mode),
        clock=clock.now,
        sleep=clock.sleep,
    )
    return result, calls, output / "rehearsals" / PROPOSAL


def test_complete_rehearsal_uses_production_flow_and_exact_prompts(authorized):
    report, calls, directory = execute(authorized)
    assert report["passed"] is True and report["observed"] == 28
    assert report["generation_requests"] == 28 and report["metadata_GET_requests"] == 6
    assert report["prior_records_unchanged"] is True
    assert (
        report["official_longitudinal_data"] is report["W0_READY"] is report["W01_READY"] is False
    )
    assert (directory / "scoped-completion-certificate.json").exists()
    posts = [c for c in calls if c["method"] == "POST"]
    assert all(
        set(c["provider"] for c in posts[i : i + 4]) == set(PROVIDERS.values())
        for i in range(0, 28, 4)
    )
    google = [c["time"] for c in posts if c["provider"] == "gemini"]
    assert all(b - a >= 65 for a, b in zip(google, google[1:], strict=False))
    assert all(
        c["url"] == "https://api.perplexity.ai/v1/agent"
        for c in posts
        if c["provider"] == "perplexity"
    )
    for c in posts:
        body = c["body"]
        turns = body.get("input") or body.get("messages") or body.get("contents")
        assert len(turns) == 1 and turns[0]["role"] == "user"
        prompt = (
            turns[0].get("content") if c["provider"] != "gemini" else turns[0]["parts"][0]["text"]
        )
        if isinstance(prompt, list):
            prompt = prompt[0]["text"]
        frozen = load_battery(ROOT / "battery/ebb-ja-v1.0.yaml")
        assert prompt in {item.prompt for item in frozen.items if item.item_id.endswith("-01")}
        assert not set(body).intersection(
            {
                "reasoning",
                "thinking",
                "temperature",
                "top_p",
                "top_k",
                "system",
                "developer",
                "instructions",
                "previous_response_id",
            }
        )
        assert "tools" not in body or c["provider"] == "perplexity"
    for panel in ("closed", "native"):
        assert (directory / panel / "wave-completion-certificate.json").exists()
        canonical = (directory / panel / "L1_canonical/observations.jsonl").read_text(
            encoding="utf-8"
        )
        assert all(
            json.loads(line)["OFFICIAL_LONGITUDINAL_DATA"] is False
            for line in canonical.splitlines()
        )
        for path in (directory / panel / "L0_raw").rglob("*.response.json"):
            assert not set(load_json(path)["headers"]).intersection({"set-cookie", "authorization"})
    assert not (authorized[0] / "gates").exists()
    assert not (authorized[0] / "Q3").exists()
    with pytest.raises(FileExistsError):
        execute(authorized)


def test_retry_once_respects_retry_after_and_preserves_both_attempts(authorized):
    report, calls, directory = execute(authorized, "retry_once")
    assert report["passed"] is True and report["generation_requests"] == 29
    google = [c for c in calls if c["method"] == "POST" and c["provider"] == "gemini"]
    assert google[1]["time"] - google[0]["time"] >= 130
    assert sum(r["attempts"] == 2 for r in report["outcomes"]) == 1
    assert len(list((directory / "closed/L0_raw").rglob("*.response.body"))) == 22


@pytest.mark.parametrize("mode", ["truncated", "block", "refusal", "completed_429"])
def test_completed_scientific_outcomes_are_never_retried(authorized, mode):
    report, _, _ = execute(authorized, mode)
    assert report["passed"] is True and report["generation_requests"] == 28
    assert all(r["attempts"] == 1 for r in report["outcomes"])


def test_technical_retry_count_is_bounded_and_missing_is_reported(authorized):
    report, calls, directory = execute(authorized, "persistent_503")
    assert report["passed"] is False and report["observed"] == 21
    assert report["generation_requests"] == 35
    assert sum(c["method"] == "POST" and c["provider"] == "openai" for c in calls) == 14
    assert not (directory / "scoped-completion-certificate.json").exists()


@pytest.mark.parametrize("mode", ["metadata_failure", "metadata_deadline"])
def test_metadata_or_deadline_failure_sends_no_generation(authorized, mode):
    report, calls, directory = execute(authorized, mode)
    assert not report["passed"] and report["generation_requests"] == 0
    assert not any(c["method"] == "POST" for c in calls)
    assert not (directory / "closed/model-lock.json").exists()


@pytest.mark.parametrize("mode", ["identity", "unexpected_tool"])
def test_identity_or_native_configuration_mismatch_stops_without_replacement(authorized, mode):
    report, _, directory = execute(authorized, mode)
    assert report["passed"] is False and report["errors"]
    assert report["generation_requests"] < 28
    assert all(r["attempts"] == 1 for r in report["outcomes"])
    assert list(directory.rglob("*.response.body"))


def test_response_received_after_deadline_is_preserved(authorized):
    report, _, _ = execute(authorized, "last_response_after_deadline")
    assert report["passed"] is True and report["generation_requests"] == 28


def test_guard_is_required_before_any_adapter(authorized):
    def guard():
        raise ValidationError("AC disconnected")

    with pytest.raises(ValidationError, match="AC disconnected"):
        execute(authorized, guard=guard)
    assert not (authorized[0] / "rehearsals").exists()


def test_secret_response_is_not_persisted_or_retried(authorized, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-credential-value")
    report, _, directory = execute(authorized, "secret")
    assert not report["passed"] and report["generation_requests"] == 1
    for path in directory.rglob("*"):
        if path.is_file():
            assert b"test-private-credential-value" not in path.read_bytes()


@pytest.mark.parametrize("key", list(DECISIONS))
def test_missing_human_decision_refuses_before_adapter_or_claim(authorized, key):
    output, path, auth, persist = authorized
    del auth["receipts"][key]
    persist()
    with pytest.raises(ValidationError, match="decisions are incomplete"):
        execute(authorized)
    assert not (output / "rehearsals").exists()


def test_approval_cannot_be_silently_edited(authorized):
    output, path, auth, _ = authorized
    receipt = output / auth["receipts"]["owner"]["path"]
    receipt.write_text("changed", encoding="utf-8")
    with pytest.raises(ValidationError):
        authorization(ROOT, output, path)


def test_changed_implementation_or_official_scope_is_rejected(authorized):
    output, path, auth, persist = authorized
    auth["implementation_files_sha256"]["src/eibo/rehearsal4.py"] = "0" * 64
    persist()
    with pytest.raises(ValidationError, match="implementation changed"):
        authorization(ROOT, output, path)
    auth["implementation_files_sha256"]["src/eibo/rehearsal4.py"] = sha256_file(
        ROOT / "src/eibo/rehearsal4.py"
    )
    auth["official_longitudinal_data"] = True
    persist()
    with pytest.raises(ValidationError, match="non-official"):
        authorization(ROOT, output, path)


def test_model_factory_refuses_xai():
    with pytest.raises(ValidationError, match="scope"):
        first_party_factory("xai")


def test_order_only_schedule_cannot_be_used_for_official_or_multiple_replications(wave_factory):
    manifest, battery, lock, _ = wave_factory(replications=2)
    for value in (manifest, replace(manifest, official=True, replications=1)):
        with pytest.raises(ValidationError, match="order-only"):
            create_schedule(value, battery, lock, order_only=True)


def test_retry_after_handles_delta_date_and_provider_metadata():
    body = {"error": {"details": [{"retryDelay": "90s"}]}}
    response = ProviderResponse(429, {"Retry-After": "130"}, b"", body)
    assert retry_after(response, 0) == 130
    response = ProviderResponse(503, {"Retry-After": "Thu, 01 Jan 1970 00:02:00 GMT"}, b"", {})
    assert retry_after(response, 30) == 90
    assert retry_after(ProviderResponse(503, {}, b"", {"error": "unavailable"}), 0) == 0


def test_budget_exhaustion_prevents_send(tmp_path):
    clock = Clock()
    budget = Budget(tmp_path, lambda: None, clock.now, clock.sleep, None)
    adapter = first_party_factory("openai")
    try:
        from eibo.live_qualification import _prepare_request

        request, _ = _prepare_request(adapter, series_id="M01", model=MODELS["M01"], prompt="test")
        budget.post = 56
        with pytest.raises(ValidationError, match="budget exhausted"):
            budget.send(adapter, request)
    finally:
        adapter.client.close()


def test_guard_is_rechecked_while_waiting(tmp_path):
    clock = Clock()

    def guard():
        if clock.now() >= 1005:
            raise ValidationError("AC disconnected during wait")

    budget = Budget(tmp_path, guard, clock.now, clock.sleep, None)
    with pytest.raises(ValidationError, match="disconnected during wait"):
        budget.wait(65)
    assert clock.now() == 1005


def test_native_guard_checks_fresh_state_pid_and_actual_AC(tmp_path, monkeypatch):
    import ctypes

    from eibo import rehearsal4

    state = tmp_path / "guard.json"
    value = {
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "status": "ACTIVE",
        "system_sleep_request_active": True,
        "ac_connected": True,
        "session": "test-session",
        "pid": 1234,
    }
    state.write_bytes(canonical_json_bytes(value))
    monkeypatch.setattr(rehearsal4, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(rehearsal4.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))

    def connected(pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ubyte))[0] = 1
        return 1

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(kernel32=SimpleNamespace(GetSystemPowerStatus=connected)),
        raising=False,
    )
    native_guard(state)
    value["updated_at_utc"] = (datetime.now(UTC) - timedelta(seconds=25)).isoformat()
    state.write_bytes(canonical_json_bytes(value))
    with pytest.raises(ValidationError, match="not active"):
        native_guard(state)


def test_credentials_loader_reads_only_four_names_and_ignored_file(tmp_path, monkeypatch):
    import sys

    from eibo import rehearsal4

    root = tmp_path / "eibo"
    root.mkdir()
    (tmp_path / ".env").write_text("OPENAI_API_KEY=unit-test-local-key\n", encoding="utf-8")
    names = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY")
    for name in names:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("EIBO_W0_EVIDENCE_ROOT", "")
    queried = []

    def query(key, name):
        queried.append(name)
        if name == "OPENAI_API_KEY":
            raise FileNotFoundError
        return ("unit-test-user-key", 1)

    monkeypatch.setitem(
        sys.modules,
        "winreg",
        SimpleNamespace(
            HKEY_CURRENT_USER=1, OpenKey=lambda *a: nullcontext(None), QueryValueEx=query
        ),
    )
    monkeypatch.setattr(rehearsal4.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    load_credentials(root, tmp_path)
    assert queried == list(names) and "XAI_API_KEY" not in queried
    assert all(bool(rehearsal4.os.getenv(name)) for name in names)


def test_cli_checks_guard_and_authorization_before_credentials(authorized, monkeypatch, capsys):
    from eibo import rehearsal4

    output, auth_path, _, _ = authorized
    events = []
    monkeypatch.setattr(rehearsal4, "native_guard", lambda p: events.append("guard"))
    original = rehearsal4.authorization

    def authorize(*args):
        events.append("authorization")
        return original(*args)

    monkeypatch.setattr(rehearsal4, "authorization", authorize)
    monkeypatch.setattr(rehearsal4, "load_credentials", lambda *a: events.append("credentials"))

    def run(**kwargs):
        events.append("run")
        return {"passed": True, "observed": 28, "generation_requests": 28}

    monkeypatch.setattr(rehearsal4, "run_rehearsal", run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "rehearsal4",
            "--root",
            str(ROOT),
            "--output-root",
            str(output),
            "--authorization",
            str(auth_path),
            "--guard-state",
            str(output / "guard.json"),
        ],
    )
    rehearsal4.main()
    assert events == ["guard", "authorization", "credentials", "run"]
    assert '"observed":28' in capsys.readouterr().out

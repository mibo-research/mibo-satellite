from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import yaml

from eibo.adapters import Environment, make_adapter
from eibo.adapters.perplexity import PerplexityAdapter
from eibo.adapters.perplexity_w0 import (
    MODEL_ID,
    PROFILE_PATH,
    PerplexityAgentW0Adapter,
    load_w0_agent_profile,
)
from eibo.errors import ProviderError, ValidationError
from eibo.live_qualification import (
    _current_gate,
    _write_gate,
    qualification_status_report,
    run_provider_qualification_set,
    run_smoke_qualification,
)
from eibo.operational import w0_pre_live_report
from eibo.util import canonical_json_bytes, sha256_bytes, write_immutable

ROOT = Path(__file__).parents[1]


def native(adapter: PerplexityAgentW0Adapter):
    return adapter.prepare(
        model=MODEL_ID, prompt="W0 diagnostic", environment=Environment.NATIVE,
        sampling={"max_output_tokens": 8192},
    )


def test_w0_migration_is_explicit_and_legacy_adapter_is_unchanged() -> None:
    adapter = PerplexityAgentW0Adapter()
    request = native(adapter)
    assert request.url == "https://api.perplexity.ai/v1/agent"
    assert request.body == {
        "model": "perplexity/sonar",
        "input": [{"type": "message", "role": "user", "content": "W0 diagnostic"}],
        "max_output_tokens": 8192, "stream": False, "tools": [{"type": "web_search"}],
    }
    audit = adapter.qualification_audit(request)
    assert audit["serialized_request_sha256"] == sha256_bytes(request.body_bytes)
    assert audit["legacy_comparability"] == "NOT_ESTABLISHED"
    assert audit["official_longitudinal_data"] is False
    assert audit["tools_absent"] is False
    legacy = make_adapter("perplexity")
    assert type(legacy) is PerplexityAdapter
    assert legacy.prepare(model="sonar", prompt="x", environment=Environment.NATIVE).url == (
        "https://api.perplexity.ai/v1/sonar"
    )


def test_no_search_diagnostic_omits_tools_effort_and_obsolete_disable_search() -> None:
    adapter = PerplexityAgentW0Adapter()
    request = adapter.prepare_closed_diagnostic(model=MODEL_ID, prompt="x")
    assert set(request.body) == {"model", "input", "max_output_tokens", "stream"}
    audit = adapter.qualification_audit(request, diagnostic=True)
    assert audit["tools_absent"] is True
    assert audit["no_search_mapping"] == "OMIT_TOOLS_AND_EFFORT"
    assert audit["legacy_disable_search_field_sent"] is False
    with pytest.raises(ValidationError, match="cannot guarantee CLOSED"):
        adapter.prepare(model=MODEL_ID, prompt="x", environment=Environment.CLOSED)


@pytest.mark.parametrize("key,value", [
    ("models", ["openai/other"]), ("effort", "fast"), ("instructions", "override"),
    ("temperature", 0), ("previous_response_id", "prior"), ("profile", "preset"),
    ("max_tokens", 8192), ("stream", True), ("model", "sonar"),
    ("max_output_tokens", 4096), ("tools", [{"type": "sandbox"}]),
    ("input", [{"role": "user", "content": [{"type": "input_file", "file_id": "file"}]}]),
])
def test_w0_request_audit_rejects_fallbacks_presets_state_and_wrong_mapping(key, value) -> None:
    adapter = PerplexityAgentW0Adapter()
    request = native(adapter)
    with pytest.raises(ValidationError, match="explicit Agent API profile"):
        adapter.qualification_audit(replace(request, body={**request.body, key: value}))


def test_first_party_and_redirect_guards_precede_transport() -> None:
    with pytest.raises(ValidationError, match="first-party"):
        PerplexityAgentW0Adapter(base_url="https://router.example")
    with pytest.raises(ValidationError, match="without redirects"):
        PerplexityAgentW0Adapter(client=httpx.Client(follow_redirects=True))
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://router.example"}, json={})

    adapter = PerplexityAgentW0Adapter(
        api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ProviderError, match="redirect refused"):
        adapter.send(native(adapter))
    assert calls == ["https://api.perplexity.ai/v1/agent"]


def test_response_trace_keeps_refusal_truncation_identity_and_cost_metadata() -> None:
    adapter = PerplexityAgentW0Adapter()
    body = {
        "id": "test", "model": MODEL_ID, "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}],
        "usage": {"input_tokens": 1, "output_tokens": 8192, "cost": {"total_cost": 1}},
    }
    response = adapter.normalize(body)
    assert response.text == "No"
    assert response.finish_reason == "max_output_tokens"
    assert response.safety["refusal"] == ["No"]
    assert response.usage == body["usage"]
    assert adapter.qualification_response_errors(body, diagnostic=True) == []
    assert adapter.qualification_response_errors({**body, "model": "openai/other"})
    assert adapter.qualification_response_errors({**body, "effort": "fast"})
    assert adapter.qualification_response_errors({**body, "output": [{"type": "search_results"}]},
                                                diagnostic=True)
    assert adapter.qualification_response_errors({**body, "tools": [{"type": "web_search"}]},
                                                diagnostic=True)
    assert adapter.qualification_response_errors({
        **body, "usage": {"tool_calls_details": {"web_search": {"invocation": 0}}},
    }, diagnostic=True) == []


@pytest.mark.parametrize("change", [
    {"id": None}, {"usage": None}, {"output": None}, {"status": "queued"},
    {"status": "failed", "error": {"code": "test"}}, {"profile": {"id": "other"}},
    {"usage": {"cost": {"tool_calls_cost": 0.1}}},
    {"output": [{"type": "message", "content": [{
        "type": "output_text", "text": "A citation",
        "annotations": [{"type": "url_citation", "url": "https://example.org"}],
    }]}]},
])
def test_incomplete_metadata_or_search_annotations_cannot_pass_diagnostic(change) -> None:
    adapter = PerplexityAgentW0Adapter()
    body = {"id": "test", "model": MODEL_ID, "status": "completed", "usage": {}, "output": []}
    assert adapter.qualification_response_errors({**body, **change}, diagnostic=True)


def test_m05_requires_a_valid_separate_w0_profile_even_with_credential(tmp_path: Path) -> None:
    report = w0_pre_live_report(module_root=tmp_path, series_ids=["M05"], environment={
        "PERPLEXITY_API_KEY": "test-key", "EIBO_W0_EVIDENCE_ROOT": "test-root",
    })
    assert any("M05 W0 Agent API profile unavailable" in r
               for r in report["W0_Q1_EXECUTABLE_reasons"])
    path = tmp_path / PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = yaml.safe_load((ROOT / PROFILE_PATH).read_text(encoding="utf-8"))
    profile["w01_authorized"] = True
    path.write_text(yaml.safe_dump(profile), encoding="utf-8")
    with pytest.raises(ValidationError, match="invalid W0"):
        load_w0_agent_profile(tmp_path)


def test_old_model_or_profile_gate_is_never_reused_or_overwritten(tmp_path: Path) -> None:
    result_path = tmp_path / "old-result.json"
    write_immutable(result_path, canonical_json_bytes({"preserved": "old response"}))
    before = result_path.read_bytes()
    _write_gate(tmp_path, stage="Q1", series_id="M05", result={
        "requested_model": "sonar", "returned_model": "sonar",
    }, result_path=result_path)
    with pytest.raises(ValidationError, match="model/profile changed"):
        _current_gate(tmp_path, "Q1", "M05", {
            "requested_model": MODEL_ID,
            "qualification_profile_sha256": load_w0_agent_profile(ROOT)["profile_sha256"],
        })
    assert result_path.read_bytes() == before


def test_invalid_m05_profile_cannot_block_an_explicitly_selected_other_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_profile(module_root):
        raise ValidationError("invalid W0 profile")

    monkeypatch.setattr("eibo.live_qualification.load_w0_agent_profile", invalid_profile)
    report = qualification_status_report(module_root=ROOT, series_ids=["M01"])
    assert report["selected_series"] == ["M01"]
    assert report["w0_model_resolutions"]["M01"]["requested_model"] == "gpt-5.6-sol"
    with pytest.raises(ValidationError, match="invalid W0 profile"):
        qualification_status_report(module_root=ROOT, series_ids=["M05"])


def test_agent_request_evidence_is_independently_hashed_and_separate_from_legacy() -> None:
    from eibo.qualification import QUALIFICATION_PROMPT

    value = json.loads((ROOT / "waves/W0/evidence/perplexity/request-shapes.agent-w0-v1.json")
                       .read_text(encoding="utf-8"))
    adapter = PerplexityAgentW0Adapter()
    assert value["profile_sha256"] == load_w0_agent_profile(ROOT)["profile_sha256"]
    for name, diagnostic in (("native", False), ("no_search_diagnostic", True)):
        request = (
            adapter.prepare_closed_diagnostic(model=MODEL_ID, prompt=QUALIFICATION_PROMPT)
            if diagnostic else adapter.prepare(model=MODEL_ID, prompt=QUALIFICATION_PROMPT,
                environment=Environment.NATIVE, sampling={"max_output_tokens": 8192})
        )
        assert value[name]["serialized_body_utf8"].encode() == request.body_bytes
        assert value[name]["audit"]["serialized_request_sha256"] == sha256_bytes(request.body_bytes)
        assert value[name]["live_verified"] is False


@pytest.mark.parametrize("behavior", ["identity_mismatch", "diagnostic_search", "refusal_cap"])
def test_live_migration_flow_preserves_scientific_responses_and_never_retries(
    behavior: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-only-key")
    monkeypatch.setenv("EIBO_W0_EVIDENCE_ROOT", "test-evidence")
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": MODEL_ID}]})
        assert request.url.path == "/v1/agent"
        payload = json.loads(request.content)
        posts.append(payload)
        body = {
            "model": MODEL_ID, "id": "test-response", "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        if behavior == "identity_mismatch":
            body["model"] = "openai/other"
        if behavior == "diagnostic_search" and "tools" not in payload:
            body["output"].append({"type": "search_results", "results": []})
        if behavior == "refusal_cap":
            body["status"] = "incomplete"
            body["incomplete_details"] = {"reason": "max_output_tokens"}
            body["output"][0]["content"] = [{"type": "refusal", "refusal": "No"}]
        return httpx.Response(200, json=body)

    def factory(provider):
        assert provider == "perplexity"
        return PerplexityAgentW0Adapter(
            api_key="test-only-key", client=httpx.Client(transport=httpx.MockTransport(handler))
        )

    q1 = run_smoke_qualification(
        module_root=ROOT, output_root=tmp_path, series_ids=["M05"], adapter_factory=factory,
        run_id="agent-q1",
    )
    assert len(posts) == 1
    if behavior == "identity_mismatch":
        assert q1["passed"] is False
        raw_path = tmp_path / "Q1/agent-q1/M05/ordinary-smoke.response.body"
        before = raw_path.read_bytes()
        repeated = run_smoke_qualification(
            module_root=ROOT, output_root=tmp_path, series_ids=["M05"], adapter_factory=factory,
            run_id="agent-q1-again",
        )
        assert repeated["passed"] is False
        assert len(posts) == 1
        assert raw_path.read_bytes() == before
        return
    assert q1["passed"] is True
    q2 = run_provider_qualification_set(
        module_root=ROOT, output_root=tmp_path, series_ids=["M05"], adapter_factory=factory,
        run_id="agent-q2",
    )
    assert len(posts) == 15
    if behavior == "diagnostic_search":
        assert q2["passed"] is False
        assert any("unexpected tool or search" in r for r in q2["results"]["M05"]["failures"])
    else:
        assert q2["passed"] is True
        assert q2["results"]["M05"]["refusals_observed"] == 7
        assert q2["results"]["M05"]["truncation_or_output_cap_stops_observed"] == 7
    repeated = run_provider_qualification_set(
        module_root=ROOT, output_root=tmp_path, series_ids=["M05"], adapter_factory=factory,
        run_id="agent-q2-again",
    )
    assert len(posts) == 15
    assert repeated["passed"] is (behavior == "refusal_cap")

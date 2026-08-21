from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from .adapters import Environment, ProviderAdapter, make_adapter
from .adapters.perplexity import PerplexityAdapter
from .artifacts import load_battery, load_manifest, load_registry, load_yaml
from .certificate import create_certificate
from .errors import ProviderError, TechnicalRetryableError, ValidationError
from .models import load_model_lock
from .operational import w0_pre_live_report
from .qc import run_qc
from .qualification import (
    FIRST_PARTY_HOSTS,
    QUALIFICATION_PROMPT,
    assert_first_party,
    audit_qualification_shape,
)
from .runner import run_wave
from .scheduling import create_schedule
from .util import (
    artifact_hash,
    canonical_json_bytes,
    ensure_no_secrets,
    load_json,
    sha256_bytes,
    sha256_file,
    utc_now,
    write_immutable,
)

SERIES_IDS = ("M01", "M02", "M03", "M04", "M05")
OUTPUT_CAP_PARAMETERS = {
    "M01": "max_output_tokens",
    "M02": "max_tokens",
    "M03": "maxOutputTokens",
    "M04": "max_output_tokens",
    "M05": "max_tokens",
}
SAMPLING = {
    "M01": {"max_output_tokens": 8192},
    "M02": {"max_tokens": 8192},
    "M03": {"maxOutputTokens": 8192},
    "M04": {"max_output_tokens": 8192},
    "M05": {"max_tokens": 8192},
}
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "x-goog-api-key",
    "cookie",
    "set-cookie",
}

AdapterFactory = Callable[[str], ProviderAdapter]


def default_module_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_output_root(module_root: Path) -> Path:
    return module_root / "waves" / "W0" / "live-qualification"


def _first_party_factory(provider: str) -> ProviderAdapter:
    return make_adapter(provider, base_url=f"https://{FIRST_PARTY_HOSTS[provider]}")


def _run_id(stage: str) -> str:
    stamp = utc_now().replace("-", "").replace(":", "").replace(".", "")
    return f"W0-{stage}-{stamp}-{uuid.uuid4().hex[:8]}"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    write_immutable(path, canonical_json_bytes(value) + b"\n")


def _public_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in SENSITIVE_HEADER_NAMES
    }


def _load_plan(module_root: Path) -> tuple[dict[str, Any], Any]:
    path = module_root / "waves" / "W0" / "live-qualification-plan.yaml"
    plan = load_yaml(path)
    battery = load_battery(module_root / "battery" / "ebb-ja-v1.0.yaml")
    models = plan.get("models")
    item_ids = plan.get("qualification_item_ids")
    rehearsal = plan.get("core_35_rehearsal") or {}
    if plan.get("official_longitudinal_data") is not False:
        raise ValidationError("W0 live qualification must remain non-official")
    if not isinstance(models, dict) or tuple(models) != SERIES_IDS:
        raise ValidationError("live qualification plan must define M01-M05 in order")
    m02 = models.get("M02") or {}
    if (
        m02.get("permanent_mibo_lineage_id") != "MIBO-SL-002"
        or m02.get("permanent_lineage_label") != "Claude"
        or m02.get("requested_model") != "claude-opus-5"
    ):
        raise ValidationError(
            "W0 M02 must map MIBO-SL-002 Claude to exact candidate claude-opus-5"
        )
    registry = load_registry(module_root / "registry" / "model-series.yaml")
    registry_m02 = next(
        (row for row in registry["series"] if row.get("series_id") == "M02"), None
    )
    if not registry_m02 or (
        registry_m02.get("permanent_mibo_lineage_id") != "MIBO-SL-002"
        or registry_m02.get("permanent_mibo_lineage_label") != "Claude"
        or "Opus Series" in str(registry_m02.get("label"))
    ):
        raise ValidationError("permanent M02 registry lineage must remain MIBO-SL-002 Claude")
    if not isinstance(item_ids, list) or len(item_ids) != 7:
        raise ValidationError("W0-Q2 must contain exactly seven preselected items")
    if [value.split("-", 1)[0] for value in item_ids] != [f"E{i}" for i in range(1, 8)]:
        raise ValidationError("W0-Q2 item set must cover E1-E7 exactly once")
    known = {item.item_id for item in battery.items}
    if len(set(item_ids)) != 7 or not set(item_ids).issubset(known):
        raise ValidationError("W0-Q2 item IDs are duplicated or absent from EBB-JA v1.0")
    if rehearsal.get("expected_observations") != 35:
        raise ValidationError("Core-35 rehearsal must contain exactly 35 observations")
    if plan.get("governance", {}).get("agent_approval_permitted") is not False:
        raise ValidationError("agents must not approve W0 governance")
    return plan, battery


def _selected_series(plan: dict[str, Any], series_ids: Iterable[str] | None) -> list[str]:
    selected = list(series_ids or SERIES_IDS)
    if not selected or len(selected) != len(set(selected)):
        raise ValidationError("qualification series selection is empty or duplicated")
    unknown = sorted(set(selected) - set(plan["models"]))
    if unknown:
        raise ValidationError(f"unknown qualification series: {unknown}")
    return selected


def _prepare_request(
    adapter: ProviderAdapter,
    *,
    series_id: str,
    model: str,
    prompt: str,
    diagnostic: bool = False,
) -> tuple[Any, dict[str, Any]]:
    row = {"M01": Environment.CLOSED, "M02": Environment.CLOSED,
           "M03": Environment.CLOSED, "M04": Environment.CLOSED,
           "M05": Environment.NATIVE}
    if diagnostic:
        if series_id != "M05" or not isinstance(adapter, PerplexityAdapter):
            raise ValidationError("only M05 supports the W0 CLOSED diagnostic")
        request = adapter.prepare_closed_diagnostic(model=model, prompt=prompt)
        environment = Environment.CLOSED
    else:
        environment = row[series_id]
        request = adapter.prepare(
            model=model,
            prompt=prompt,
            environment=environment,
            sampling=SAMPLING[series_id],
        )
    audit = audit_qualification_shape(
        request,
        provider=adapter.provider,
        environment=environment,
        output_cap_parameter=OUTPUT_CAP_PARAMETERS[series_id],
        allow_disable_search=diagnostic,
    )
    return request, audit


def _capture_request(directory: Path, label: str, request: Any) -> dict[str, Any]:
    body = request.body_bytes
    ensure_no_secrets(body, context=f"{label} request body")
    body_path = directory / f"{label}.request.body"
    write_immutable(body_path, body)
    core = {
        "captured_at": utc_now(),
        "method": request.method,
        "url": request.url,
        "headers": _public_headers(request.headers),
        "body_sha256": sha256_bytes(body),
        "body_length": len(body),
        "authorization_header_stored": False,
    }
    record = {**core, "request_record_sha256": artifact_hash(core)}
    _write_json(directory / f"{label}.request.json", record)
    return record


def _capture_response(directory: Path, label: str, response: Any) -> dict[str, Any]:
    ensure_no_secrets(response.body_bytes, context=f"{label} response body")
    body_path = directory / f"{label}.response.body"
    write_immutable(body_path, response.body_bytes)
    core = {
        "captured_at": utc_now(),
        "status_code": response.status_code,
        "headers": _public_headers(response.headers),
        "body_sha256": sha256_bytes(response.body_bytes),
        "body_length": len(response.body_bytes),
    }
    record = {**core, "response_record_sha256": artifact_hash(core)}
    _write_json(directory / f"{label}.response.json", record)
    return record


def _send_captured(
    adapter: ProviderAdapter, directory: Path, label: str, request: Any
) -> tuple[Any | None, str | None]:
    _capture_request(directory, label, request)
    try:
        response = adapter.send(request)
    except (TechnicalRetryableError, ProviderError) as exc:
        captured = getattr(exc, "provider_response", None)
        if captured is not None:
            _capture_response(directory, label, captured)
        return None, f"{type(exc).__name__}: {exc}"
    _capture_response(directory, label, response)
    return response, None


def _identity_match(requested: str, returned: str | None) -> bool:
    if not returned:
        return False
    return requested.removeprefix("models/") == returned.removeprefix("models/")


def _metadata_identity_fields(bodies: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {"id", "name", "model", "version", "fingerprint", "aliases", "displayName"}
    collected: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            selected = {key: value[key] for key in allowed.intersection(value)}
            if selected:
                collected.append(selected)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for body in bodies:
        visit(body)
    return collected


def _gate_path(output_root: Path, stage: str, series_id: str) -> Path:
    return output_root / "gates" / f"{stage}-{series_id}.json"


def _write_gate(
    output_root: Path,
    *,
    stage: str,
    series_id: str,
    result: dict[str, Any],
    result_path: Path,
) -> dict[str, Any]:
    core = {
        "schema_version": "1.0",
        "stage": stage,
        "series_id": series_id,
        "passed": True,
        "official_longitudinal_data": False,
        "qualified_at": utc_now(),
        "requested_model": result["requested_model"],
        "returned_model": result.get("returned_model"),
        "result_path": str(result_path.resolve()),
        "result_sha256": sha256_file(result_path),
    }
    gate = {**core, "gate_sha256": artifact_hash(core)}
    _write_json(_gate_path(output_root, stage, series_id), gate)
    return gate


def _read_gate(output_root: Path, stage: str, series_id: str) -> dict[str, Any] | None:
    path = _gate_path(output_root, stage, series_id)
    if not path.is_file():
        return None
    gate = load_json(path)
    claimed = gate.pop("gate_sha256", None)
    if claimed != artifact_hash(gate):
        raise ValidationError(f"qualification gate hash mismatch: {path}")
    result_path = Path(str(gate["result_path"]))
    if not result_path.is_file() or sha256_file(result_path) != gate["result_sha256"]:
        raise ValidationError(f"qualification gate evidence changed: {path}")
    gate["gate_sha256"] = claimed
    return gate


def _rehearsal_gate_passed(output_root: Path) -> bool:
    path = output_root / "gates" / "Q3-CORE-35.json"
    if not path.is_file():
        return False
    gate = load_json(path)
    claimed = gate.pop("gate_sha256", None)
    if claimed != artifact_hash(gate):
        raise ValidationError(f"qualification gate hash mismatch: {path}")
    result_path = Path(str(gate["result_path"]))
    if not result_path.is_file() or sha256_file(result_path) != gate["result_sha256"]:
        raise ValidationError(f"qualification gate evidence changed: {path}")
    return gate.get("passed") is True and gate.get("official_longitudinal_data") is False


def run_smoke_qualification(
    *,
    module_root: Path | None = None,
    output_root: Path | None = None,
    series_ids: Iterable[str] | None = None,
    adapter_factory: AdapterFactory = _first_party_factory,
    run_id: str | None = None,
) -> dict[str, Any]:
    module_root = (module_root or default_module_root()).resolve()
    output_root = (output_root or default_output_root(module_root)).resolve()
    plan, _ = _load_plan(module_root)
    selected = _selected_series(plan, series_ids)
    identifier = run_id or _run_id("Q1")
    run_dir = output_root / "Q1" / identifier
    pre_live = w0_pre_live_report(module_root=module_root, series_ids=selected)
    if not pre_live["W0_Q1_EXECUTABLE"]:
        results = {
            series_id: {
                "status": "BLOCKED_PRE_LIVE_OPERATIONAL_GATES",
                "passed": False,
                "requested_model": plan["models"][series_id].get("requested_model"),
                "ordinary_requests_attempted": 0,
                "substitution_attempted": False,
                "pre_live_report_sha256": pre_live["report_sha256"],
            }
            for series_id in selected
        }
        core = {
            "schema_version": "1.0",
            "stage": "W0-Q1",
            "run_id": identifier,
            "official_longitudinal_data": False,
            "passed": False,
            "pre_live": pre_live,
            "results": results,
        }
        report = {**core, "report_sha256": artifact_hash(core)}
        _write_json(run_dir / "report.json", report)
        return report
    results: dict[str, Any] = {}
    for series_id in selected:
        existing = _read_gate(output_root, "Q1", series_id)
        if existing:
            results[series_id] = {"status": "ALREADY_PASSED", "gate": existing}
            continue
        row = plan["models"][series_id]
        model = row.get("requested_model")
        provider = str(row["provider"])
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "stage": "W0-Q1",
            "series_id": series_id,
            "provider": provider,
            "requested_model": model,
            "official_longitudinal_data": False,
            "ordinary_requests_attempted": 0,
            "substitution_attempted": False,
            "pre_live_report_sha256": pre_live["report_sha256"],
        }
        if not isinstance(model, str) or not model:
            result.update(status="BLOCKED_EXACT_MODEL_UNRESOLVED", passed=False)
        else:
            try:
                adapter = adapter_factory(provider)
            except Exception as exc:
                result.update(
                    status="FAILED_CLOSED",
                    passed=False,
                    error=f"adapter initialization: {type(exc).__name__}: {exc}",
                )
            else:
                if not adapter.api_key:
                    result.update(status="BLOCKED_CREDENTIAL_MISSING", passed=False)
                else:
                    provider_dir = run_dir / series_id
                    try:
                        metadata_bodies: list[dict[str, Any]] = []
                        metadata_records: list[dict[str, Any]] = []
                        for number, request in enumerate(
                            adapter.model_metadata_requests(model), start=1
                        ):
                            assert_first_party(request, provider)
                            response, error = _send_captured(
                                adapter, provider_dir, f"metadata-{number:02d}", request
                            )
                            if error or response is None or response.body is None:
                                raise ProviderError(error or "metadata response was not JSON")
                            metadata_bodies.append(response.body)
                            metadata_records.append(
                                {
                                    "body_sha256": sha256_bytes(response.body_bytes),
                                    "status_code": response.status_code,
                                }
                            )
                        metadata_match = adapter.metadata_identifies_model(
                            model, tuple(metadata_bodies)
                        )
                        if not metadata_match:
                            raise ValidationError(
                                f"{provider} metadata did not identify exact requested "
                                f"model {model}"
                            )
                        request, audit = _prepare_request(
                            adapter,
                            series_id=series_id,
                            model=model,
                            prompt=str(plan.get("smoke_prompt") or QUALIFICATION_PROMPT),
                        )
                        result["ordinary_requests_attempted"] = 1
                        response, error = _send_captured(
                            adapter, provider_dir, "ordinary-smoke", request
                        )
                        if error or response is None or response.body is None:
                            raise ProviderError(error or "ordinary response was not JSON")
                        normalized = adapter.normalize(response.body)
                        identity_match = _identity_match(model, normalized.returned_model)
                        response_flags = _response_flags(normalized)
                        result.update(
                            status="PASSED" if identity_match else "FAILED_RETURNED_IDENTITY",
                            passed=identity_match,
                            returned_model=normalized.returned_model,
                            returned_identity_matches_requested=identity_match,
                            response_id=normalized.response_id,
                            finish_reason=normalized.finish_reason,
                            usage=normalized.usage,
                            safety=normalized.safety,
                            stop_reason_is_max_tokens=response_flags[
                                "stop_reason_is_max_tokens"
                            ],
                            request_shape=audit,
                            metadata_complete=True,
                            metadata_records=metadata_records,
                            metadata_identity_fields=_metadata_identity_fields(metadata_bodies),
                            raw_preservation=True,
                            secret_redaction_validated=True,
                        )
                        if series_id == "M02":
                            result["anthropic_observation_metadata"] = {
                                "stop_reason": normalized.finish_reason,
                                "stop_reason_is_max_tokens": response_flags[
                                    "stop_reason_is_max_tokens"
                                ],
                                "thinking": _anthropic_thinking_metadata(response.body),
                            }
                    except Exception as exc:
                        result.update(
                            status="FAILED_CLOSED",
                            passed=False,
                            error=f"{type(exc).__name__}: {exc}",
                        )
        result_path = run_dir / series_id / "result.json"
        _write_json(result_path, result)
        if result.get("passed") is True:
            _write_gate(
                output_root,
                stage="Q1",
                series_id=series_id,
                result=result,
                result_path=result_path,
            )
        results[series_id] = result
    core = {
        "schema_version": "1.0",
        "stage": "W0-Q1",
        "run_id": identifier,
        "official_longitudinal_data": False,
        "passed": all(
            value.get("passed") or value.get("status") == "ALREADY_PASSED"
            for value in results.values()
        ),
        "pre_live_report_sha256": pre_live["report_sha256"],
        "results": results,
    }
    report = {**core, "report_sha256": artifact_hash(core)}
    _write_json(run_dir / "report.json", report)
    return report


def _response_flags(normalized: Any) -> dict[str, Any]:
    finish = str(normalized.finish_reason or "")
    refusal = bool(normalized.safety.get("refusal")) or "refus" in finish.lower()
    provider_block = finish.upper() in {"PROMPT_BLOCKED", "SAFETY", "BLOCKED"}
    truncation = finish.lower() in {
        "length",
        "max_tokens",
        "max_output_tokens",
        "incomplete",
    }
    return {
        "finish_reason": normalized.finish_reason,
        "stop_reason_is_max_tokens": finish == "max_tokens",
        "refusal_observed": refusal,
        "provider_block_observed": provider_block,
        "truncation_or_output_cap_stop_observed": truncation,
        "visible_output_characters": len(normalized.text),
        "usage": normalized.usage,
    }


def _anthropic_thinking_metadata(body: dict[str, Any]) -> dict[str, Any]:
    content = body.get("content")
    blocks = content if isinstance(content, list) else []
    typed_blocks = [block for block in blocks if isinstance(block, dict)]
    thinking_blocks = [block for block in typed_blocks if block.get("type") == "thinking"]
    redacted_blocks = [
        block for block in typed_blocks if block.get("type") == "redacted_thinking"
    ]
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    details = (
        usage.get("output_tokens_details")
        if isinstance(usage.get("output_tokens_details"), dict)
        else {}
    )
    thinking_tokens = details.get("thinking_tokens")
    return {
        "content_block_types": [
            str(block.get("type")) for block in typed_blocks if block.get("type")
        ],
        "thinking_block_count": len(thinking_blocks),
        "thinking_content_characters": sum(
            len(str(block.get("thinking", ""))) for block in thinking_blocks
        ),
        "redacted_thinking_block_count": len(redacted_blocks),
        "thinking_tokens": thinking_tokens,
        "thinking_token_metadata_exposed": thinking_tokens is not None,
        "thinking_content_metadata_exposed": bool(thinking_blocks or redacted_blocks),
    }


def run_provider_qualification_set(
    *,
    module_root: Path | None = None,
    output_root: Path | None = None,
    series_ids: Iterable[str] | None = None,
    adapter_factory: AdapterFactory = _first_party_factory,
    run_id: str | None = None,
) -> dict[str, Any]:
    module_root = (module_root or default_module_root()).resolve()
    output_root = (output_root or default_output_root(module_root)).resolve()
    plan, battery = _load_plan(module_root)
    selected = _selected_series(plan, series_ids)
    items = {item.item_id: item for item in battery.items}
    qualification_items = [items[item_id] for item_id in plan["qualification_item_ids"]]
    identifier = run_id or _run_id("Q2")
    run_dir = output_root / "Q2" / identifier
    pre_live = w0_pre_live_report(module_root=module_root, series_ids=selected)
    if not pre_live["W0_Q1_EXECUTABLE"]:
        results = {
            series_id: {
                "status": "BLOCKED_PRE_LIVE_OPERATIONAL_GATES",
                "passed": False,
                "requested_model": plan["models"][series_id].get("requested_model"),
                "pre_live_report_sha256": pre_live["report_sha256"],
            }
            for series_id in selected
        }
        core = {
            "schema_version": "1.0",
            "stage": "W0-Q2",
            "run_id": identifier,
            "official_longitudinal_data": False,
            "item_ids": plan["qualification_item_ids"],
            "passed": False,
            "pre_live": pre_live,
            "results": results,
        }
        report = {**core, "report_sha256": artifact_hash(core)}
        _write_json(run_dir / "report.json", report)
        return report
    results: dict[str, Any] = {}
    for series_id in selected:
        existing = _read_gate(output_root, "Q2", series_id)
        if existing:
            results[series_id] = {"status": "ALREADY_PASSED", "gate": existing}
            continue
        q1_gate = _read_gate(output_root, "Q1", series_id)
        if not q1_gate:
            results[series_id] = {
                "status": "BLOCKED_Q1_NOT_PASSED",
                "passed": False,
                "requested_model": plan["models"][series_id].get("requested_model"),
            }
            continue
        row = plan["models"][series_id]
        provider = str(row["provider"])
        model = str(q1_gate["requested_model"])
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "stage": "W0-Q2",
            "series_id": series_id,
            "provider": provider,
            "requested_model": model,
            "official_longitudinal_data": False,
            "q1_gate_sha256": q1_gate["gate_sha256"],
            "item_results": [],
            "closed_diagnostic_results": [],
            "substitution_attempted": False,
            "pre_live_report_sha256": pre_live["report_sha256"],
        }
        try:
            adapter = adapter_factory(provider)
        except Exception as exc:
            result.update(
                status="FAILED_CLOSED",
                passed=False,
                error=f"adapter initialization: {type(exc).__name__}: {exc}",
            )
            result_path = run_dir / series_id / "result.json"
            _write_json(result_path, result)
            results[series_id] = result
            continue
        if not adapter.api_key:
            result.update(status="BLOCKED_CREDENTIAL_MISSING", passed=False)
        else:
            failures: list[str] = []
            for item in qualification_items:
                label = f"{item.item_id}-native" if series_id == "M05" else item.item_id
                try:
                    request, audit = _prepare_request(
                        adapter,
                        series_id=series_id,
                        model=model,
                        prompt=item.prompt,
                    )
                    response, error = _send_captured(
                        adapter, run_dir / series_id, label, request
                    )
                    if error or response is None or response.body is None:
                        raise ProviderError(error or "response was not JSON")
                    normalized = adapter.normalize(response.body)
                    identity_match = _identity_match(model, normalized.returned_model)
                    item_result = {
                        "item_id": item.item_id,
                        "prompt_sha256": item.prompt_sha256,
                        "request_sha256": audit["serialized_request_sha256"],
                        "response_sha256": sha256_bytes(response.body_bytes),
                        "returned_model": normalized.returned_model,
                        "returned_identity_matches_requested": identity_match,
                        **_response_flags(normalized),
                    }
                    if series_id == "M02":
                        item_result["stop_reason"] = normalized.finish_reason
                        item_result["anthropic_thinking_metadata"] = (
                            _anthropic_thinking_metadata(response.body)
                        )
                    result["item_results"].append(item_result)
                    if not identity_match:
                        failures.append(f"{item.item_id}: returned identity mismatch")
                except Exception as exc:
                    failures.append(f"{item.item_id}: {type(exc).__name__}: {exc}")
            if series_id == "M05":
                for item in qualification_items:
                    label = f"{item.item_id}-closed-diagnostic"
                    try:
                        request, audit = _prepare_request(
                            adapter,
                            series_id=series_id,
                            model=model,
                            prompt=item.prompt,
                            diagnostic=True,
                        )
                        response, error = _send_captured(
                            adapter, run_dir / series_id, label, request
                        )
                        if error or response is None or response.body is None:
                            raise ProviderError(error or "diagnostic response was not JSON")
                        normalized = adapter.normalize(response.body)
                        identity_match = _identity_match(model, normalized.returned_model)
                        diagnostic_result = {
                            "item_id": item.item_id,
                            "classification": "NON_OFFICIAL_W0_ONLY",
                            "disable_search": True,
                            "prompt_sha256": item.prompt_sha256,
                            "request_sha256": audit["serialized_request_sha256"],
                            "response_sha256": sha256_bytes(response.body_bytes),
                            "returned_model": normalized.returned_model,
                            "returned_identity_matches_requested": identity_match,
                            **_response_flags(normalized),
                        }
                        result["closed_diagnostic_results"].append(diagnostic_result)
                        if not identity_match:
                            failures.append(
                                f"{item.item_id} diagnostic: returned identity mismatch"
                            )
                    except Exception as exc:
                        failures.append(
                            f"{item.item_id} diagnostic: {type(exc).__name__}: {exc}"
                        )
            complete = len(result["item_results"]) == 7 and (
                series_id != "M05" or len(result["closed_diagnostic_results"]) == 7
            )
            result.update(
                status="PASSED" if complete and not failures else "FAILED_CLOSED",
                passed=complete and not failures,
                failures=failures,
                refusals_observed=sum(
                    bool(value["refusal_observed"]) for value in result["item_results"]
                ),
                provider_blocks_observed=sum(
                    bool(value["provider_block_observed"])
                    for value in result["item_results"]
                ),
                truncation_or_output_cap_stops_observed=sum(
                    bool(value["truncation_or_output_cap_stop_observed"])
                    for value in result["item_results"]
                ),
                raw_preservation=complete,
                secret_redaction_validated=complete,
            )
            if series_id == "M02":
                result["opus_5_output_cap_evidence"] = {
                    "permanent_mibo_lineage_id": "MIBO-SL-002",
                    "permanent_lineage_label": "Claude",
                    "canonical_model_id_provider_documented_pinned_snapshot": (
                        model == "claude-opus-5"
                    ),
                    "serving_infrastructure_behavioral_variation_possible": True,
                    "effort_omitted": True,
                    "thinking_override_omitted": True,
                    "max_tokens": 8192,
                    "stop_reason_max_tokens_count": sum(
                        value["finish_reason"] == "max_tokens"
                        for value in result["item_results"]
                    ),
                    "visible_output_characters": [
                        value["visible_output_characters"]
                        for value in result["item_results"]
                    ],
                    "thinking_metadata_by_item": [
                        {
                            "item_id": value["item_id"],
                            **value["anthropic_thinking_metadata"],
                        }
                        for value in result["item_results"]
                    ],
                    "frozen_protocol_modified": False,
                    "material_constraint_interpretation": "HUMAN_REVIEW_REQUIRED",
                }
        result_path = run_dir / series_id / "result.json"
        _write_json(result_path, result)
        if result.get("passed") is True:
            _write_gate(
                output_root,
                stage="Q2",
                series_id=series_id,
                result=result,
                result_path=result_path,
            )
        results[series_id] = result
    core = {
        "schema_version": "1.0",
        "stage": "W0-Q2",
        "run_id": identifier,
        "official_longitudinal_data": False,
        "item_ids": plan["qualification_item_ids"],
        "passed": all(
            value.get("passed") or value.get("status") == "ALREADY_PASSED"
            for value in results.values()
        ),
        "pre_live_report_sha256": pre_live["report_sha256"],
        "results": results,
    }
    report = {**core, "report_sha256": artifact_hash(core)}
    _write_json(run_dir / "report.json", report)
    return report


def _subset_battery(battery: Any, item_ids: list[str]) -> dict[str, Any]:
    selected = {item.item_id: item for item in battery.items}
    return {
        "battery_id": "MIBO-EDU-W0-CORE-35",
        "version": "1.0",
        "status": "ENGINEERING_ONLY",
        "approved": False,
        "official_longitudinal_eligible": False,
        "expected_item_count": 7,
        "items": [
            {
                "id": item_id,
                "stratum": selected[item_id].stratum,
                "frozen": True,
                "prompt_ja": selected[item_id].prompt,
                "prompt_sha256": selected[item_id].prompt_sha256,
            }
            for item_id in item_ids
        ],
    }


def _materialize_rehearsal_panel(
    *,
    directory: Path,
    panel: str,
    models: list[dict[str, Any]],
    battery_raw: dict[str, Any],
) -> tuple[Any, Any, dict[str, Any], dict[str, Any]]:
    battery_path = directory / "battery.yaml"
    registry_path = directory / "registry.yaml"
    manifest_path = directory / "manifest.yaml"
    model_lock_path = directory / "model-lock.json"
    schedule_path = directory / "schedule.json"
    write_immutable(
        battery_path,
        yaml.safe_dump(battery_raw, allow_unicode=True, sort_keys=False).encode("utf-8"),
    )
    registry_raw = {
        "registry_id": f"MIBO-EDU-W0-Q3-{panel.upper()}",
        "version": "1.0",
        "status": "ENGINEERING",
        "approved": False,
        "series": [
            {
                "series_id": value["series_id"],
                "provider": value["provider"],
                "label": f"W0 rehearsal {value['series_id']}",
                "closed_eligibility": panel == "closed",
            }
            for value in models
        ],
    }
    write_immutable(
        registry_path, yaml.safe_dump(registry_raw, sort_keys=False).encode("utf-8")
    )
    environment = "CLOSED" if panel == "closed" else "NATIVE"
    sampling = {
        value["provider"]: SAMPLING[value["series_id"]] for value in models
    }
    manifest_raw = {
        "schema_version": "1.0",
        "status": "ENGINEERING",
        "approved": False,
        "wave_id": f"MIBO-EDU-W0-Q3-{panel.upper()}",
        "site_id": "MIBO-SITE-JP01",
        "official_longitudinal_data": False,
        "protocol_version": "w0-live-qualification-1.0",
        "battery": "battery.yaml",
        "model_registry": "registry.yaml",
        "model_lock": "model-lock.json",
        "schedule": "schedule.json",
        "environment": environment,
        "replications": 1,
        "random_seed": f"MIBO-Education|W0-Q3|Core-35|{panel}|v1.0",
        "field_window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-12-31T23:59:59Z",
        },
        "sampling": sampling,
        "native_options": {},
        "max_technical_attempts": 3,
        "retry_delays_minutes": [10, 30],
        "approvals": {
            "protocol_owner": False,
            "provider_terms_review": False,
            "ethics_or_governance_determination": False,
        },
    }
    write_immutable(
        manifest_path, yaml.safe_dump(manifest_raw, sort_keys=False).encode("utf-8")
    )
    manifest = load_manifest(manifest_path)
    registry = load_registry(registry_path)
    lock_core = {
        "schema_version": "1.0",
        "wave_id": manifest.wave_id,
        "registry_sha256": registry["registry_sha256"],
        "resolved_at": utc_now(),
        "models": models,
    }
    lock = {**lock_core, "model_lock_sha256": artifact_hash(lock_core)}
    _write_json(model_lock_path, lock)
    loaded_battery = load_battery(battery_path)
    loaded_lock = load_model_lock(model_lock_path)
    schedule = create_schedule(manifest, loaded_battery, loaded_lock)
    if schedule_path != manifest.schedule_path:
        raise ValidationError("rehearsal schedule path mismatch")
    return manifest, loaded_battery, loaded_lock, schedule


def run_dress_rehearsal(
    *,
    module_root: Path | None = None,
    output_root: Path | None = None,
    adapter_factory: AdapterFactory = _first_party_factory,
    run_id: str | None = None,
    sleep: Any = None,
) -> dict[str, Any]:
    module_root = (module_root or default_module_root()).resolve()
    output_root = (output_root or default_output_root(module_root)).resolve()
    plan, battery = _load_plan(module_root)
    pre_live = w0_pre_live_report(module_root=module_root, series_ids=SERIES_IDS)
    if not pre_live["W0_Q1_EXECUTABLE"]:
        raise ValidationError(
            "W0-Q3 refused: pre-live operational gates are incomplete: "
            f"{pre_live['W0_Q1_EXECUTABLE_reasons']}"
        )
    q2_gates = {series_id: _read_gate(output_root, "Q2", series_id) for series_id in SERIES_IDS}
    missing = [series_id for series_id, gate in q2_gates.items() if gate is None]
    if missing:
        raise ValidationError(f"W0-Q3 refused: required Q2 gates are missing: {missing}")
    adapters = {
        series_id: adapter_factory(str(plan["models"][series_id]["provider"]))
        for series_id in SERIES_IDS
    }
    missing_credentials = [
        series_id for series_id, adapter in adapters.items() if not adapter.api_key
    ]
    if missing_credentials:
        raise ValidationError(
            f"W0-Q3 refused: credentials are missing for {missing_credentials}"
        )
    identifier = run_id or _run_id("Q3")
    run_dir = output_root / "Q3" / identifier
    battery_raw = _subset_battery(battery, plan["qualification_item_ids"])
    model_rows: dict[str, dict[str, Any]] = {}
    for series_id, gate in q2_gates.items():
        assert gate is not None
        model_rows[series_id] = {
            "series_id": series_id,
            "provider": plan["models"][series_id]["provider"],
            "requested_model": gate["requested_model"],
            "live_verified": True,
            "pinning_evidence": (
                "provider-documented pinned canonical ID"
                if series_id == "M02" and gate["requested_model"] == "claude-opus-5"
                else "W0 Q1/Q2 live identity evidence"
            ),
            "pinning_verified": series_id == "M02" and gate["requested_model"] == "claude-opus-5",
            "provider_metadata": {
                "q2_gate_sha256": gate["gate_sha256"],
                "returned_model": gate.get("returned_model"),
            },
        }
    panel_definitions = {
        "closed": [model_rows[series_id] for series_id in SERIES_IDS[:4]],
        "native": [model_rows["M05"]],
    }

    def rehearsal_factory(provider: str) -> ProviderAdapter:
        for adapter in adapters.values():
            if adapter.provider == provider:
                return adapter
        raise ValidationError(f"no first-party rehearsal adapter for {provider}")

    panel_results: dict[str, Any] = {}
    total_completed = 0
    total_technical_failures = 0
    for panel, models in panel_definitions.items():
        manifest, subset, lock, schedule = _materialize_rehearsal_panel(
            directory=run_dir / panel,
            panel=panel,
            models=models,
            battery_raw=battery_raw,
        )
        runner_kwargs: dict[str, Any] = {}
        if sleep is not None:
            runner_kwargs["sleep"] = sleep
        stats = run_wave(
            manifest=manifest,
            battery=subset,
            lock=lock,
            schedule=schedule,
            ignore_planned_time=True,
            adapter_factory=rehearsal_factory,
            **runner_kwargs,
        )
        qc = run_qc(manifest, subset, lock, schedule)
        certificate = create_certificate(
            manifest.source.parent,
            manifest_sha256=manifest.content_sha256,
            battery_sha256=subset.content_sha256,
            model_lock_sha256=lock["model_lock_sha256"],
            schedule_sha256=schedule["schedule_sha256"],
        )
        total_completed += stats["completed"]
        total_technical_failures += stats["technical_failure"]
        panel_results[panel] = {
            "stats": stats,
            "qc_passed": qc["passed"],
            "qc_report_sha256": qc["qc_report_sha256"],
            "certificate_sha256": certificate["certificate_sha256"],
            "official_longitudinal_data": False,
        }
    passed = total_completed == 35 and total_technical_failures == 0 and all(
        value["qc_passed"] for value in panel_results.values()
    )
    core = {
        "schema_version": "1.0",
        "stage": "W0-Q3",
        "run_id": identifier,
        "official_longitudinal_data": False,
        "expected_observations": 35,
        "completed_observations": total_completed,
        "technical_failures": total_technical_failures,
        "passed": passed,
        "panels": panel_results,
    }
    report = {**core, "report_sha256": artifact_hash(core)}
    report_path = run_dir / "report.json"
    _write_json(report_path, report)
    if passed:
        gate_core = {
            "schema_version": "1.0",
            "stage": "Q3",
            "passed": True,
            "official_longitudinal_data": False,
            "qualified_at": utc_now(),
            "result_path": str(report_path.resolve()),
            "result_sha256": sha256_file(report_path),
        }
        _write_json(
            output_root / "gates" / "Q3-CORE-35.json",
            {**gate_core, "gate_sha256": artifact_hash(gate_core)},
        )
    return report


def qualification_status_report(
    *,
    module_root: Path | None = None,
    output_root: Path | None = None,
    series_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    module_root = (module_root or default_module_root()).resolve()
    output_root = (output_root or default_output_root(module_root)).resolve()
    plan, _ = _load_plan(module_root)
    selected = _selected_series(plan, series_ids)
    pre_live = w0_pre_live_report(module_root=module_root, series_ids=selected)
    gates: dict[str, Any] = {}
    resolved_candidates: dict[str, bool] = {}
    for series_id in selected:
        model = plan["models"][series_id].get("requested_model")
        resolved_candidates[series_id] = isinstance(model, str) and bool(model)
        gates[series_id] = {
            "Q1": _read_gate(output_root, "Q1", series_id) is not None,
            "Q2": _read_gate(output_root, "Q2", series_id) is not None,
        }
    q1_executable_reasons = list(pre_live["W0_Q1_EXECUTABLE_reasons"])
    unresolved = [
        series_id for series_id, resolved in resolved_candidates.items() if not resolved
    ]
    if unresolved:
        q1_executable_reasons.append(f"exact W0 candidates are unresolved: {unresolved}")
    return {
        "schema_version": "1.0",
        "official_longitudinal_data": False,
        "selected_series": selected,
        "HUMAN_GOVERNANCE_READY": pre_live["HUMAN_GOVERNANCE_READY"],
        "HUMAN_GOVERNANCE_READY_reasons": pre_live[
            "HUMAN_GOVERNANCE_READY_reasons"
        ],
        "CREDENTIAL_ENVIRONMENT_READY": pre_live["CREDENTIAL_ENVIRONMENT_READY"],
        "CREDENTIAL_ENVIRONMENT_READY_reasons": pre_live[
            "CREDENTIAL_ENVIRONMENT_READY_reasons"
        ],
        "credentials_present": pre_live["credential_environment"][
            "credentials_present"
        ],
        "credential_values_exposed": False,
        "credential_values_hashed": False,
        "environment_values_exposed": False,
        "environment_values_hashed": False,
        "exact_w0_candidates_resolved": resolved_candidates,
        "W0_Q1_EXECUTABLE": not q1_executable_reasons,
        "W0_Q1_EXECUTABLE_reasons": q1_executable_reasons,
        "gates": gates,
        "Q3": _rehearsal_gate_passed(output_root),
        "governance_records": pre_live["governance_records"],
        "output_root_configured": pre_live["credential_environment"][
            "persistent_evidence_root_present"
        ],
    }

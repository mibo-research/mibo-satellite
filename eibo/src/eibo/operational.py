from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapters.perplexity_w0 import load_w0_agent_profile
from .artifacts import load_yaml
from .errors import ValidationError
from .util import artifact_hash, sha256_file

SERIES_IDS = ("M01", "M02", "M03", "M04", "M05")
CREDENTIAL_ENV_BY_SERIES = {
    "M01": "OPENAI_API_KEY",
    "M02": "ANTHROPIC_API_KEY",
    "M03": "GEMINI_API_KEY",
    "M04": "XAI_API_KEY",
    "M05": "PERPLEXITY_API_KEY",
}
EVIDENCE_ROOT_ENV = "EIBO_W0_EVIDENCE_ROOT"
PROTECTED_ENVIRONMENT_MARKER = "EIBO_W0_PROTECTED_ENVIRONMENT"
RUNNER_REQUIREMENTS_MARKER = "EIBO_W0_RUNNER_REQUIREMENTS"
GOVERNANCE_RECORDS = {
    "protocol_owner": "protocol-owner.yaml",
    "terms_review": "terms-review.yaml",
    "ethics_or_governance_determination": "ethics-or-governance-determination.yaml",
}


def _selected_series(series_ids: Iterable[str] | None) -> list[str]:
    selected = list(series_ids or SERIES_IDS)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("operational-preflight series selection is empty or duplicated")
    unknown = sorted(set(selected) - set(SERIES_IDS))
    if unknown:
        raise ValueError(f"unknown operational-preflight series: {unknown}")
    return selected


def _presence(environment: Mapping[str, str], name: str) -> bool:
    return bool(environment.get(name))


def _valid_decision_time(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def provider_execution_hold_report(
    module_root: Path, series_ids: Iterable[str] | None = None
) -> dict[str, Any]:
    """Apply runtime holds without changing the scientific panel or candidate IDs."""
    selected = _selected_series(series_ids)
    path = module_root / "waves/W0/provider-execution-holds.yaml"
    holds: dict[str, Any] = {}
    if path.is_file():
        value = load_yaml(path)
        if (
            value.get("schema_version") != "1.0"
            or value.get("official_longitudinal_data") is not False
            or not isinstance(value.get("holds"), dict)
        ):
            raise ValidationError("invalid W0 provider execution holds")
        holds = value["holds"]
        if set(holds) - set(SERIES_IDS):
            raise ValidationError("unknown series in W0 provider execution holds")
        for series_id, hold in holds.items():
            if (
                not isinstance(hold, dict)
                or hold.get("execution_permitted") is not False
                or not isinstance(hold.get("status"), str)
                or not hold["status"].strip()
                or not isinstance(hold.get("reason"), str)
                or not hold["reason"].strip()
            ):
                raise ValidationError(f"invalid W0 execution hold for {series_id}")
    selected_holds = {key: holds[key] for key in selected if key in holds}
    return {
        "holds": selected_holds,
        "source_sha256": sha256_file(path) if path.is_file() else None,
        "reasons": [
            f"{key} live execution held: {hold['status']}: {hold['reason']}"
            for key, hold in selected_holds.items()
        ],
    }


def human_governance_report(module_root: Path) -> dict[str, Any]:
    module_root = module_root.resolve()
    records_root = module_root / "waves" / "W0" / "governance" / "records"
    records: dict[str, Any] = {}
    reasons: list[str] = []
    for record_type, filename in GOVERNANCE_RECORDS.items():
        path = records_root / filename
        relative_path = path.relative_to(module_root).as_posix()
        result: dict[str, Any] = {
            "record_type": record_type,
            "record_path": relative_path,
            "present": path.is_file(),
            "valid_final_human_record": False,
        }
        if not path.is_file():
            reasons.append(f"human governance record is missing: {relative_path}")
            records[record_type] = result
            continue
        record_errors: list[str] = []
        try:
            record = load_yaml(path)
        except Exception as exc:
            record_errors.append(f"cannot load record: {exc}")
            record = {}
        if record.get("schema_version") != "1.0":
            record_errors.append("schema_version must be 1.0")
        if record.get("record_type") != record_type:
            record_errors.append(f"record_type must be {record_type}")
        if record.get("status") != "FINAL":
            record_errors.append("status must be FINAL")
        determination = record.get("determination")
        if not isinstance(determination, str) or not determination.strip():
            record_errors.append("determination must be a non-empty human determination")
        decided_by = record.get("decided_by")
        if not isinstance(decided_by, dict):
            record_errors.append("decided_by must identify a human decision-maker")
        else:
            if decided_by.get("actor_type") != "HUMAN":
                record_errors.append("decided_by.actor_type must be HUMAN")
            for field in ("name", "role"):
                value = decided_by.get(field)
                if not isinstance(value, str) or not value.strip():
                    record_errors.append(f"decided_by.{field} must be non-empty")
        if not _valid_decision_time(record.get("decided_at")):
            record_errors.append("decided_at must be an ISO-8601 timestamp with timezone")
        rationale = record.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            record_errors.append("rationale must be non-empty")
        references = record.get("evidence_references")
        if not isinstance(references, list) or any(
            not isinstance(value, str) or not value.strip() for value in references
        ):
            record_errors.append("evidence_references must be a list of non-empty references")
        if record.get("human_attestation") is not True:
            record_errors.append("human_attestation must be explicitly true")
        if record.get("agent_approval_permitted") is not False:
            record_errors.append("agent_approval_permitted must remain false")
        result["status"] = record.get("status")
        result["determination_recorded"] = bool(
            isinstance(determination, str) and determination.strip()
        )
        result["human_attribution_recorded"] = bool(
            isinstance(decided_by, dict)
            and decided_by.get("actor_type") == "HUMAN"
            and isinstance(decided_by.get("name"), str)
            and decided_by.get("name", "").strip()
        )
        result["record_sha256"] = sha256_file(path)
        result["errors"] = record_errors
        result["valid_final_human_record"] = not record_errors
        reasons.extend(f"{record_type}: {error}" for error in record_errors)
        records[record_type] = result
    core = {
        "schema_version": "1.0",
        "HUMAN_GOVERNANCE_READY": not reasons,
        "agent_approval_permitted": False,
        "records": records,
        "reasons": reasons,
    }
    return {**core, "report_sha256": artifact_hash(core)}


def credential_environment_report(
    *,
    series_ids: Iterable[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    selected = _selected_series(series_ids)
    env = os.environ if environment is None else environment
    credentials_present = {
        series_id: _presence(env, CREDENTIAL_ENV_BY_SERIES[series_id])
        for series_id in selected
    }
    evidence_root_present = _presence(env, EVIDENCE_ROOT_ENV)
    github_actions_present = _presence(env, "GITHUB_ACTIONS")
    protected_environment_present = _presence(env, PROTECTED_ENVIRONMENT_MARKER)
    runner_requirements_present = _presence(env, RUNNER_REQUIREMENTS_MARKER)
    reasons = [
        f"credential is missing for {series_id}: {CREDENTIAL_ENV_BY_SERIES[series_id]}"
        for series_id, present in credentials_present.items()
        if not present
    ]
    if not evidence_root_present:
        reasons.append(f"persistent evidence-root marker is missing: {EVIDENCE_ROOT_ENV}")
    if github_actions_present and not protected_environment_present:
        reasons.append(
            f"protected W0 environment marker is missing: {PROTECTED_ENVIRONMENT_MARKER}"
        )
    if github_actions_present and not runner_requirements_present:
        reasons.append(
            f"protected W0 runner marker is missing: {RUNNER_REQUIREMENTS_MARKER}"
        )
    core = {
        "schema_version": "1.0",
        "selected_series": selected,
        "CREDENTIAL_ENVIRONMENT_READY": not reasons,
        "credentials_present": credentials_present,
        "persistent_evidence_root_present": evidence_root_present,
        "github_actions_context_present": github_actions_present,
        "protected_environment_required": github_actions_present,
        "protected_environment_marker_present": protected_environment_present,
        "runner_requirements_marker_present": runner_requirements_present,
        "credential_values_exposed": False,
        "credential_values_hashed": False,
        "environment_values_exposed": False,
        "environment_values_hashed": False,
        "reasons": reasons,
    }
    return {**core, "report_sha256": artifact_hash(core)}


def w0_pre_live_report(
    *,
    module_root: Path,
    series_ids: Iterable[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    selected = _selected_series(series_ids)
    governance = human_governance_report(module_root)
    credential_environment = credential_environment_report(
        series_ids=selected, environment=environment
    )
    execution_holds = provider_execution_hold_report(module_root, selected)
    profile_reasons: list[str] = []
    profile_hashes: dict[str, str] = {}
    if "M05" in selected:
        try:
            profile_hashes["M05"] = load_w0_agent_profile(module_root)["profile_sha256"]
        except (OSError, ValidationError) as exc:
            profile_reasons.append(f"M05 W0 Agent API profile unavailable: {exc}")
    reasons = [
        *governance["reasons"],
        *credential_environment["reasons"],
        *execution_holds["reasons"],
        *profile_reasons,
    ]
    core = {
        "schema_version": "1.0",
        "selected_series": selected,
        "HUMAN_GOVERNANCE_READY": governance["HUMAN_GOVERNANCE_READY"],
        "CREDENTIAL_ENVIRONMENT_READY": credential_environment[
            "CREDENTIAL_ENVIRONMENT_READY"
        ],
        "W0_Q1_EXECUTABLE": not reasons,
        "HUMAN_GOVERNANCE_READY_reasons": governance["reasons"],
        "CREDENTIAL_ENVIRONMENT_READY_reasons": credential_environment["reasons"],
        "W0_Q1_EXECUTABLE_reasons": reasons,
        "governance_report_sha256": governance["report_sha256"],
        "credential_environment_report_sha256": credential_environment["report_sha256"],
        "governance_records": governance["records"],
        "credential_environment": credential_environment,
        "provider_execution_holds": execution_holds,
        "qualification_profile_hashes": profile_hashes,
        "secret_or_environment_values_exposed": False,
    }
    return {**core, "report_sha256": artifact_hash(core)}

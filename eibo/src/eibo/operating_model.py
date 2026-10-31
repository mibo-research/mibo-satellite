from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import load_yaml
from .errors import ValidationError


def load_operating_model(path: Path) -> dict[str, Any]:
    value = load_yaml(path)
    errors: list[str] = []

    expected_scalars = {
        "schema_version": "1.0",
        "project_name": "EIBO",
        "legacy_project_name": "MIBO-Education",
        "status": "CONFIGURED_PENDING_HUMAN_ATTESTATION",
        "effective_scope": "PROSPECTIVE_EIBO_WAVES_ONLY",
    }
    for field, expected in expected_scalars.items():
        if value.get(field) != expected:
            errors.append(f"{field} must be {expected}")

    legacy = value.get("legacy_scientific_record")
    if not isinstance(legacy, dict):
        errors.append("legacy_scientific_record must be a mapping")
    else:
        for field in (
            "preserve_frozen_v1_0_bytes",
            "preserve_legacy_artifact_ids",
            "preserve_legacy_wave_ids",
        ):
            if legacy.get(field) is not True:
                errors.append(f"legacy_scientific_record.{field} must be true")
        for field in ("w01_compatible_with_this_operating_model", "w01_execution_permitted"):
            if legacy.get(field) is not False:
                errors.append(f"legacy_scientific_record.{field} must be false")

    solo = value.get("solo_operations")
    if not isinstance(solo, dict):
        errors.append("solo_operations must be a mapping")
    else:
        if solo.get("mode") != "SINGLE_HUMAN_OPERATOR_WITH_AUTOMATION":
            errors.append("solo_operations.mode is invalid")
        if solo.get("human_operator_count") != 1:
            errors.append("solo_operations.human_operator_count must be 1")
        if solo.get("separate_human_operator_required") is not False:
            errors.append("solo_operations.separate_human_operator_required must be false")
        if solo.get("automation_may_execute_approved_workflows") is not True:
            errors.append("solo operations must permit approved workflow automation")
        if solo.get("agent_may_approve_governance") is not False:
            errors.append("agents must never approve governance")
        if solo.get("explicit_human_governance_records_required") is not True:
            errors.append("explicit human governance records must remain required")

    coding = value.get("coding")
    if not isinstance(coding, dict):
        errors.append("coding must be a mapping")
    else:
        if coding.get("primary_coder_type") != "HUMAN":
            errors.append("coding.primary_coder_type must be HUMAN")
        if coding.get("primary_coder_count") != 1:
            errors.append("coding.primary_coder_count must be 1")
        if coding.get("independent_human_coding_required") is not False:
            errors.append("independent human coding must not be required")
        if coding.get("inter_rater_reliability_claimed") is not False:
            errors.append("inter-rater reliability must not be claimed")
        for field in ("primary_codes_must_be_blind", "coding_provenance_required"):
            if coding.get(field) is not True:
                errors.append(f"coding.{field} must be true")
        ai = coding.get("ai_secondary")
        if not isinstance(ai, dict):
            errors.append("coding.ai_secondary must be a mapping")
        else:
            required_false = (
                "enabled_by_default",
                "may_replace_human_coder",
                "may_satisfy_independent_human_coder_requirement",
                "may_overwrite_primary_codes",
            )
            for field in required_false:
                if ai.get(field) is not False:
                    errors.append(f"coding.ai_secondary.{field} must be false")
            if ai.get("status") != "OPTIONAL":
                errors.append("coding.ai_secondary.status must be OPTIONAL")
            if ai.get("purpose") != "SENSITIVITY_ANALYSIS_ONLY":
                errors.append("AI secondary coding must be sensitivity analysis only")
            for field in (
                "outputs_must_remain_separate",
                "model_prompt_and_parameters_must_be_locked",
                "blind_to_primary_codes",
            ):
                if ai.get(field) is not True:
                    errors.append(f"coding.ai_secondary.{field} must be true")

    adoption = value.get("adoption")
    if not isinstance(adoption, dict):
        errors.append("adoption must be a mapping")
    else:
        if adoption.get("agent_approval_permitted") is not False:
            errors.append("adoption.agent_approval_permitted must be false")
        record = adoption.get("human_attestation_record")
        if record != "operations/operating-model-attestation.yaml":
            errors.append("adoption human attestation path is invalid")

    if errors:
        raise ValidationError("invalid EIBO operating model: " + "; ".join(errors))
    return value


def operating_model_report(module_root: Path) -> dict[str, Any]:
    module_root = module_root.resolve()
    model = load_operating_model(module_root / "operations" / "operating-model.yaml")
    relative_record = model["adoption"]["human_attestation_record"]
    record_path = module_root / relative_record
    reasons: list[str] = []
    if not record_path.is_file():
        reasons.append(f"human operating-model attestation is missing: {relative_record}")
        return {
            "configured": True,
            "human_attestation_complete": False,
            "record_path": relative_record,
            "reasons": reasons,
            "model": model,
        }

    record = load_yaml(record_path)
    if record.get("schema_version") != "1.0":
        reasons.append("operating-model attestation schema_version must be 1.0")
    if record.get("record_type") != "eibo_operating_model":
        reasons.append("operating-model attestation record_type is invalid")
    if record.get("status") != "FINAL":
        reasons.append("operating-model attestation status must be FINAL")
    determination = record.get("determination")
    if not isinstance(determination, str) or not determination.strip():
        reasons.append("operating-model determination must be non-empty")
    decided_by = record.get("decided_by")
    if not isinstance(decided_by, dict) or decided_by.get("actor_type") != "HUMAN":
        reasons.append("operating-model decision must be attributed to a human")
    else:
        for field in ("name", "role"):
            item = decided_by.get(field)
            if not isinstance(item, str) or not item.strip():
                reasons.append(f"operating-model decided_by.{field} must be non-empty")
    decided_at = record.get("decided_at")
    try:
        parsed = datetime.fromisoformat(str(decided_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError:
        reasons.append("operating-model decided_at must include an ISO-8601 timezone")
    rationale = record.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        reasons.append("operating-model rationale must be non-empty")
    references = record.get("evidence_references")
    if not isinstance(references, list) or any(
        not isinstance(reference, str) or not reference.strip()
        for reference in references
    ):
        reasons.append("operating-model evidence_references must be a string list")
    if record.get("human_attestation") is not True:
        reasons.append("operating-model human_attestation must be true")
    if record.get("agent_approval_permitted") is not False:
        reasons.append("operating-model agent_approval_permitted must remain false")
    return {
        "configured": True,
        "human_attestation_complete": not reasons,
        "record_path": relative_record,
        "reasons": reasons,
        "model": model,
    }

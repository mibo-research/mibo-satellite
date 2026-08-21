from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from miboe.operational import (
    GOVERNANCE_RECORDS,
    credential_environment_report,
    human_governance_report,
    w0_pre_live_report,
)

ROOT = Path(__file__).parents[1]


def _record(record_type: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "record_type": record_type,
        "status": "FINAL",
        "determination": "APPROVED_FOR_W0_LIVE_QUALIFICATION",
        "decided_by": {
            "actor_type": "HUMAN",
            "name": "Test Human",
            "role": "Protocol owner",
            "affiliation": "Test institution",
        },
        "decided_at": "2026-08-16T12:00:00+09:00",
        "rationale": "Explicit human test determination.",
        "evidence_references": [],
        "human_attestation": True,
        "agent_approval_permitted": False,
    }
    value.update(overrides)
    return value


def _write_records(module_root: Path, overrides: dict[str, dict[str, Any]] | None = None) -> None:
    records_root = module_root / "waves/W0/governance/records"
    records_root.mkdir(parents=True)
    for record_type, filename in GOVERNANCE_RECORDS.items():
        value = _record(record_type, **(overrides or {}).get(record_type, {}))
        (records_root / filename).write_text(
            yaml.safe_dump(value, sort_keys=False), encoding="utf-8"
        )


def test_governance_templates_are_pending_and_cannot_self_approve() -> None:
    template_root = ROOT / "waves/W0/governance/templates"
    for record_type, filename in GOVERNANCE_RECORDS.items():
        template = yaml.safe_load(
            (template_root / filename.replace(".yaml", ".template.yaml")).read_text(
                encoding="utf-8"
            )
        )
        assert template["record_type"] == record_type
        assert template["status"] == "PENDING_HUMAN_DETERMINATION"
        assert template["determination"] is None
        assert template["human_attestation"] is False
        assert template["agent_approval_permitted"] is False
        assert set(template) >= {
            "status",
            "determination",
            "decided_by",
            "decided_at",
            "rationale",
            "evidence_references",
        }


def test_human_governance_is_fail_closed_until_all_records_are_final(tmp_path: Path) -> None:
    report = human_governance_report(tmp_path)
    assert report["HUMAN_GOVERNANCE_READY"] is False
    assert len(report["reasons"]) == 3
    _write_records(tmp_path)
    report = human_governance_report(tmp_path)
    assert report["HUMAN_GOVERNANCE_READY"] is True
    assert report["reasons"] == []
    assert all(
        value["valid_final_human_record"] for value in report["records"].values()
    )


def test_agent_attribution_is_rejected_even_when_record_claims_final(tmp_path: Path) -> None:
    _write_records(
        tmp_path,
        {
            "protocol_owner": {
                "decided_by": {
                    "actor_type": "AGENT",
                    "name": "Automated agent",
                    "role": "Agent",
                    "affiliation": None,
                }
            }
        },
    )
    report = human_governance_report(tmp_path)
    assert report["HUMAN_GOVERNANCE_READY"] is False
    assert any("actor_type must be HUMAN" in reason for reason in report["reasons"])


@pytest.mark.parametrize("determination", ["NOT_APPLICABLE", "NOT_HUMAN_SUBJECTS"])
def test_nonapplicable_determinations_still_require_human_and_rationale(
    tmp_path: Path, determination: str
) -> None:
    _write_records(
        tmp_path,
        {
            "ethics_or_governance_determination": {
                "determination": determination,
                "decided_by": {
                    "actor_type": "HUMAN",
                    "name": None,
                    "role": "Reviewer",
                    "affiliation": None,
                },
                "rationale": None,
            }
        },
    )
    report = human_governance_report(tmp_path)
    assert report["HUMAN_GOVERNANCE_READY"] is False
    reasons = " ".join(report["reasons"])
    assert "decided_by.name must be non-empty" in reasons
    assert "rationale must be non-empty" in reasons


def test_provider_specific_credential_preflight_checks_only_selected_series() -> None:
    sentinel = "unit-test-credential-must-never-appear"
    environment = {
        "ANTHROPIC_API_KEY": sentinel,
        "MIBOE_W0_EVIDENCE_ROOT": "private-path-must-never-appear",
    }
    report = credential_environment_report(series_ids=["M02"], environment=environment)
    serialized = json.dumps(report)
    assert report["CREDENTIAL_ENVIRONMENT_READY"] is True
    assert report["credentials_present"] == {"M02": True}
    assert "M01" not in report["credentials_present"]
    assert sentinel not in serialized
    assert environment["MIBOE_W0_EVIDENCE_ROOT"] not in serialized
    assert report["credential_values_exposed"] is False
    assert report["credential_values_hashed"] is False
    assert report["environment_values_exposed"] is False
    assert report["environment_values_hashed"] is False


def test_github_context_requires_protected_environment_and_runner_markers() -> None:
    environment = {
        "OPENAI_API_KEY": "secret",
        "MIBOE_W0_EVIDENCE_ROOT": "evidence-root",
        "GITHUB_ACTIONS": "true",
    }
    report = credential_environment_report(series_ids=["M01"], environment=environment)
    assert report["CREDENTIAL_ENVIRONMENT_READY"] is False
    assert len(report["reasons"]) == 2
    environment["MIBOE_W0_PROTECTED_ENVIRONMENT"] = "present"
    environment["MIBOE_W0_RUNNER_REQUIREMENTS"] = "present"
    report = credential_environment_report(series_ids=["M01"], environment=environment)
    assert report["CREDENTIAL_ENVIRONMENT_READY"] is True


def test_combined_pre_live_gate_requires_human_and_selected_credential(
    tmp_path: Path,
) -> None:
    _write_records(tmp_path)
    report = w0_pre_live_report(
        module_root=tmp_path,
        series_ids=["M02"],
        environment={
            "ANTHROPIC_API_KEY": "secret",
            "MIBOE_W0_EVIDENCE_ROOT": "evidence-root",
        },
    )
    assert report["HUMAN_GOVERNANCE_READY"] is True
    assert report["CREDENTIAL_ENVIRONMENT_READY"] is True
    assert report["W0_Q1_EXECUTABLE"] is True
    assert report["secret_or_environment_values_exposed"] is False

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from eibo.cli import parser
from eibo.errors import ValidationError
from eibo.operating_model import load_operating_model, operating_model_report
from eibo.readiness import scientific_readiness
from eibo.util import sha256_file

LEGACY_FROZEN_HASHES = {
    "battery/ebb-ja-v1.0.yaml": (
        "5475d4c0edd651ae4fbc6e79c42642433fa7e0c27dba616a972236d35517cd4e"
    ),
    "battery/ebb-ja-v1.0.prompt-lock.json": (
        "8e251463eebb1c2e3f86ae7e82d98a4685afbf2dd3434731cdc72939d6ef6a82"
    ),
    "protocol/codebook-v1.0.md": (
        "c38cce32bad4e3b156ec6094d2368fca0937536519b25a2a80e115042da9161a"
    ),
    "protocol/item-level-scoring-manual-v1.0.md": (
        "3ae057c2e5f23312b5ca000f3d9f42ced4db23ca6b6db8c4889905c9f9a0bbef"
    ),
    "protocol/observation-protocol-v1.0.md": (
        "ca9b51ecbca1f5fd61443e7921ff4305dac82829a3043c795416c437b20d5d8f"
    ),
    "waves/W01/scientific-manifest-v1.0.yaml": (
        "ecb5b5aa779d0806cb034581d76ab1c128587f1b9590a7b482fc3fa93336a6f1"
    ),
}


def test_eibo_is_current_name_and_legacy_frozen_bytes_are_unchanged() -> None:
    root = Path(__file__).parents[1]
    assert root.name == "eibo"
    assert not (root.parent / "mibo-education").exists()
    assert parser().prog == "eibo"
    for relative_path, expected_hash in LEGACY_FROZEN_HASHES.items():
        assert sha256_file(root / relative_path) == expected_hash


def test_solo_operating_model_is_simple_fail_closed_and_prospective() -> None:
    root = Path(__file__).parents[1]
    model = load_operating_model(root / "operations" / "operating-model.yaml")
    assert model["solo_operations"]["human_operator_count"] == 1
    assert model["solo_operations"]["agent_may_approve_governance"] is False
    assert model["coding"]["primary_coder_count"] == 1
    assert model["coding"]["independent_human_coding_required"] is False
    assert model["coding"]["inter_rater_reliability_claimed"] is False
    assert model["coding"]["ai_secondary"]["enabled_by_default"] is False
    assert model["coding"]["ai_secondary"]["purpose"] == "SENSITIVITY_ANALYSIS_ONLY"
    assert model["legacy_scientific_record"]["w01_execution_permitted"] is False
    report = operating_model_report(root)
    assert report["configured"] is True
    assert report["human_attestation_complete"] is True
    assert report["reasons"] == []


def test_legacy_w01_remains_blocked_under_solo_operating_model() -> None:
    report = scientific_readiness(Path(__file__).parents[1])
    assert report["W01_READY"] is False
    assert any(
        "solo coding applies prospectively" in reason
        for reason in report["reasons"]["W01_READY"]
    )


def test_operating_model_rejects_a_two_coder_or_ai_replacement_drift(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    value = yaml.safe_load((root / "operations" / "operating-model.yaml").read_text())
    value["coding"]["primary_coder_count"] = 2
    value["coding"]["ai_secondary"]["may_replace_human_coder"] = True
    path = tmp_path / "operating-model.yaml"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError, match="primary_coder_count must be 1"):
        load_operating_model(path)


def test_named_human_can_attest_the_operating_model(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    target = tmp_path / "operations"
    target.mkdir()
    shutil.copy2(root / "operations" / "operating-model.yaml", target / "operating-model.yaml")
    record = {
        "schema_version": "1.0",
        "record_type": "eibo_operating_model",
        "status": "FINAL",
        "determination": "Adopt the prospective EIBO solo operating model.",
        "decided_by": {
            "actor_type": "HUMAN",
            "name": "Test Human",
            "role": "Protocol owner",
            "affiliation": "Test",
        },
        "decided_at": "2026-10-22T12:00:00+09:00",
        "rationale": "One accountable operator will run the automated workflow.",
        "evidence_references": ["protocol/amendments/EIBO-PA-001"],
        "human_attestation": True,
        "agent_approval_permitted": False,
    }
    (target / "operating-model-attestation.yaml").write_text(
        yaml.safe_dump(record, sort_keys=False), encoding="utf-8"
    )
    report = operating_model_report(tmp_path)
    assert report["human_attestation_complete"] is True
    assert report["reasons"] == []

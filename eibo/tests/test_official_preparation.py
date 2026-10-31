from __future__ import annotations

from pathlib import Path

import pytest

from eibo.artifacts import load_battery, load_manifest, load_scientific_artifact_registry, load_yaml
from eibo.errors import ValidationError
from eibo.util import sha256_file

ROOT = Path(__file__).parents[1]
PACK = ROOT / "operations/official-four-provider"
PROTOCOL = ROOT / "protocol/amendments/EIBO-PA-003-four-provider-solo.draft.md"


@pytest.mark.parametrize(
    "filename",
    ["scope-01.proposal.yaml", "scientific-design.draft.yaml", "runtime-lock.template.yaml"],
)
def test_proposals_and_runtime_template_are_not_execution_authority(filename: str) -> None:
    value = load_yaml(PACK / filename)
    assert value["execution_permitted"] is False
    assert value.get("approved") is not True
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / filename)


def test_all_legacy_sources_and_exact_frozen_items_remain_independently_locked() -> None:
    design = load_yaml(PACK / "scientific-design.draft.yaml")
    source_paths = set()
    for reference in design["source_artifacts"]:
        path = ROOT / reference["path"]
        assert sha256_file(path) == reference["sha256"]
        source_paths.add(reference["path"])
    assert len(source_paths) == 6
    assert "waves/W01/scientific-manifest-v1.0.yaml" in source_paths
    registry = load_scientific_artifact_registry(ROOT / "protocol/scientific-artifacts.yaml")
    assert len(registry["artifacts"]) == 5
    assert registry["status"] == "FROZEN"
    battery = load_battery(ROOT / "battery/ebb-ja-v1.0.yaml")
    assert len(battery.items) == 70
    # The proposed delta must reference the instrument, not create another copy.
    text = PROTOCOL.read_text(encoding="utf-8")
    assert not any(item.prompt in text for item in battery.items)


def test_scope_keeps_new_baseline_roles_lineage_and_legacy_holds_separate() -> None:
    scope = load_yaml(PACK / "scope-01.proposal.yaml")["scope"]
    assert scope["new_prospective_baseline"] is True
    assert scope["wave_id_proposal"] == "EIBO-F01"
    assert scope["closed_primary"] == ["M01", "M02", "M03"]
    assert scope["native_separate_mirror"] == ["M05"]
    assert scope["excluded_series"] == {"M04": "NOT_RUN_COST_CONSTRAINT"}
    for field in (
        "legacy_W01_renamed_or_reused",
        "legacy_W01_execution_permitted",
        "xai_requests_permitted",
        "permanent_registry_changed",
        "pool_NATIVE_with_CLOSED",
        "W0_data_may_be_promoted",
    ):
        assert scope[field] is False
    series = load_yaml(ROOT / "registry/model-series.yaml")["series"]
    assert [row["series_id"] for row in series] == ["M01", "M02", "M03", "M04", "M05"]
    claude = next(row for row in series if row["series_id"] == "M02")
    assert claude["permanent_mibo_lineage_id"] == "MIBO-SL-002"
    assert claude["permanent_mibo_lineage_label"] == "Claude"


def test_solo_coding_is_human_primary_without_invented_reliability_or_qa() -> None:
    coding = load_yaml(PACK / "scientific-design.draft.yaml")["coding"]
    assert coding["proposed_primary_coder_type"] == "HUMAN"
    assert coding["proposed_primary_coder_count"] == 1
    assert coding["masked_export_required"] is True
    assert coding["unmasking_incidents_must_be_recorded"] is True
    for field in (
        "ai_secondary_enabled",
        "two_human_inter_rater_reliability_claimed",
        "perfect_blinding_claimed",
        "response_text_edited_to_hide_identity",
        "legacy_reliability_pilot_claimed_satisfied",
        "coding_QA_plan_approved",
        "agreement_or_correctness_guarantee_claimed",
    ):
        assert coding[field] is False
    assert coding["coding_QA_method"] is None
    assert coding["audit_sample_size"] is None


def test_volume_and_timing_are_proposals_not_silently_approved() -> None:
    design = load_yaml(PACK / "scientific-design.draft.yaml")
    rep = design["replication"]
    assert rep["approved_k"] is None
    assert rep["inherited_proposal_k"] == 10
    assert rep["proposed_counts"] == {"CLOSED": 2100, "NATIVE": 700, "total": 2800}
    assert rep["frozen_items"] * 4 * rep["inherited_proposal_k"] == 2800
    timing = design["synchronization"]
    assert timing["at_65_second_gap_minimum_span_seconds"] == (700 - 1) * 65
    assert timing["at_65_second_gap_minimum_span_seconds"] > 12 * 3600
    assert timing["historical_12h_target_feasible_at_that_gap"] is False
    assert timing["future_capacity_verified"] is False
    assert timing["target_window_hours"] is timing["hard_window_hours"] is None
    assert design["wave_id"] is None


def test_w0_profile_and_candidates_are_not_automatic_official_locks() -> None:
    value = load_yaml(PACK / "scientific-design.draft.yaml")["provider_preparation"]
    assert value["current_availability_assumed"] is False
    assert value["exact_official_models"] is value["official_request_profiles"] is None
    assert value["M05_official_surface_approved"] is False
    assert value["W0_profile_may_authorize_official_use"] is False
    assert value["legacy_Sonar_fallback_permitted"] is False
    assert value["legacy_behavioral_equivalence_claimed"] is False
    assert value["M02_permanent_lineage"] == {"id": "MIBO-SL-002", "label": "Claude"}


def test_runtime_template_has_no_final_lock_budget_or_launch_approval() -> None:
    runtime = load_yaml(PACK / "runtime-lock.template.yaml")
    open_fields = (
        "wave_id",
        "official_longitudinal_data",
        "scientific_protocol_path",
        "scientific_protocol_sha256",
        "scientific_design_sha256",
        "model_lock_path",
        "model_lock_sha256",
        "provider_profile_lock_path",
        "schedule_path",
        "schedule_sha256",
        "schedule_seed",
        "observer_site_lock",
        "governance_records",
        "request_budget",
        "technical_attempt_budget",
        "financial_budget",
        "explicit_launch_authority",
        "locked_at_utc",
    )
    assert all(runtime[field] is None for field in open_fields)
    assert runtime["field_window"]["start"] is runtime["field_window"]["end"] is None
    assert all(runtime["prohibitions"].values())
    assert not list(PACK.glob("**/model-lock.json"))
    assert not list(PACK.glob("**/schedule.json"))
    assert not any(load_yaml(PACK / "scientific-design.draft.yaml")["readiness"].values())


def test_decisions_are_sequential_and_governance_is_not_inferred_or_self_approved() -> None:
    queue = load_yaml(PACK / "approval-queue.yaml")
    assert queue["ask_one_decision_at_a_time"] is True
    assert queue["current_step"] == 1
    assert [step["order"] for step in queue["steps"]] == list(range(1, 12))
    assert len({step["id"] for step in queue["steps"]}) == 11
    assert all(step["status"] == "PENDING" for step in queue["steps"])
    assert queue["prior_W0_approvals_auto_extended"] is False
    assert queue["human_decision_may_be_inferred_from_preparation_request"] is False
    assert queue["agent_approval_permitted"] is queue["launch"]["authorized"] is False
    governance = load_yaml(PACK / "governance.template.yaml")
    assert governance["agent_approval_permitted"] is False
    assert governance["prior_W0_approval_is_sufficient"] is False
    assert set(governance["records"]) == {
        "protocol_owner",
        "terms_review",
        "ethics_or_governance_determination",
    }
    for record in governance["records"].values():
        assert record["status"] == "PENDING"
        assert record["human_attestation"] is False
        assert record["determination"] is record["decided_at"] is record["rationale"] is None
        assert not any(record["decided_by"].values())

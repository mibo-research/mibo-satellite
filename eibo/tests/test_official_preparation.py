from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
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


def test_explicit_scope_adoption_does_not_approve_other_decisions() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    assert progress["current_step"] == 12
    assert progress["next_decision_id"] == "offline_full_wave_capacity_verification"
    assert progress["execution_permitted"] is False
    adopted = progress["scope_adoption"]
    assert adopted["decision"] == "EXPLICIT_HUMAN_OPTION_A_BASIC_SCOPE_ONLY"
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["exact_human_message_time_assumed"] is False
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert len(adopted["receipt_file_sha256"]) == len(adopted["receipt_sha256"]) == 64
    assert (
        progress["other_decisions"]["exact_model_and_provider_profile_runtime_locks"] == "PENDING"
    )
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"
    assert all(v in {"PENDING", "NOT_AUTHORIZED"} for v in progress["other_decisions"].values())
    assert all(progress["prohibitions"].values())


def test_historical_coding_qa_proposal_is_preserved_and_not_runnable() -> None:
    proposal = load_yaml(PACK / "coding-qa-02.proposal.yaml")
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["other_authority"].values())
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "coding-qa-02.proposal.yaml")


def test_repeat_audit_preserves_a_preregistered_masked_same_human_comparison() -> None:
    proposal = load_yaml(PACK / "coding-qa-02.proposal.yaml")
    audit = proposal["proposed_repeat_audit"]
    assert audit["target_observations_per_series_item"] == 1
    assert audit["series"] == ["M01", "M02", "M03", "M05"]
    assert audit["target_selected_count"] == 4 * audit["item_count"] == 280
    assert audit["minimum_days_after_first_pass_lock"] == 7
    assert audit["selection_rule_and_seed_locked_before_wave_execution"] is True
    for field in (
        "sample_locked_before_primary_coding",
        "previous_codes_hidden",
        "same_human_coder",
        "new_blind_identifiers_and_random_order",
        "same_Frozen_anchors_and_coding_fields",
        "both_passes_preserved_with_timestamps_and_hashes",
    ):
        assert audit[field] is True
    assert audit["seed"] is None
    assert (
        audit["visible_response_text_modified"] is audit["recoding_may_call_provider_API"] is False
    )


def test_audit_missing_nr_and_disagreement_cannot_be_selectively_replaced() -> None:
    proposal = load_yaml(PACK / "coding-qa-02.proposal.yaml")
    audit, review = proposal["proposed_repeat_audit"], proposal["review"]
    assert audit["exclude_or_reselect_based_on_response_or_score"] is False
    assert audit["technical_missing_remains_missing_no_replacement"] is True
    assert audit["NR_outcomes_preserved_not_forced_to_zero"] is True
    assert review["unresolved_flags_block_coding_QA_procedure_closeout"] is True
    for field in (
        "automatically_choose_higher_or_average_scores",
        "first_pass_score_overwritten",
        "correction_selection_based_on_provider_or_desired_result",
        "post_review_agreement_may_replace_original_agreement_report",
    ):
        assert review[field] is False


def test_single_coder_audit_claims_neither_validity_nor_two_rater_reliability() -> None:
    proposal = load_yaml(PACK / "coding-qa-02.proposal.yaml")
    assert proposal["primary_coding"]["coder_count"] == 1
    assert proposal["primary_coding"]["coder_type"] == "HUMAN"
    assert proposal["primary_coding"]["AI_secondary_enabled"] is False
    assert proposal["primary_coding"]["automated_primary_scoring"] is False
    assert proposal["reporting"]["precision_or_power_guaranteed_by_280"] is False
    assert proposal["reporting"]["aggregate_agreement_pass_threshold"] is None
    for field in (
        "memory_or_identity_recognition_eliminated",
        "independent_second_rater_created",
        "two_human_inter_rater_reliability_claimed",
        "coding_validity_or_correctness_guaranteed",
        "legacy_150_or_200_response_two_coder_pilot_satisfied",
        "agreement_results_already_observed",
        "observed_reliability_claimed",
    ):
        assert proposal["limits"][field] is False
    assert proposal["automated_checks"]["may_assign_or_change_substantive_scores"] is False
    assert proposal["automated_checks"]["may_claim_coding_correctness"] is False


def test_audit_example_does_not_approve_replication_or_workload() -> None:
    proposal = load_yaml(PACK / "coding-qa-02.proposal.yaml")
    example = proposal["example_only_not_a_volume_approval"]
    assert example["primary_records"] == 4 * 70 * example["if_primary_replication_k"]
    assert example["selected_audit_records"] == 280
    assert example["maximum_first_plus_repeat_coding_records"] == 3080
    assert proposal["other_authority"]["primary_replication_count_or_workload_approved"] is False


def test_qa_method_adoption_is_attributed_separately_from_later_replication_adoption() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    adopted = progress["coding_QA_adoption"]
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert adopted["method_adopted_but_not_implemented_or_completed"] is True
    assert adopted["selected_audit_target"] == 280
    assert adopted["minimum_days_after_first_pass_lock"] == 7
    assert adopted["exact_human_message_time_assumed"] is False
    assert len(adopted["receipt_file_sha256"]) == len(adopted["receipt_sha256"]) == 64
    assert (
        progress["other_decisions"]["exact_model_and_provider_profile_runtime_locks"] == "PENDING"
    )
    assert progress["execution_permitted"] is False


@pytest.mark.parametrize("choice, expected_k", [("A", 10), ("B", 5), ("C", 3)])
def test_replication_options_count_primary_and_recoding_separately(choice, expected_k) -> None:
    proposal = load_yaml(PACK / "replication-03.proposal.yaml")
    option = proposal["options"][choice]
    assert option["k"] == expected_k
    assert option["primary_requests_per_series"] == 70 * expected_k
    assert option["CLOSED_primary_requests"] == 3 * 70 * expected_k
    assert option["NATIVE_primary_requests"] == 70 * expected_k
    assert option["total_primary_requests_and_coding_records"] == 4 * 70 * expected_k
    assert option["repeat_coding_target"] == 280
    assert option["maximum_primary_plus_repeat_coding_records"] == 4 * 70 * expected_k + 280
    assert option["audit_fraction"] == pytest.approx(1 / expected_k)
    assert option["per_cell_empirical_frequency_step_percent"] == pytest.approx(100 / expected_k)
    assert (
        option["historical_Google_65_second_gap_minimum_start_span_seconds"]
        == (70 * expected_k - 1) * 65
    )


def test_historical_replication_proposal_stays_nonexecuting_without_budgets_or_power_claims() -> (
    None
):
    proposal = load_yaml(PACK / "replication-03.proposal.yaml")
    assert proposal["recommended_option"] == "A"
    assert proposal["approved_k"] is None
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["other_authority"].values())
    limits = proposal["scientific_limits"]
    for field in (
        "sufficient_power_or_precision_claimed",
        "primary_records_are_independent_human_subjects",
        "empirical_frequency_steps_are_accuracy_or_confidence_bounds",
        "k_changed_after_inspecting_answers",
        "missing_cells_relabelled_or_filled_by_later_recovery",
        "good_answers_selected_from_extra_runs",
        "NATIVE_and_CLOSED_pooled_as_equivalent",
        "legacy_Frozen_k10_or_W01_manifest_modified",
        "Google_lower_bounds_guarantee_completion_within_a_target_window",
    ):
        assert limits[field] is False
    assert limits["replication_temporally_distributed"] is True
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "replication-03.proposal.yaml")


def test_coding_time_examples_are_explicit_assumptions_not_observed_times_or_api_calls() -> None:
    proposal = load_yaml(PACK / "replication-03.proposal.yaml")
    workload = proposal["workload_interpretation"]
    assert workload["time_per_record_measured"] is False
    assert workload["repeat_coding_reuses_existing_answers_without_provider_requests"] is True
    assert workload["discrepancy_review_training_and_breaks_included_in_example"] is False
    for choice, option in proposal["options"].items():
        assert workload["example_total_hours_not_a_schedule_or_observed_timing"][choice] == (
            option["maximum_primary_plus_repeat_coding_records"]
            * workload["example_minutes_per_coding_record_assumption_only"]
            / 60
        )


def test_replication_adoption_does_not_infer_cadence_dates_money_or_api_authority() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    adopted = progress["replication_adoption"]
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["exact_human_message_time_assumed"] is False
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert adopted["selected_k"] == 10
    assert adopted["CLOSED_primary_target"] == 2100
    assert adopted["NATIVE_primary_target"] == 700
    assert adopted["primary_coding_target"] == 2800
    assert adopted["maximum_first_plus_repeat_coding_target"] == 3080
    assert adopted["completed_or_rateable_responses_claimed"] is False
    assert adopted["concrete_dates_or_financial_or_API_authority_inferred"] is False
    assert (
        progress["other_decisions"]["exact_model_and_provider_profile_runtime_locks"] == "PENDING"
    )
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"


@pytest.mark.parametrize("choice, months, waves", [("A", 3, 4), ("B", 1, 12), ("C", 6, 2)])
def test_cadence_options_account_for_fixed_workload_without_creating_dates(choice, months, waves):
    proposal = load_yaml(PACK / "cadence-window-04.proposal.yaml")
    option = proposal["options"][choice]
    assert option["interval_calendar_months"] == months
    assert option["steady_state_waves_per_year_for_accounting_only"] == waves == 12 / months
    assert option["illustrative_annual_coding_hours_not_a_commitment"] == 154 * waves
    assert proposal["fixed_inputs"]["adopted_k"] == 10
    assert proposal["fixed_inputs"]["primary_records_per_wave"] == 2800
    assert proposal["fixed_inputs"]["maximum_coding_records_per_wave"] == 3080
    assert all(v is None for v in proposal["unfilled_runtime_values"].values())


def test_shared_observation_window_never_silently_extends_or_backfills_late_data() -> None:
    proposal = load_yaml(PACK / "cadence-window-04.proposal.yaml")
    window = proposal["common_API_observation_window_proposal"]
    assert window["target_hours_from_shared_anchor"] == 18
    assert window["planned_schedule_span_hours_from_shared_anchor"] == 18
    assert window["hard_hours_from_shared_anchor"] == 24
    assert window["same_fixed_anchor_for_all_four_series"] is True
    assert window["generation_before_shared_anchor"] is False
    assert window["provider_specific_restarting_of_hard_window"] is False
    assert window["new_generation_sends_or_retries_at_or_after_hard_deadline"] is False
    assert window["silent_extension_to_finish_missing_cells"] is False
    assert window["late_or_recovery_data_may_replace_primary_missing_cells"] is False
    assert window["in_flight_response_preservation_required"] is True
    assert "LATE_NONPRIMARY" in window["response_received_after_hard_deadline"]
    assert window["response_after_target_but_within_hard_window"] == (
        "RETAIN_PRIMARY_WITH_TARGET_OVERRUN_FLAG"
    )
    assert window["legacy_W01_12h_target_or_24h_hard_window_changed"] is False
    capacity = proposal["capacity_gate"]
    assert capacity["historical_gap_minimum_first_to_last_start_span_seconds"] == 699 * 65
    assert capacity["full_wave_capacity_dry_run_evidence_required_before_launch"] is True
    assert capacity["extrapolation_from_28_response_rehearsal_is_sufficient"] is False
    assert (
        capacity["separate_planned_target_and_hard_deadline_scheduler_support_already_verified"]
        is False
    )
    assert capacity["if_not_feasible_or_not_verified"].startswith("FAIL_CLOSED")


def test_frequency_policy_is_not_a_coding_deadline_automation_or_launch_permission() -> None:
    proposal = load_yaml(PACK / "cadence-window-04.proposal.yaml")
    assert proposal["recommended_option"] == "A"
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["other_authority"].values())
    recurrence = proposal["coding_and_recurrence"]
    assert recurrence["human_coding_deadline_is_API_24h_window"] is False
    assert recurrence["repeat_coding_waits_at_least_7_days_after_first_pass_lock"] is True
    assert recurrence["automatic_next_wave_launch_from_cadence_alone"] is False
    assert recurrence["annual_accounting_numbers_authorize_multiple_waves_or_spending"] is False
    assert (
        recurrence["new_wave_requires_scoped_locks_governance_capacity_and_launch_authority"]
        is True
    )
    assert proposal["capacity_gate"]["new_live_capacity_experiments_authorized"] is False
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "cadence-window-04.proposal.yaml")


def test_contextual_yes_adopts_only_the_immediately_preceding_cadence_policy() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    adopted = progress["cadence_window_adoption"]
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert adopted["interval_calendar_months"] == 3
    assert adopted["target_hours"] == adopted["planned_schedule_span_hours"] == 18
    assert adopted["hard_hours"] == 24
    assert adopted["capacity_and_scheduler_support_verified"] is False
    assert adopted["concrete_dates_or_financial_or_API_authority_inferred"] is False
    assert adopted["exact_human_message_time_assumed"] is False
    assert (
        progress["other_decisions"]["exact_model_and_provider_profile_runtime_locks"] == "PENDING"
    )
    assert progress["execution_permitted"] is False


def test_initial_provider_candidates_preserve_w0_identity_without_creating_locks() -> None:
    proposal = load_yaml(PACK / "provider-policy-05.proposal.yaml")
    candidates = {row["series_id"]: row for row in proposal["initial_candidates"]}
    assert {sid: row["candidate_exact_id"] for sid, row in candidates.items()} == {
        "M01": "gpt-5.6-sol",
        "M02": "claude-opus-5",
        "M03": "gemini-3.6-flash",
        "M05": "perplexity/sonar",
    }
    assert {sid: row["environment"] for sid, row in candidates.items()} == {
        "M01": "CLOSED",
        "M02": "CLOSED",
        "M03": "CLOSED",
        "M05": "NATIVE",
    }
    assert all(row["output_cap_value"] == 8192 for row in candidates.values())
    assert "M04" not in candidates
    policy = proposal["selection_policy"]
    assert policy["exact_ids_are_per_wave_runtime_values_not_scientific_manifest_fields"] is True
    assert policy["future_waves_require_fresh_human_model_resolution"] is True
    assert policy["initial_candidates_are_permanent_or_annual_model_locks"] is False
    assert policy["latest_or_more_capable_models_selected_automatically"] is False
    assert policy["unavailable_model_substituted_automatically"] is False
    assert policy["account_access_or_current_live_identity_assumed"] is False


def test_claude_candidate_retains_lineage_and_shared_budget_limits_without_override() -> None:
    proposal = load_yaml(PACK / "provider-policy-05.proposal.yaml")
    claude = next(row for row in proposal["initial_candidates"] if row["series_id"] == "M02")
    assert claude["permanent_mibo_lineage_id"] == "MIBO-SL-002"
    assert claude["permanent_mibo_lineage_label"] == "Claude"
    assert claude["output_cap_parameter"] == "max_tokens"
    assert claude["thinking_shares_max_tokens_budget"] is True
    assert claude["serving_infrastructure_behavioral_variation_possible"] is True
    assert claude["effort_or_thinking_override_requested"] is False
    assert claude["automatic_family_or_tier_switch_permitted"] is False


def test_m05_official_surface_is_proposed_separately_without_relabelling_w0() -> None:
    proposal = load_yaml(PACK / "provider-policy-05.proposal.yaml")
    m05 = next(row for row in proposal["initial_candidates"] if row["series_id"] == "M05")
    assert m05["endpoint"] == "https://api.perplexity.ai/v1/agent"
    assert m05["allowed_tools"] == [{"type": "web_search"}]
    assert m05["search_invocation_forced_by_researcher"] is False
    assert m05["W0_only_profile_relabelled_or_reused_as_official"] is False
    assert m05["new_scoped_official_profile_and_hash_required"] is True
    assert m05["official_CLOSED_eligibility_claimed"] is False
    assert m05["legacy_Sonar_behavioral_equivalence_claimed"] is False
    omitted = proposal["M05_omitted_fields_policy"]
    assert {"models", "effort", "profile", "instructions", "previous_response_id"} <= set(
        omitted["fields"]
    )
    assert omitted["legacy_disable_search_sent"] is False
    assert omitted["third_party_router_or_legacy_Sonar_fallback_allowed"] is False
    assert omitted["additional_official_no_search_diagnostic_proposed"] is False


def test_provider_proposal_is_guidance_not_api_configuration_or_credential_authority() -> None:
    proposal = load_yaml(PACK / "provider-policy-05.proposal.yaml")
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["remaining_operational_gates"].values())
    assert not any(proposal["other_authority"].values())
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "provider-policy-05.proposal.yaml")


def test_common_candidate_conditions_do_not_override_native_behavior_or_retry_science() -> None:
    common = load_yaml(PACK / "provider-policy-05.proposal.yaml")["common_request_policy"]
    assert common["first_party_provider_API_only"] is True
    assert common["independent_exact_Frozen_prompt_single_user_turn"] is True
    for field in (
        "researcher_system_developer_or_extra_instruction",
        "previous_response_or_conversation_linkage",
        "history_files_RAG_or_memory_supplied",
        "tools_or_search_in_CLOSED",
        "optional_sampling_or_reasoning_or_effort_overrides",
        "forced_language_or_structured_output",
        "streaming",
        "background_or_automatic_continuation_or_tool_loop_by_researcher",
        "sdk_auto_retries_or_auto_model_switching",
        "visible_8192_token_budget_guaranteed",
        "truncation_refusal_or_poor_answer_retryable",
        "provider_controlled_system_layers_claimed_absent",
        "provider_internal_serving_routes_or_regions_claimed_transparent",
        "consumer_UI_equivalence_assumed_or_required",
    ):
        assert common[field] is False


def test_provider_policy_adoption_is_human_attributed_not_an_exact_runtime_lock() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    adopted = progress["provider_policy_adoption"]
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["exact_human_message_time_assumed"] is False
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert adopted["proposal_sha256"] == (
        "63713184d9a585b46fb97054def76ba2232ecacf3069f56114d519e3fa99b20c"
    )
    assert len(adopted["receipt_sha256"]) == len(adopted["receipt_file_sha256"]) == 64
    proposal = load_yaml(ROOT / adopted["proposal_path"])
    assert adopted["initial_candidates"] == {
        row["series_id"]: row["candidate_exact_id"] for row in proposal["initial_candidates"]
    }
    assert adopted["M05_new_official_scope_profile_policy_adopted"] is True
    assert adopted["fresh_per_wave_human_model_resolution_required"] is True
    assert adopted["original_proposal_kept_unchanged"] is True
    assert adopted["models_or_profiles_are_final_runtime_locks"] is False
    assert adopted["account_access_metadata_or_payload_audit_verified"] is False
    assert adopted["credential_financial_date_governance_or_API_authority_inferred"] is False
    sequence = progress["confirmation_sequence"]
    assert sequence["budget_question_moved_before_governance_at_explicit_human_request"] is True
    assert sequence["governance_checks_skipped_or_approved"] is False
    assert progress["other_decisions"]["budget_enforcement_and_safe_cost_bound"] == "PENDING"


def test_budget_proposal_is_one_initial_wave_not_annual_spending_or_launch_authority() -> None:
    proposal = load_yaml(PACK / "budget-limits-06.proposal.yaml")
    scope = proposal["scope"]
    assert scope["number_of_waves_covered"] == 1
    assert scope["series"] == ["M01", "M02", "M03", "M05"]
    assert scope["primary_observation_cells"] == 4 * scope["cells_per_series"] == 2800
    for field in (
        "future_quarterly_waves_or_annual_spending_authorized",
        "xai_or_W01_or_Q3_included",
        "additional_official_no_search_diagnostic",
        "recoding_280_requires_new_API_generation",
    ):
        assert scope[field] is False
    assert scope["additional_qualification_or_scientific_generations"] == 0
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["remaining_gates"].values())
    assert not any(proposal["other_authority"].values())
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "budget-limits-06.proposal.yaml")


def test_budget_output_arithmetic_is_reproducible_not_a_total_invoice_bound() -> None:
    proposal = load_yaml(PACK / "budget-limits-06.proposal.yaml")
    prices = proposal["public_pricing_reference"]
    calc = prices["illustrative_output_only_calculation"]
    rates = prices["rates_USD_per_million_tokens"]
    outputs = {}
    for sid, row in rates.items():
        rate = Decimal(row.get("output", row.get("output_including_thinking")))
        outputs[sid] = Decimal(700) * Decimal(8192) * rate / Decimal(1_000_000)
    assert outputs == {
        sid: Decimal(amount) for sid, amount in calc["primary_output_USD_by_series"].items()
    }
    assert sum(outputs.values()) == Decimal(calc["primary_output_USD_total"]) == Decimal("293.888")
    assert sum(outputs.values()) * Decimal("1.1") == Decimal(
        calc["at_770_attempts_per_series_output_USD_total"]
    )
    for field in (
        "input_search_internal_intermediate_tokens_tax_and_fees_included",
        "actual_usage_or_invoice_forecast_claimed",
        "safe_total_bound_or_minimum_cost_claimed",
    ):
        assert calc[field] is False
    assert rates["M03"]["published_2027_output_including_thinking"] == "7.50"
    assert rates["M05"]["standard_web_search_USD_per_invocation"] == "0.0025"
    assert rates["M05"]["one_search_per_POST_assumed"] is False


def test_money_gate_requires_unknown_cost_and_inflight_reservations_to_fail_closed() -> None:
    money = load_yaml(PACK / "budget-limits-06.proposal.yaml")["financial_policy"]
    assert money["currency"] == "USD"
    assert Decimal(money["proposed_API_charge_ceiling"]) == Decimal("500")
    assert Decimal(money["warning_at_committed_charge"]) == Decimal("400")
    assert "UNRECONCILED" in money["accounting_basis"]
    assert "ALL_IN_FLIGHT" in money["accounting_basis"]
    assert money["stop_before_next_send_if_cost_bound_unknown_or_would_exceed_ceiling"] is True
    assert money["reserve_for_possible_provider_processing_and_failed_attempt_charges"] is True
    assert money["before_launch_fresh_first_party_rate_card_and_safe_cost_bound_required"] is True
    for field in (
        "invoice_total_or_JPY_ceiling_guaranteed",
        "provider_account_hard_cap_or_realtime_billing_guaranteed",
        "invoice_final_amount_guaranteed_by_this_proposal",
        "automatic_topup_tier_upgrade_or_purchase_authorized",
        "automatic_budget_increase_or_transfer_from_other_projects",
        "cheaper_model_or_smaller_output_cap_or_sample_on_budget_exhaustion",
        "missing_usage_or_timeout_assumed_free",
        "price_cache_discount_or_free_tier_savings_assumed",
        "M05_internal_search_and_intermediate_tokens_safely_bounded",
        "safe_reservation_and_admission_controller_implemented_and_tested",
    ):
        assert money[field] is False
    assert money["if_safe_cost_bound_unavailable"].startswith("BLOCK_BEFORE_LAUNCH")
    assert {"provider_search_and_internal_tool_charges", "technical_attempts"} <= set(
        money["includes"]
    )
    assert {"tax", "currency_conversion_and_card_fees"} <= set(money["excludes"])


def test_request_ceilings_include_failures_but_cannot_buy_extra_observations() -> None:
    request = load_yaml(PACK / "budget-limits-06.proposal.yaml")["request_policy"]
    assert request["first_attempt_generation_target"] == 2800
    assert request["maximum_attempts_per_cell_including_first"] == 2
    assert request["maximum_extra_technical_attempts_total"] == 4 * 70 == 280
    assert request["maximum_extra_technical_attempts_per_series"] == 70
    assert request["maximum_generation_POST_attempts_total"] == 2800 + 280 == 4 * 770
    assert request["maximum_generation_POST_attempts_per_series"] == 770
    assert request["maximum_metadata_GET_attempts_total"] == 4 * 3 == 12
    assert request["maximum_metadata_GET_attempts_per_series"] == 3
    assert request["maximum_researcher_HTTP_attempts_total"] == 3080 + 12
    for field in (
        "metadata_counts_include_failed_attempts",
        "generation_counts_include_429_failed_and_ambiguous_dispatches",
        "admission_receipt_and_budget_reservation_before_dispatch",
        "completed_refused_blocked_truncated_empty_or_poor_answers_consume_cell",
        "internal_provider_tool_charges_must_be_accounted_separately",
        "global_request_money_and_time_ceiling_all_must_pass",
    ):
        assert request[field] is True
    for field in (
        "internal_provider_tool_calls_are_covered_by_researcher_POST_count",
        "counting_API_calls_or_additional_network_calls_authorized",
        "retry_capacity_may_be_used_for_extra_cells_or_replacements",
        "one_provider_failure_may_replace_another_series",
        "SDK_automatic_retries_or_continuations_or_fallback",
    ):
        assert request[field] is False


def test_bounded_technical_retries_never_retry_science_or_unknown_after_send_outcomes() -> None:
    retry = load_yaml(PACK / "budget-limits-06.proposal.yaml")["technical_retry_policy"]
    assert retry["explicit_technical_failures_only"] is True
    assert retry["scientific_output_or_recoverable_final_response_precludes_retry"] is True
    assert retry["allowed_HTTP_statuses_if_no_scientific_response"] == [429, 500, 502, 503, 504]
    for field in (
        "refusal_safety_block_hallucination_quality_empty_or_cap_stop_retryable",
        "successful_response_with_missing_identity_or_metadata_retryable",
        "identity_mismatch_or_profile_violation_retryable",
        "ambiguous_after_send_timeout_or_connection_loss_auto_retryable",
        "current_quota_verified_from_this_policy",
    ):
        assert retry[field] is False
    assert "HOLD_CELL_FOR_HUMAN_REVIEW" in retry["ambiguous_attempt_action"]
    assert retry["minimum_technical_retry_delay_seconds"] == 120
    assert retry["Google_minimum_generation_start_gap_seconds"] == 65
    assert retry["honor_longer_retry_after_and_google_retryDelay"] is True
    assert retry["all_attempts_receipts_and_original_raw_preserved"] is True


def test_budget_early_stop_does_not_change_window_or_replace_primary_missing_cells() -> None:
    timing = load_yaml(PACK / "budget-limits-06.proposal.yaml")["time_and_missingness_policy"]
    assert timing["target_hours"] == timing["planned_schedule_span_hours"] == 18
    assert timing["hard_hours"] == 24
    for field in (
        "one_shared_anchor_for_all_series",
        "early_stop_for_budget_or_attempts_must_be_reported_as_missing",
        "late_responses_preserved_with_nonprimary_flag",
    ):
        assert timing[field] is True
    for field in (
        "new_sends_or_retries_at_or_after_hard_deadline",
        "missing_cells_may_be_filled_by_recovery_or_later_wave",
        "smaller_success_only_subset_may_be_called_complete",
        "actual_dates_or_execution_authority_set",
        "this_proposal_guarantees_2800_responses_or_window_feasibility",
    ):
        assert timing[field] is False


def test_budget_adoption_is_one_wave_policy_not_governance_or_dispatch_permission() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    adopted = progress["budget_limits_adoption"]
    proposal = load_yaml(ROOT / adopted["proposal_path"])
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert adopted["proposal_sha256"] == (
        "e51a951ee8ea9e3e332f5e7f7084f27aa9afeb19d13d45118589da0d9a504f08"
    )
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["exact_human_message_time_assumed"] is False
    assert adopted["original_proposal_kept_unchanged"] is True
    assert len(adopted["receipt_sha256"]) == len(adopted["receipt_file_sha256"]) == 64
    assert adopted["number_of_waves_covered"] == 1
    assert adopted["currency"] == "USD"
    assert (
        adopted["API_charge_ceiling"]
        == proposal["financial_policy"]["proposed_API_charge_ceiling"]
        == "500.00"
    )
    assert adopted["warning_at_committed_charge"] == "400.00"
    assert adopted["tax_currency_conversion_and_card_fees_excluded"] is True
    assert adopted["primary_observation_cells"] == 2800
    for field in (
        "maximum_extra_technical_attempts_total",
        "maximum_extra_technical_attempts_per_series",
        "maximum_attempts_per_cell_including_first",
        "maximum_generation_POST_attempts_total",
        "maximum_generation_POST_attempts_per_series",
        "maximum_metadata_GET_attempts_total",
        "maximum_metadata_GET_attempts_per_series",
        "maximum_researcher_HTTP_attempts_total",
    ):
        assert adopted[field] == proposal["request_policy"][field]
    assert adopted["safe_cost_bound_and_budget_controller_verified"] is False
    assert adopted["dates_governance_freeze_or_API_authority_inferred"] is False
    assert progress["other_decisions"]["named_protocol_owner_final_freeze"] == "PENDING"
    assert progress["other_decisions"]["provider_terms_review"] == "PENDING"
    assert progress["other_decisions"]["ethics_or_governance_determination"] == "PENDING"
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"


def test_owner_role_proposal_requires_new_human_acceptance_not_inherited_w0_authority() -> None:
    proposal = load_yaml(PACK / "protocol-owner-07.proposal.yaml")
    role = proposal["owner_role_proposal"]
    assert role["responsible_human_count"] == role["continuing_human_primary_coder_count"] == 1
    assert role["requires_explicit_current_scope_human_acceptance"] is True
    assert role["old_W0_or_operating_attestation_is_new_scope_approval"] is False
    assert role["affiliation_transferred_as_current_or_institutional_authority"] is False
    assert role["agent_may_make_human_governance_or_primary_coding_decisions"] is False
    sources = proposal["prior_records_reference_only"]
    for reference in sources:
        assert sha256_file(ROOT / reference["path"]) == reference["sha256"]
    owner_reference = next(
        row for row in sources if row["path"].endswith("records/protocol-owner.yaml")
    )
    historical_owner = load_yaml(ROOT / owner_reference["path"])
    assert role["candidate_human_name_from_prior_record"] == historical_owner["decided_by"]["name"]
    assert proposal["scope"]["legacy_W01_or_W0_governance_reapproved_by_this_proposal"] is False
    assert proposal["scope"]["original_Frozen_artifacts_or_historical_raw_modified"] is False


def test_new_governance_template_stays_pending_and_agent_cannot_finalize_records() -> None:
    proposal = load_yaml(PACK / "protocol-owner-07.proposal.yaml")
    reference = proposal["untouched_new_scope_governance_template"]
    assert sha256_file(ROOT / reference["path"]) == reference["sha256"]
    assert reference["record_statuses_remain"] == "PENDING"
    assert reference["human_attestations_remain"] is False
    governance = load_yaml(ROOT / reference["path"])
    for record in governance["records"].values():
        assert record["status"] == "PENDING"
        assert record["determination"] is record["decided_at"] is record["rationale"] is None
        assert not any(record["decided_by"].values())
        assert record["human_attestation"] is False
    final = proposal["final_approval_process_proposal"]
    assert final["agent_may_fill_decision_fields_or_set_FINAL_or_human_attestation"] is False
    assert final["agent_transcription_receipt_is_a_FINAL_governance_record"] is False
    assert final["current_recording_timestamp_is_human_decision_timestamp"] is False
    assert final["historical_W0_record_or_budget_approval_may_complete_governance"] is False
    assert final["missing_human_fields_or_required_institutional_steps_action"] == "BLOCK"
    assert set(final["final_human_record_requires"]) == {
        "status",
        "determination",
        "decided_by_name_and_role",
        "actual_decision_time_with_timezone",
        "rationale",
        "evidence_references",
        "scope_version_and_hash",
    }


def test_final_protocol_review_is_separate_from_role_terms_ethics_and_launch() -> None:
    proposal = load_yaml(PACK / "protocol-owner-07.proposal.yaml")
    final = proposal["final_approval_process_proposal"]
    for field in (
        "complete_prospective_protocol_text_and_version_presented_before_final_decision",
        "exact_scientific_packet_file_hashes_required_for_final_decision",
        "adopted_decision_receipts_must_be_reconciled_without_rewriting_old_proposals",
        "pending_scientific_methods_cannot_be_approved_by_generic_role_acceptance",
        "exact_models_schedule_seed_site_and_execution_dates_are_separate_runtime_values",
        "scope_specific_terms_and_ethics_records_required_before_launch",
        "institutional_review_applicability_requires_explicit_human_determination",
        "separate_explicit_launch_after_all_operational_gates_required",
    ):
        assert final[field] is True
    for field in (
        "this_role_choice_is_final_protocol_approval_or_freeze",
        "affiliation_or_personal_owner_acceptance_is_institutional_approval",
        "NOT_APPLICABLE_or_NOT_HUMAN_SUBJECTS_auto_assumed",
        "final_protocol_approval_is_launch_authority",
    ):
        assert final[field] is False
    assert all(value == "PENDING" for value in proposal["next_separate_confirmations"].values())
    assert "PRESERVE_PRIOR_VERSION" in final["post_freeze_change_rule"]


def test_owner_proposal_and_budget_receipt_do_not_make_any_future_wave_runnable() -> None:
    proposal = load_yaml(PACK / "protocol-owner-07.proposal.yaml")
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["remaining_gates"].values())
    assert not any(proposal["other_authority"].values())
    assert load_yaml(PACK / "decision-progress.yaml")["execution_permitted"] is False
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "protocol-owner-07.proposal.yaml")


def test_human_owner_role_adoption_does_not_approve_protocol_or_terms() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    role = progress["protocol_owner_role_adoption"]
    assert role["actor_attribution"] == "CURRENT_CHAT_USER"
    assert role["protocol_and_operations_responsible_actor"] == "CURRENT_CHAT_USER"
    assert role["final_complete_protocol_approver_actor"] == "CURRENT_CHAT_USER"
    assert role["responsible_human_count"] == 1
    assert role["agent_is_transcriber_not_approver"] is True
    assert role["original_proposal_kept_unchanged"] is True
    assert role["proposal_sha256"] == sha256_file(ROOT / role["proposal_path"])
    assert role["proposal_sha256"] == (
        "0c6fbc4d19afc38822f3ab0bcb91bed7abcebbf46a955627ac23991069de0876"
    )
    for field in (
        "current_affiliation_or_institutional_authority_inferred",
        "complete_protocol_final_approval_or_freeze_inferred",
        "final_human_governance_records_complete",
        "terms_ethics_dates_or_API_authority_inferred",
        "exact_human_message_time_assumed",
    ):
        assert role[field] is False
    assert progress["other_decisions"]["provider_terms_review"] == "PENDING"
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"


def test_public_terms_sources_do_not_clear_any_provider_or_invent_account_contracts() -> None:
    proposal = load_yaml(PACK / "terms-review-08.proposal.yaml")
    providers = proposal["providers"]
    assert set(providers) == {"M01", "M02", "M03", "M05"}
    expected = load_yaml(PACK / "decision-progress.yaml")["provider_policy_adoption"][
        "initial_candidates"
    ]
    for sid, provider in providers.items():
        assert provider["requested_candidate"] == expected[sid]
        assert provider["gate"] == "BLOCKED_PENDING_SCOPE_SPECIFIC_HUMAN_TERMS_DETERMINATION"
        assert provider["unresolved"]
        assert provider["sources"]
        assert all(row["url"].startswith("https://") for row in provider["sources"])
    source = proposal["source_method"]
    assert source["source_facts_are_separate_from_reviewer_inferences"] is True
    assert source["update_and_actual_applicability_review_required_before_each_wave"] is True
    assert source["authenticated_account_contracts_or_orders_inspected"] is False
    assert source["page_bytes_or_contract_snapshot_hash_claimed"] is False
    assert source["retrieval_date_equals_applicable_effective_date"] is False


def test_future_dated_policies_cannot_be_treated_as_current_terms_on_review_date() -> None:
    proposal = load_yaml(PACK / "terms-review-08.proposal.yaml")
    review_date = proposal["reviewed_on_jst"]
    future_sources = []
    for provider in proposal["providers"].values():
        for source in provider["sources"]:
            effective = source.get("displayed_effective_date")
            if effective and effective > review_date:
                future_sources.append(source)
                assert source["treated_as_current_on_review_date"] is False
    assert {row["displayed_effective_date"] for row in future_sources} == {
        "2026-11-12",
        "2026-11-20",
    }
    anthropic = proposal["providers"]["M02"]
    assert anthropic["applicable_current_AUP_version_verified"] is False
    assert any(
        row["url"].endswith("/usage-policies/revisions/2025-10-29/")
        for row in proposal["providers"]["M01"]["sources"]
    )


def test_frozen_item_aup_flags_are_not_rewrites_exclusions_or_research_exemptions() -> None:
    proposal = load_yaml(PACK / "terms-review-08.proposal.yaml")
    screen = proposal["Frozen_battery_policy_screen"]
    assert sha256_file(ROOT / screen["source_path"]) == screen["source_sha256"]
    battery = load_battery(ROOT / screen["source_path"])
    assert screen["items_read"] == len(battery.items) == 70
    assert set(screen["example_ids_for_further_human_AUP_review"]) <= {
        item.item_id for item in battery.items
    }
    assert screen["flagged_IDs_are_not_exhaustive_or_a_finding_of_illegality"] is True
    assert screen["research_purpose_alone_grants_policy_exception"] is False
    assert screen["all_70_items_human_AUP_review_complete"] is False
    assert screen["prompts_or_scoring_anchors_copied_paraphrased_or_changed"] is False
    assert proposal["providers"]["M05"]["scientific_AUP_exception_assumed_automatic"] is False
    text = (PACK / "TERMS-REVIEW-08.md").read_text(encoding="utf-8")
    assert not any(item.prompt in text for item in battery.items)


def test_private_storage_or_owner_acceptance_never_releases_terms_or_design_hold() -> None:
    proposal = load_yaml(PACK / "terms-review-08.proposal.yaml")
    holds = proposal["execution_holds"]
    assert holds["unresolved_scope_terms_action"] == "NO_OFFICIAL_WAVE_START"
    for field in (
        "single_provider_hold_may_silently_reduce_four_provider_design",
        "private_archive_alone_resolves_contract_restrictions",
        "raw_deletion_or_replacement_is_used_to_hide_permission_gap",
        "prior_W0_terms_approval_is_new_scope_approval",
        "owner_role_acceptance_releases_terms_hold",
        "following_ethics_question_releases_terms_hold",
    ):
        assert holds[field] is False
    use = proposal["proposed_use_policy"]
    assert use["first_party_API_four_series_only"] == ["M01", "M02", "M03", "M05"]
    assert "ONLY_AFTER_RIGHTS_AND_RETENTION_CONFIRMED" in use["raw_archive_policy"]
    assert use["retention_or_reproduction_conflict_action"].startswith("BLOCK_BEFORE_LAUNCH")
    assert use["Google_paid_billing_project_status_must_be_confirmed_before_launch"] is True
    assert proposal["providers"]["M03"]["paid_billing_project_verified"] is False
    assert proposal["providers"]["M03"]["Google_Search_grounding_enabled_or_assumed"] is False
    assert proposal["providers"]["M01"]["store_false_equals_zero_provider_retention"] is False
    for field in (
        "real_student_personal_data_or_real_student_grading_decisions",
        "actual_schoolwork_submission_or_competing_model_training",
        "researcher_safety_bypass_or_prompt_injection_or_rate_limit_evasion",
        "Frozen_prompt_rewrite_append_or_item_deletion_to_obtain_permission",
        "selected_items_or_fewer_providers_may_replace_adopted_design",
        "refusal_block_or_undesirable_response_retryable",
        "researcher_additional_disclosure_instruction_in_Frozen_request",
        "open_full_response_dataset_or_raw_in_git_authorized",
        "automatic_output_publication_authorized",
        "claimed_provider_or_institutional_endorsement",
        "provider_output_ownership_equals_all_third_party_rights_or_publication_permission",
        "account_or_billing_settings_change_authorized",
        "historical_raw_or_prior_W0_governance_changed_by_review",
    ):
        assert use[field] is False


def test_conditional_terms_proposal_never_accepts_contracts_sends_messages_or_finalizes_gates() -> (
    None
):
    proposal = load_yaml(PACK / "terms-review-08.proposal.yaml")
    approval = proposal["approval_scope"]
    assert approval["independent_ethics_question_may_follow_without_releasing_terms_hold"] is True
    assert all(
        value is False
        for key, value in approval.items()
        if key != "independent_ethics_question_may_follow_without_releasing_terms_hold"
    )
    assert not any(proposal["remaining_gates"].values())
    assert proposal["agent_may_finalize_human_governance_records"] is False
    assert proposal["approved"] is proposal["execution_permitted"] is False
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "terms-review-08.proposal.yaml")


def test_adopting_conditional_terms_preserves_all_unresolved_provider_and_ethics_holds() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    adopted = progress["conditional_terms_policy_adoption"]
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["original_proposal_kept_unchanged"] is True
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert adopted["proposal_sha256"] == (
        "cd4afa717ebcdbabef917d5cc2ad3bbdfa1b0fae6a91a89c0a21ae276cfeed1e"
    )
    for field in (
        "conditional_use_archive_and_publication_policy_adopted",
        "unresolved_terms_hold_maintained",
        "next_independent_ethics_question_authorized",
    ):
        assert adopted[field] is True
    for field in (
        "all_four_providers_terms_cleared",
        "FINAL_terms_review_record_complete",
        "provider_permission_or_contract_acceptance_inferred",
        "institutional_contact_or_email_authorized",
        "ethics_dates_freeze_or_API_authority_inferred",
        "exact_human_message_time_assumed",
    ):
        assert adopted[field] is False
    assert progress["other_decisions"]["provider_terms_review"] == "PENDING"
    assert progress["other_decisions"]["ethics_or_governance_determination"] == "PENDING"
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"


def test_ethics_review_discloses_human_coding_without_automatically_classifying_subjects() -> None:
    proposal = load_yaml(PACK / "ethics-governance-09.proposal.yaml")
    scope = proposal["scope"]
    assert scope["first_party_API_series"] == ["M01", "M02", "M03", "M05"]
    assert scope["primary_observations"] == 2800
    assert scope["human_primary_coders"] == 1
    assert scope["selected_repeat_coding_records"] == 280
    assert scope["minimum_repeat_delay_days_after_first_pass_lock"] == 7
    assert scope["primary_and_repeat_human_coding_records_in_design"] is True
    assert scope["model_response_is_only_data_type_in_design"] is False
    assert scope["new_human_participant_recruitment_intervention_or_survey_planned"] is False
    assert scope["actual_student_records_or_real_grading_decisions_planned"] is False
    assert scope["human_coder_is_a_research_participant_determination"].startswith("UNDETERMINED")
    assert scope["institutional_coverage_of_this_scope_verified"] is False
    process = proposal["confirmation_process_proposal"]
    assert process["sole_human_coder_automatically_requires_or_exempts_ethics_review"] is False
    assert process["personal_NOT_HUMAN_SUBJECTS_equals_institutional_NOT_REQUIRED"] is False
    assert process["A_is_a_requirement_confirmation_plan_not_a_nonhuman_subjects_decision"] is True


def test_prior_w0_nonhuman_subjects_judgment_is_preserved_not_extended_to_new_scope() -> None:
    proposal = load_yaml(PACK / "ethics-governance-09.proposal.yaml")
    prior = proposal["prior_ethics_record_reference_only"]
    assert sha256_file(ROOT / prior["path"]) == prior["sha256"]
    record = load_yaml(ROOT / prior["path"])
    assert record["status"] == "FINAL"
    assert record["decided_by"]["actor_type"] == "HUMAN"
    assert record["determination"] == prior["historical_determination"] == "NOT_HUMAN_SUBJECTS"
    assert prior["reapplied_or_relabelled_as_new_official_approval"] is False
    for record in load_yaml(PACK / "governance.template.yaml")["records"].values():
        assert record["status"] == "PENDING"
        assert record["determination"] is None
        assert record["human_attestation"] is False


def test_ethics_applicability_and_office_selection_remain_unfilled_without_current_authority() -> (
    None
):
    proposal = load_yaml(PACK / "ethics-governance-09.proposal.yaml")
    assert all(value is None for value in proposal["unfilled_human_fields"].values())
    public = proposal["public_sources_reference_only"]
    assert public["current_affiliation_or_right_to_apply_verified"] is False
    assert public["source_page_bytes_or_contract_snapshot_hash_claimed"] is False
    assert len(public["sources"]) == 4
    process = proposal["confirmation_process_proposal"]
    assert (
        process[
            "confirm_current_affiliation_project_host_and_applicable_rules_before_selecting_office"
        ]
        is True
    )
    assert (
        process["where_applicability_uncertain_seek_appropriate_human_or_office_clarification"]
        is True
    )
    for field in (
        "prior_affiliations_or_public_pages_establish_current_eligibility",
        "external_inquiry_always_legally_mandatory_for_every_API_study_claimed",
        "agent_may_decide_whether_that_route_applies",
        "membership_or_solo_owner_acceptance_equals_institutional_approval",
        "silence_or_no_reply_equals_exemption",
    ):
        assert process[field] is False
    assert process["applicable_rules_may_allow_attributed_responsible_human_determination"] is True
    assert process["if_institution_requires_review_or_other_steps"].endswith("BEFORE_LAUNCH")


def test_existing_new_scope_ethics_evidence_requires_authority_time_and_relevant_scope() -> None:
    proposal = load_yaml(PACK / "ethics-governance-09.proposal.yaml")
    evidence = proposal["existing_judgment_B_requirements"]
    assert evidence["old_W0_record_is_sufficient"] is False
    assert evidence["evidence_provided_by_this_preparation"] is False
    for field in (
        "exact_new_scope_version_and_hash_required",
        "decision_maker_name_role_authority_and_actual_time_with_timezone_required",
        "determination_rationale_and_evidence_references_required",
        "required_institutional_steps_completed_or_documented_not_required",
        "reference_number_or_office_reply_if_applicable_required",
        "appropriate_method_and_scope_must_match_current_plan",
    ):
        assert evidence[field] is True
    process = proposal["confirmation_process_proposal"]
    assert process["AI_may_fill_determination_or_set_FINAL_or_human_attestation"] is False
    assert process["actual_human_decision_timestamp_may_be_invented_from_recording_time"] is False


def test_ethics_preparation_never_sends_contact_or_api_requests_or_changes_frozen_payloads() -> (
    None
):
    proposal = load_yaml(PACK / "ethics-governance-09.proposal.yaml")
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert not any(proposal["remaining_gates"].values())
    assert not any(proposal["other_authority"].values())
    process = proposal["confirmation_process_proposal"]
    assert process["ethics_outcome_overrides_terms_or_runtime_holds"] is False
    assert (
        process[
            "actual_inquiry_recipient_content_and_sending_authority_require_separate_confirmation"
        ]
        is True
    )
    risk = proposal["risk_and_preservation_policy"]
    for field in (
        "unsupported_blanket_no_human_related_data_claim",
        "introduce_student_identifiers_or_new_participants_without_new_review",
        "Frozen_prompts_or_anchors_reworded_or_extra_payload_disclosure_added",
        "governance_or_coder_identity_added_to_model_request",
        "human_judgment_records_treated_as_provider_generated_output",
        "adverse_refusal_or_safety_outcome_removed_or_regenerated",
        "historical_raw_or_prior_governance_modified_by_this_plan",
    ):
        assert risk[field] is False
    assert risk["approved_scope_changes_require_new_version_and_review"] is True
    assert "STOP_AUTOMATIC_PUBLICATION" in risk["apparent_personal_data_or_rights_issue_action"]
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "ethics-governance-09.proposal.yaml")


def test_human_B_nonhuman_subjects_judgment_is_recorded_without_rewriting_reason_or_choice() -> (
    None
):
    progress = load_yaml(PACK / "decision-progress.yaml")
    judgment = progress["ethics_B_personal_judgment"]
    assert judgment["actor_attribution"] == "CURRENT_CHAT_USER"
    assert judgment["selected_option"] == "B"
    assert judgment["declared_personal_determination"] == "NOT_HUMAN_SUBJECTS"
    assert judgment["rationale_received_verbatim"] == "人間対象研究ではないため。"
    assert judgment["new_scope_personal_judgment_received"] is True
    assert judgment["human_reason_supplemented_by_agent"] is False
    assert judgment["option_A_external_inquiry_plan_adopted"] is False
    assert judgment["date_context_jst"] == "2026-11-02"
    assert judgment["exact_human_message_time_assumed"] is False
    assert judgment["agent_is_transcriber_not_approver"] is True
    assert judgment["original_proposal_kept_unchanged"] is True
    assert judgment["proposal_sha256"] == sha256_file(ROOT / judgment["proposal_path"])
    assert judgment["proposal_sha256"] == (
        "b24ee128827e0e1674c77e5861804f7a6e26edf7f4d8472b1fa07d8a4f17d98a"
    )
    assert len(judgment["receipt_sha256"]) == len(judgment["receipt_file_sha256"]) == 64


def test_personal_B_judgment_is_not_institutional_approval_or_completed_B_evidence() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    judgment = progress["ethics_B_personal_judgment"]
    for field in (
        "option_B_required_authority_and_evidence_complete",
        "current_host_or_nonreview_rule_verified",
        "personal_judgment_converted_to_institutional_approval_or_NOT_REQUIRED",
        "FINAL_ethics_or_governance_record_complete",
        "contact_dates_freeze_or_API_authority_inferred",
    ):
        assert judgment[field] is False
    assert progress["other_decisions"]["ethics_or_governance_determination"] == "PENDING"
    assert progress["other_decisions"]["provider_terms_review"] == "PENDING"
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"
    assert progress["execution_permitted"] is False
    assert judgment["unresolved_terms_hold_maintained"] is True
    for record in load_yaml(PACK / "governance.template.yaml")["records"].values():
        assert record["status"] == "PENDING"
        assert record["determination"] is record["decided_at"] is None
        assert not any(record["decided_by"].values())
        assert record["human_attestation"] is False


def test_B_judgment_does_not_invent_host_rules_or_remove_human_coding_from_scope() -> None:
    proposal = load_yaml(PACK / "ethics-governance-09.proposal.yaml")
    assert all(value is None for value in proposal["unfilled_human_fields"].values())
    assert proposal["scope"]["primary_and_repeat_human_coding_records_in_design"] is True
    assert proposal["scope"]["model_response_is_only_data_type_in_design"] is False
    assert proposal["scope"]["human_coder_is_a_research_participant_determination"].startswith(
        "UNDETERMINED"
    )
    assert (
        proposal["confirmation_process_proposal"][
            "external_inquiry_always_legally_mandatory_for_every_API_study_claimed"
        ]
        is False
    )
    assert not any(proposal["remaining_gates"].values())
    assert not any(proposal["other_authority"].values())


def test_human_B_supplement_does_not_copy_frozen_prompts_or_release_terms_holds() -> None:
    text = (PACK / "ETHICS-09-HUMAN-JUDGMENT.md").read_text(encoding="utf-8")
    battery = load_battery(ROOT / "battery/ebb-ja-v1.0.yaml")
    assert not any(item.prompt in text for item in battery.items)
    terms = load_yaml(PACK / "terms-review-08.proposal.yaml")
    assert all(
        row["gate"] == "BLOCKED_PENDING_SCOPE_SPECIFIC_HUMAN_TERMS_DETERMINATION"
        for row in terms["providers"].values()
    )
    progress = load_yaml(PACK / "decision-progress.yaml")
    assert progress["conditional_terms_policy_adoption"]["unresolved_terms_hold_maintained"] is True
    assert all(progress["prohibitions"].values())


def test_existing_institutional_judgment_report_is_received_without_selecting_outcome() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    report = progress["institutional_determination_report"]
    assert report["actor_attribution"] == "CURRENT_CHAT_USER"
    assert report["report_received_verbatim"] == "機関による承認・審査不要の判断あり。"
    assert report["existing_institutional_determination_reported"] is True
    assert report["verification_status"] == "REPORTED_DETAILS_PENDING"
    assert report["agent_is_transcriber_not_approver"] is True
    assert report["proposal_sha256"] == sha256_file(ROOT / report["proposal_path"])
    assert len(report["receipt_sha256"]) == len(report["receipt_file_sha256"]) == 64
    assert report["determination_category_chosen_by_agent"] is False
    assert report["previous_personal_judgment_replaced"] is False
    assert progress["ethics_B_personal_judgment"]["declared_personal_determination"] == (
        "NOT_HUMAN_SUBJECTS"
    )


def test_reported_institutional_judgment_does_not_invent_its_metadata_or_scope() -> None:
    report = load_yaml(PACK / "decision-progress.yaml")["institutional_determination_report"]
    for field in (
        "institution_name",
        "determination_category",
        "institutional_decision_date",
        "decision_maker_or_office",
        "covered_plan_version_or_hash",
        "evidence_reference",
        "conditions_or_expiry_if_applicable",
    ):
        assert report[field] is None
    assert report["institutional_metadata_and_scope_coverage_verified"] is False
    assert report["exact_institutional_or_human_message_timestamp_assumed"] is False
    assert report["new_institutional_review_or_contact_required_by_agent"] is False


def test_institutional_report_keeps_gates_pending_and_does_not_authorize_contacts_or_api() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    report = progress["institutional_determination_report"]
    assert report["FINAL_ethics_or_governance_record_complete"] is False
    assert report["contact_dates_freeze_or_API_authority_inferred"] is False
    assert report["unresolved_terms_hold_maintained"] is True
    assert progress["other_decisions"]["ethics_or_governance_determination"] == "PENDING"
    assert progress["other_decisions"]["provider_terms_review"] == "PENDING"
    assert progress["other_decisions"]["API_execution"] == "NOT_AUTHORIZED"
    assert progress["execution_permitted"] is False
    assert all(progress["prohibitions"].values())
    for record in load_yaml(PACK / "governance.template.yaml")["records"].values():
        assert record["status"] == "PENDING"
        assert record["determination"] is record["decided_at"] is None
        assert record["human_attestation"] is False


def test_human_direction_stops_document_requests_but_preserves_unverified_governance() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    direction = progress["governance_followup_direction"]
    assert direction["actor_attribution"] == "CURRENT_CHAT_USER"
    assert direction["agent_is_transcriber_not_approver"] is True
    assert direction["proposal_sha256"] == sha256_file(ROOT / direction["proposal_path"])
    assert direction["reference_is_prior_context_not_ethics_proposal_adoption"] is True
    for field in (
        "site_and_time_options_preparation_authorized",
        "further_governance_document_requests_stopped",
        "unverified_governance_details_retained_without_inference",
    ):
        assert direction[field] is True
    for field in (
        "institutional_details_or_terms_holds_cleared",
        "FINAL_human_governance_records_complete",
        "site_option_adopted_or_actual_site_locked",
        "concrete_date_or_field_window_approved",
        "automatic_start_or_calendar_schedule_authorized",
        "contact_credentials_freeze_or_API_authority_inferred",
    ):
        assert direction[field] is False
    report = progress["institutional_determination_report"]
    assert report["existing_institutional_determination_reported"] is True
    assert report["institution_name"] is report["determination_category"] is None
    assert report["verification_status"] == "REPORTED_DETAILS_PENDING"
    assert progress["other_decisions"]["ethics_or_governance_determination"] == "PENDING"
    assert progress["other_decisions"]["provider_terms_review"] == "PENDING"


def test_observer_site_options_require_new_choice_and_never_silently_reuse_old_site() -> None:
    proposal = load_yaml(PACK / "observer-site-10.proposal.yaml")
    assert proposal["recommended_option"] == "A"
    assert proposal["approved"] is proposal["execution_permitted"] is False
    option = proposal["options"]["A"]
    assert option["proposed_country"] == "JP"
    assert option["same_PC_place_and_ordinary_connection_as_W0_proposed"] is True
    assert option["AC_power_required_for_future_execution"] is True
    assert option["historical_site_label_candidate_only"] == "MIBO-SITE-JP01"
    assert option["prior_W0_declaration_is_new_scope_site_approval"] is False
    alternative = proposal["options"]["B"]
    assert alternative["new_site_details"] is None
    assert alternative["prior_site_label_may_be_silently_reused"] is False
    assert alternative["requires_scoped_site_and_environment_assessment_before_launch"] is True
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(PACK / "observer-site-10.proposal.yaml")


def test_observer_site_does_not_request_private_location_identifiers_or_claim_serving_region() -> (
    None
):
    proposal = load_yaml(PACK / "observer-site-10.proposal.yaml")
    assert not any(proposal["privacy_and_interpretation"].values())
    holds = proposal["governance_and_other_holds"]
    assert holds["further_governance_document_requests_stopped"] is True
    assert holds["unverified_details_remain_unverified"] is True
    for field in (
        "human_report_of_institutional_judgment_rejected_or_removed",
        "terms_or_governance_holds_cleared_by_site_choice",
        "incomplete_cost_capacity_or_runtime_support_waived",
        "full_four_provider_wave_is_ready_or_feasibility_guaranteed",
        "Frozen_artifacts_prompts_anchors_or_historical_raw_changed",
        "final_protocol_approval_or_execution_permission_inferred",
    ):
        assert holds[field] is False


def test_site_environment_requirements_do_not_start_guard_probe_network_or_read_credentials() -> (
    None
):
    proposal = load_yaml(PACK / "observer-site-10.proposal.yaml")
    environment = proposal["future_environment_controls"]
    assert environment["evidence_root_candidate"] == r"C:\Users\offic\EIBO-W0-Evidence"
    assert environment["persistent_storage_and_write_check_required_before_execution"] is True
    assert (
        environment["first_party_provider_endpoint_and_no_third_party_model_router_required"]
        is True
    )
    assert (
        environment["AC_state_guard_process_and_environment_preflight_required_before_execution"]
        is True
    )
    for field in (
        "researcher_added_VPN_or_proxy_rerouting_proposed",
        "full_18h_target_24h_hard_window_sleep_guard_support_verified",
        "power_plan_display_lock_lid_update_or_battery_protection_changes_authorized",
        "guard_start_credential_read_or_network_probe_authorized_now",
        "actual_current_country_PC_connection_AC_or_guard_verified",
    ):
        assert environment[field] is False
    assert (
        "PRESERVE_IN_FLIGHT_AND_RAW"
        in environment["site_or_material_environment_change_during_wave_action"]
    )
    assert all(proposal["prohibitions"].values())


def test_site_choice_leaves_dates_automation_and_final_runtime_locks_unfilled() -> None:
    proposal = load_yaml(PACK / "observer-site-10.proposal.yaml")
    timing = proposal["time_and_authority"]
    assert timing["next_question_is_separate_datetime_choice"] is True
    assert timing["display_timezone"] == "Asia/Tokyo"
    assert timing["canonical_clock"] == "UTC"
    assert timing["adopted_target_hours"] == timing["adopted_planned_span_hours"] == 18
    assert timing["adopted_hard_hours"] == 24
    for field in (
        "concrete_date_time_or_timezone_offset_selected",
        "new_observation_window_or_dates_created",
        "automation_or_calendar_schedule_created",
        "earliest_possible_launch_equals_site_policy_adoption",
        "actual_runtime_site_lock_created",
        "models_schedule_or_manifest_lock_created",
    ):
        assert timing[field] is False
    runtime = load_yaml(PACK / "runtime-lock.template.yaml")
    assert (
        runtime["observer_site_lock"]
        is runtime["schedule_path"]
        is runtime["model_lock_path"]
        is None
    )
    assert runtime["field_window"]["start"] is runtime["field_window"]["end"] is None
    assert runtime["explicit_launch_authority"] is None


def test_adopted_site_policy_is_bound_to_the_proposal_but_not_a_runtime_lock() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    site = progress["observer_site_policy_adoption"]
    assert site["decision"] == "EXPLICIT_HUMAN_OPTION_A_SAME_LOCAL_W0_SITE_POLICY_ONLY"
    assert site["actor_attribution"] == "CURRENT_CHAT_USER"
    assert site["agent_is_transcriber_not_approver"] is True
    assert site["proposal_sha256"] == sha256_file(ROOT / site["proposal_path"])
    assert len(site["receipt_file_sha256"]) == len(site["receipt_sha256"]) == 64
    assert site["country_policy"] == "JP"
    assert site["same_W0_PC_place_and_ordinary_connection"] is True
    assert site["AC_power_required_for_future_execution"] is True
    for field in (
        "actual_site_environment_verified_or_locked",
        "concrete_date_or_field_window_approved",
        "calendar_automation_or_automatic_start_authorized",
        "institutional_details_or_terms_holds_cleared",
        "API_execution_authorized",
        "exact_human_message_time_assumed",
    ):
        assert site[field] is False
    assert progress["other_decisions"]["observer_site_and_date"] == "PENDING"


def test_datetime_proposal_is_not_schedule_or_authority_and_preserves_holds() -> None:
    path = PACK / "observation-datetime-11.proposal.yaml"
    proposal = load_yaml(path)
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert proposal["wave_id_candidate"] == "EIBO-F01"
    assert proposal["scope"]["series"] == ["M01", "M02", "M03", "M05"]
    assert proposal["recommended_option"] == "A"
    assert proposal["options"]["A"]["date_candidate"] is None
    assert proposal["options"]["A"]["automatic_start_on_readiness"] is False
    assert proposal["timing_policy"]["confirmed_start"] is None
    assert (
        proposal["timing_policy"]["final_datetime_and_launch_require_separate_human_confirmation"]
        is True
    )
    holds = proposal["holds"]
    assert holds["further_governance_document_requests_stopped"] is True
    assert holds["unverified_governance_details_and_terms_retained"] is True
    assert holds["existing_readiness_and_final_lock_gates_maintained"] is True
    assert holds["automatic_start_calendar_reservation_or_runtime_lock_created"] is False
    assert all(proposal["prohibitions"].values())
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(path)


def test_tentative_datetime_uses_one_anchor_and_adopted_jst_utc_window() -> None:
    proposal = load_yaml(PACK / "observation-datetime-11.proposal.yaml")
    timing = proposal["timing_policy"]
    candidate = proposal["options"]["B"]
    start = datetime.fromisoformat(candidate["start_candidate_jst"])
    target = datetime.fromisoformat(candidate["target_candidate_jst"])
    end = datetime.fromisoformat(candidate["hard_deadline_candidate_jst"])
    assert start.weekday() == 2 and candidate["weekday"] == "Wednesday"
    assert start.utcoffset() == timedelta(hours=9)
    assert start.strftime("%H:%M") == proposal["options"]["A"]["preferred_start_jst"]
    assert timing["same_anchor_for_all_series"] is True
    assert timing["recurrence_interval_calendar_months"] == 3
    assert timing["future_wave_dates_or_automatic_recurrence_created"] is False
    assert target - start == timedelta(hours=timing["target_hours"]) == timedelta(hours=18)
    assert end - start == timedelta(hours=timing["hard_hours"]) == timedelta(hours=24)
    assert timing["planned_span_hours"] == timing["target_hours"]
    for field, stamp in (("start", start), ("target", target), ("hard_deadline", end)):
        assert stamp.astimezone(UTC) == datetime.fromisoformat(candidate[f"{field}_candidate_utc"])
    assert candidate["operator_availability_or_full_wave_feasibility_verified"] is False
    assert candidate["if_gates_unmet_or_candidate_passes"].startswith(
        "DO_NOT_START_NO_AUTOMATIC_RESCHEDULE"
    )


def test_datetime_adoption_records_policy_without_date_reservation_or_authority() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    date_policy = progress["first_observation_datetime_policy_adoption"]
    assert date_policy["decision"] == (
        "EXPLICIT_HUMAN_OPTION_A_CHOOSE_WEEKDAY_0900_JST_AFTER_READINESS_ONLY"
    )
    assert date_policy["actor_attribution"] == "CURRENT_CHAT_USER"
    assert date_policy["proposal_sha256"] == sha256_file(ROOT / date_policy["proposal_path"])
    assert len(date_policy["receipt_file_sha256"]) == len(date_policy["receipt_sha256"]) == 64
    assert date_policy["weekday_only"] is date_policy["choose_date_only_after_readiness"] is True
    assert date_policy["preferred_start_jst"] == "09:00"
    assert date_policy["confirmed_start"] is None
    for field in (
        "tentative_option_B_adopted",
        "calendar_automation_or_automatic_start_authorized",
        "institutional_details_or_terms_holds_cleared",
        "API_execution_authorized",
        "exact_human_message_time_assumed",
    ):
        assert date_policy[field] is False
    assert date_policy["further_governance_document_requests_stopped"] is True
    assert date_policy["unverified_governance_details_retained_without_inference"] is True
    assert date_policy["agent_is_transcriber_not_approver"] is True
    assert progress["other_decisions"]["observer_site_and_date"] == "PENDING"


def test_offline_capacity_proposal_keeps_full_scope_without_live_execution() -> None:
    path = PACK / "offline-capacity-12.proposal.yaml"
    proposal = load_yaml(path)
    assert proposal["recommended_option"] == "A"
    assert proposal["approved"] is proposal["execution_permitted"] is False
    assert "OFFLINE" in proposal["options"]["A"]
    assert proposal["options"]["B"] == "DEFER_OFFLINE_VERIFICATION_KEEP_CAPACITY_GATE_BLOCKED"
    scope = proposal["fixed_scope"]
    assert scope["series"] == ["M01", "M02", "M03", "M05"]
    assert scope["primary_cells"] == len(scope["series"]) * scope["items"] * 10 == 2800
    assert scope["replications_per_item_series"] == 10
    assert scope["same_anchor_for_all_series"] is True
    assert scope["planned_span_and_target_hours"] == 18
    assert scope["hard_deadline_hours"] == 24
    assert scope["Google_minimum_start_gap_seconds_including_retries"] == 65
    assert scope["minimum_technical_retry_wait_seconds"] == 120
    assert scope["honor_longer_provider_retry_advice"] is True
    assert all(proposal["prohibitions"].values())
    with pytest.raises(ValidationError, match="invalid Wave Manifest"):
        load_manifest(path)


def test_offline_capacity_proposal_does_not_claim_a_pass_or_clear_live_gates() -> None:
    proposal = load_yaml(PACK / "offline-capacity-12.proposal.yaml")
    checks = proposal["checks_proposed"]
    assert checks["mock_transport_with_no_outbound_network_and_separate_synthetic_archive"]
    assert checks["exercise_intended_implementation_paths_or_report_missing_coverage"]
    assert checks["fault_cases_check_safe_stops_and_missingness_not_guaranteed_completion"]
    assert checks["no_scientific_outcome_retry_or_substitution"]
    assert checks["late_response_preserved_nonprimary_and_no_start_at_or_after_hard_deadline"]
    assert len(proposal["unverified_after_offline_test"]) == 5
    status = proposal["authority_and_status"]
    for field in (
        "verification_performed_or_passed",
        "synthetic_records_are_official_longitudinal_data",
        "actual_date_confirmed_or_automation_reserved",
        "runtime_locks_created",
    ):
        assert status[field] is False
    assert status["unverified_governance_details_and_terms_retained"] is True
    assert status["further_governance_document_requests_stopped"] is True
    assert status["date_selection_and_launch_authority_remain_separate"] is True

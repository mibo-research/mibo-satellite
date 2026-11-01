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


def test_explicit_scope_adoption_does_not_approve_other_decisions() -> None:
    progress = load_yaml(PACK / "decision-progress.yaml")
    assert progress["current_step"] == 5
    assert progress["next_decision_id"] == "official_provider_profiles_and_model_selection_policy"
    assert progress["execution_permitted"] is False
    adopted = progress["scope_adoption"]
    assert adopted["decision"] == "EXPLICIT_HUMAN_OPTION_A_BASIC_SCOPE_ONLY"
    assert adopted["actor_attribution"] == "CURRENT_CHAT_USER"
    assert adopted["agent_is_transcriber_not_approver"] is True
    assert adopted["exact_human_message_time_assumed"] is False
    assert adopted["proposal_sha256"] == sha256_file(ROOT / adopted["proposal_path"])
    assert len(adopted["receipt_file_sha256"]) == len(adopted["receipt_sha256"]) == 64
    assert progress["other_decisions"]["official_provider_profiles_and_exact_models"] == "PENDING"
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
    assert progress["other_decisions"]["official_provider_profiles_and_exact_models"] == "PENDING"
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
    assert progress["other_decisions"]["official_provider_profiles_and_exact_models"] == "PENDING"
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
    assert progress["other_decisions"]["official_provider_profiles_and_exact_models"] == "PENDING"
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

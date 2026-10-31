from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from eibo.closeout import ITEM_IDS, MODELS, assess_closeout, evidence_path, main, verify_archive
from eibo.errors import ImmutabilityError, ValidationError
from eibo.util import canonical_json_bytes, load_json, sha256_file


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "external-evidence"
    root.mkdir()

    def write(relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes({"official_longitudinal_data": False, **data}))
        return {"path": relative, "sha256": sha256_file(path)}

    sentinel = write("archive/original.json", {"immutable": True})
    sources = {
        "official_longitudinal_data": False,
        "summary": write("summary.json", {"archive_integrity_qc_passed": True}),
        "archive": write("archive.json", {"entries": [sentinel]}),
        "prior_integrity": write("prior.json", {"entries": {sentinel["path"]: sentinel["sha256"]}}),
        "recovery_qc": write(
            "qc.json", {"archive_integrity_qc_passed": True, "entries": [sentinel]}
        ),
        "m05_profile_sha256": "a" * 64,
        "providers": {},
    }
    for series, model in MODELS.items():
        rows = [{"item_id": item, "returned_model": model} for item in ITEM_IDS]
        common = {
            "series_id": series,
            "requested_model": model,
            "substitution_attempted": False,
            "qualification_profile_sha256": "a" * 64,
        }
        refs = {
            "q1": write(
                f"{series}/q1.json",
                {
                    **common,
                    "passed": True,
                    "ordinary_requests_attempted": 1,
                    "metadata_complete": True,
                    "returned_model": model,
                },
            ),
            "q2": write(
                f"{series}/q2.json",
                {
                    **common,
                    "passed": series != "M03",
                    "status": "FAILED_CLOSED" if series == "M03" else "PASSED",
                    "item_results": rows[:5] if series == "M03" else rows,
                    "closed_diagnostic_results": rows if series == "M05" else [],
                },
            ),
        }
        if series == "M03":
            refs["original_technical_failures"] = {
                item: write(f"failed/{item}.json", {"status_code": 429}) for item in ITEM_IDS[5:]
            }
            refs["recoveries"] = [
                write(
                    f"recovery/{item}.json",
                    {
                        "item_id": item,
                        "returned_model": model,
                        "recovery_qualified": True,
                    },
                )
                for item in ITEM_IDS[5:]
            ]
        sources["providers"][series] = refs
    source_path = tmp_path / "sources.json"

    def persist():
        source_path.write_bytes(canonical_json_bytes(sources))

    def change(reference, **values):
        path = root / reference["path"]
        data = load_json(path)
        data.update(values)
        path.write_bytes(canonical_json_bytes(data))
        reference["sha256"] = sha256_file(path)
        persist()

    persist()
    return root, source_path, sources, persist, change


def test_offline_closeout_preserves_original_results_and_gates(evidence, monkeypatch):
    root, source, _, _, _ = evidence
    before = {p: sha256_file(p) for p in root.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("offline assessment must not send any provider request")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    report = assess_closeout(root, source)
    assert report["FOUR_PROVIDER_EVIDENCE_COMPLETE"] is True
    assert report["providers"]["M03"]["original_Q2"] == "FAILED_CLOSED"
    assert report["providers"]["M03"]["separate_recovery_items"] == 2
    assert report["providers"]["M05"]["non_official_no_search_diagnostics"] == 7
    assert report["official_longitudinal_data"] is False
    assert report["W0_READY"] is report["W01_READY"] is False
    assert report["new_Q2_or_Q3_gate_created"] is False
    assert report["human_closeout_acceptance"] == "PENDING_EXPLICIT_HUMAN_RECORD"
    assert report["provider_requests_sent"] == report["xai_requests_sent"] == 0
    assert {p: sha256_file(p) for p in root.rglob("*") if p.is_file()} == before


def test_changed_pinned_evidence_is_rejected(evidence):
    root, source, sources, _, _ = evidence
    (root / sources["providers"]["M01"]["q1"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValidationError, match="hash mismatch"):
        assess_closeout(root, source)


@pytest.mark.parametrize(
    "values",
    [
        {"passed": False},
        {"ordinary_requests_attempted": 2},
        {"metadata_complete": False},
        {"returned_model": "substitute"},
        {"requested_model": "substitute"},
        {"series_id": "M04"},
        {"substitution_attempted": True},
        {"official_longitudinal_data": True},
    ],
)
def test_invalid_smoke_evidence_fails_closed(evidence, values):
    root, source, sources, _, change = evidence
    change(sources["providers"]["M01"]["q1"], **values)
    with pytest.raises(ValidationError):
        assess_closeout(root, source)


@pytest.mark.parametrize("case", ["missing", "duplicate", "identity", "failed"])
def test_incomplete_original_q2_fails_closed(evidence, case):
    root, source, sources, _, change = evidence
    ref = sources["providers"]["M01"]["q2"]
    rows = load_json(root / ref["path"])["item_results"]
    if case == "missing":
        rows.pop()
    elif case == "duplicate":
        rows[-1] = rows[0]
    elif case == "identity":
        rows[0]["returned_model"] = "substitute"
    change(ref, item_results=rows, passed=case != "failed")
    with pytest.raises(ValidationError):
        assess_closeout(root, source)


@pytest.mark.parametrize(
    "values",
    [
        {"item_id": "E1-01"},
        {"recovery_qualified": False},
        {"returned_model": "substitute"},
        {"official_longitudinal_data": True},
    ],
)
def test_recovery_cannot_replace_completed_cell_or_change_identity(evidence, values):
    root, source, sources, _, change = evidence
    change(sources["providers"]["M03"]["recoveries"][0], **values)
    with pytest.raises(ValidationError):
        assess_closeout(root, source)


def test_google_original_failure_cannot_be_relabelled_passed(evidence):
    root, source, sources, _, change = evidence
    change(sources["providers"]["M03"]["q2"], status="PASSED", passed=True)
    with pytest.raises(ValidationError, match="historical Google"):
        assess_closeout(root, source)


@pytest.mark.parametrize("status_code", [200, 400, 401, 403])
def test_scientific_or_nonretryable_original_response_cannot_be_recovered(evidence, status_code):
    root, source, sources, _, change = evidence
    change(
        sources["providers"]["M03"]["original_technical_failures"]["E6-01"], status_code=status_code
    )
    with pytest.raises(ValidationError, match="scientific response"):
        assess_closeout(root, source)


@pytest.mark.parametrize(
    "values",
    [
        {"qualification_profile_sha256": "b" * 64},
        {"closed_diagnostic_results": []},
    ],
)
def test_m05_qualification_requires_current_profile_and_separate_diagnostic(evidence, values):
    root, source, sources, _, change = evidence
    change(sources["providers"]["M05"]["q2"], **values)
    with pytest.raises(ValidationError):
        assess_closeout(root, source)


def test_refusal_and_truncation_are_outcomes_not_retry_or_failure_conditions(evidence):
    root, source, sources, _, change = evidence
    ref = sources["providers"]["M01"]["q2"]
    rows = load_json(root / ref["path"])["item_results"]
    rows[0].update(refusal_observed=True, truncation_or_output_cap_stop_observed=True)
    change(ref, item_results=rows)
    row = assess_closeout(root, source)["providers"]["M01"]
    assert row["assessment"] == "COMPLETE"
    assert row["refusals_observed"] == row["truncations_observed"] == 1


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "C:/secret", r"..\secret", ""])
def test_sources_cannot_escape_evidence_root(tmp_path, path):
    with pytest.raises(ValidationError):
        evidence_path(tmp_path, path)


def test_windows_archive_paths_are_portable_without_rewriting(evidence):
    root, _, sources, _, _ = evidence
    row = load_json(root / sources["archive"]["path"])["entries"][0]
    assert verify_archive(root, [{**row, "path": row["path"].replace("/", "\\")}]) == 1
    with pytest.raises(ValidationError, match="duplicate"):
        verify_archive(root, [row, {**row, "path": row["path"].replace("/", "\\")}])
    with pytest.raises(ValidationError, match="byte count"):
        verify_archive(root, [{**row, "bytes": 0}])


def test_sources_cannot_reintroduce_xai_or_official_status(evidence):
    root, source, sources, persist, _ = evidence
    sources["providers"]["M04"] = sources["providers"]["M01"]
    persist()
    with pytest.raises(ValidationError, match="four authorized"):
        assess_closeout(root, source)
    del sources["providers"]["M04"]
    sources["official_longitudinal_data"] = True
    persist()
    with pytest.raises(ValidationError, match="non-official"):
        assess_closeout(root, source)


def test_archive_integrity_and_secret_scan_fail_closed(evidence):
    root, source, sources, _, change = evidence
    change(sources["summary"], unexpected="AIza" + "X" * 35)
    with pytest.raises(ValidationError, match="secret-redaction"):
        assess_closeout(root, source)


def test_closeout_output_is_create_once(evidence, monkeypatch):
    root, source, _, _, _ = evidence
    output = root / "closeouts/assessment.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "closeout",
            "--evidence-root",
            str(root),
            "--sources",
            str(source),
            "--output",
            str(output),
        ],
    )
    main()
    before = output.read_bytes()
    with pytest.raises(ImmutabilityError):
        main()
    assert output.read_bytes() == before


def test_prospective_drafts_do_not_approve_or_execute_anything():
    root = Path(__file__).resolve().parents[1]
    directory = root / "operations/prospective-four-provider"
    plan = yaml.safe_load((directory / "plan.draft.yaml").read_text(encoding="utf-8"))
    assert plan["status"] == "DRAFT_PENDING_EXPLICIT_HUMAN_DETERMINATIONS"
    assert plan["execution_permitted"] is plan["official_longitudinal_data"] is False
    assert plan["legacy_Core_35_redefined"] is False
    assert plan["panel"]["closed_primary"] == ["M01", "M02", "M03"]
    assert plan["panel"]["native_separate_mirror"] == ["M05"]
    assert plan["panel"]["xai_api_calls_permitted"] is False
    assert plan["next_rehearsal_proposal"]["expected_primary_requests"] == 28
    assert plan["next_rehearsal_proposal"]["execution_authorized"] is False
    assert plan["future_official_wave_proposal"]["ai_secondary_coding_enabled"] is False
    runtime = yaml.safe_load((directory / "runtime-lock.template.yaml").read_text(encoding="utf-8"))
    assert runtime["execution_permitted"] is False
    assert runtime["field_window"]["start"] is runtime["field_window"]["end"] is None
    assert runtime["schedule_sha256"] is runtime["exact_model_lock_path"] is None
    assert runtime["observer"]["actual_site_id"] is None
    for path in (directory / "governance").glob("*.yaml"):
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert record["status"] == "PENDING_HUMAN_DETERMINATION"
        assert record["human_attestation"] is False
        assert record["decided_by"]["name"] is record["decided_at"] is None
    legacy = yaml.safe_load(
        (root / "waves/W0/live-qualification-plan.yaml").read_text(encoding="utf-8")
    )
    assert legacy["core_35_rehearsal"]["series_ids"] == ["M01", "M02", "M03", "M04", "M05"]

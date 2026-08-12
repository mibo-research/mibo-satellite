from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import Environment, make_adapter
from .artifacts import (
    load_battery,
    load_manifest,
    load_registry,
    load_scientific_artifact_registry,
    load_yaml,
)
from .preflight import preflight
from .util import sha256_file

FLAGS = (
    "ENGINEERING_READY",
    "SCIENTIFIC_PROTOCOL_COMPLETE",
    "W0_READY",
    "W01_READY",
)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def scientific_readiness(root: Path) -> dict[str, Any]:
    root = root.resolve()
    reasons = {flag: [] for flag in FLAGS}
    artifact_states: dict[str, dict[str, Any]] = {}

    try:
        load_registry(root / "registry" / "model-series.yaml")
        load_battery(root / "battery" / "w0-engineering-smoke.yaml")
        probes = (
            ("openai", {}, Environment.CLOSED),
            ("anthropic", {"max_tokens": 64}, Environment.CLOSED),
            ("gemini", {}, Environment.CLOSED),
            ("xai", {}, Environment.CLOSED),
            ("perplexity", {}, Environment.NATIVE),
        )
        for provider, sampling, environment in probes:
            make_adapter(provider).prepare(
                model="engineering-exact-id",
                prompt="dry run",
                environment=environment,
                sampling=sampling,
            )
    except Exception as exc:
        reasons["ENGINEERING_READY"].append(str(exc))

    try:
        science_registry = load_scientific_artifact_registry(
            root / "protocol" / "scientific-artifacts.yaml"
        )
        if science_registry["status"] != "FROZEN":
            reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(
                "scientific artifact freeze registry is BLOCKED rather than FROZEN"
            )
        for artifact_id, value in science_registry["artifacts"].items():
            artifact_states[artifact_id] = {
                "status": value["status"],
                "approved": value["approved"],
                "expected_path": str(value["resolved_path"]),
                "sha256": value.get("sha256"),
                "blocker": value.get("blocker"),
            }
            if value["status"] != "FROZEN" or not value["approved"]:
                reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(
                    f"{artifact_id}: {value.get('blocker') or 'not Frozen and approved'}"
                )
    except Exception as exc:
        reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(str(exc))

    try:
        battery = load_battery(root / "battery" / "ebb-ja-v1.0.yaml")
        if not battery.approved or not battery.official_eligible:
            reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(
                "EBB-JA v1.0 is not approved and longitudinally eligible"
            )
    except Exception as exc:
        reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(f"EBB-JA v1.0: {exc}")

    w0_path = root / "waves" / "W0" / "manifest.yaml"
    try:
        w0 = load_manifest(w0_path)
        if w0.official:
            reasons["W0_READY"].append("W0 is incorrectly marked official longitudinal data")
        missing_approvals = sorted(key for key, value in w0.approvals.items() if not value)
        if missing_approvals:
            reasons["W0_READY"].append(f"missing W0 approvals: {missing_approvals}")
        reasons["W0_READY"].extend(preflight(w0, write_report=False)["errors"])
        candidate_path = root / "waves" / "W0" / "model-lock.candidate.yaml"
        if candidate_path.is_file():
            candidate = load_yaml(candidate_path)
            if candidate.get("status") != "QUALIFIED":
                reasons["W0_READY"].append(
                    "W0 model-lock candidate is incomplete and not executable"
                )
                reasons["W0_READY"].extend(
                    f"W0 qualification: {blocker}"
                    for blocker in candidate.get("blockers", [])
                    if isinstance(blocker, str)
                )
    except Exception as exc:
        reasons["W0_READY"].append(str(exc))
    if reasons["ENGINEERING_READY"]:
        reasons["W0_READY"].append("engineering validation is incomplete")

    w01_path = root / "waves" / "W01" / "manifest.yaml"
    try:
        runtime = load_yaml(w01_path)
        scientific_path = w01_path.parent / str(runtime.get("scientific_design_artifact", ""))
        claimed_scientific_hash = runtime.get("scientific_design_sha256")
        if runtime.get("scientific_design_artifact") != "scientific-manifest-v1.0.yaml":
            reasons["W01_READY"].append(
                "runtime manifest does not reference scientific-manifest-v1.0.yaml"
            )
        elif (
            not scientific_path.is_file()
            or sha256_file(scientific_path) != claimed_scientific_hash
        ):
            reasons["W01_READY"].append("runtime scientific-manifest hash binding is invalid")
        if runtime.get("runtime_status") != "LOCKED":
            reasons["W01_READY"].append("W01 runtime manifest is not LOCKED")
        if not runtime.get("exact_model_lock_path"):
            reasons["W01_READY"].append("exact Wave model-lock is missing")
        if not runtime.get("schedule_path") or not runtime.get("schedule_sha256"):
            reasons["W01_READY"].append("schedule path and SHA-256 lock are missing")
        if not runtime.get("observer_site_or_region"):
            reasons["W01_READY"].append("observer site or region lock is missing")
        provider_controls = runtime.get("provider_required_controls") or {}
        unresolved_controls = [
            series_id for series_id in (f"M0{i}" for i in range(1, 6))
            if not provider_controls.get(series_id)
        ]
        if unresolved_controls:
            reasons["W01_READY"].append(
                f"required provider controls are unresolved: {unresolved_controls}"
            )
        closed_eligibility = runtime.get("closed_eligibility_verified") or {}
        unverified_closed = [
            series_id for series_id in ("M01", "M02", "M03", "M04")
            if closed_eligibility.get(series_id) is not True
        ]
        if unverified_closed:
            reasons["W01_READY"].append(
                f"CLOSED eligibility is unverified: {unverified_closed}"
            )
        governance = (
            "protocol_owner",
            "provider_terms_review",
            "institutional_ethics_or_governance_determination",
        )
        missing_governance = [key for key in governance if not runtime.get(key)]
        if missing_governance:
            reasons["W01_READY"].append(
                f"required governance determinations are missing: {missing_governance}"
            )
        if not runtime.get("wave_lock_timestamp_utc"):
            reasons["W01_READY"].append("Wave lock timestamp is missing")
        if runtime.get("execution_permitted") is not True:
            reasons["W01_READY"].append("W01 execution is not permitted")
    except Exception as exc:
        reasons["W01_READY"].append(f"W01 runtime manifest is invalid: {exc}")
    if reasons["SCIENTIFIC_PROTOCOL_COMPLETE"]:
        reasons["W01_READY"].append("scientific protocol artifacts are incomplete")
    if reasons["ENGINEERING_READY"]:
        reasons["W01_READY"].append("engineering validation is incomplete")

    reasons = {flag: _unique(values) for flag, values in reasons.items()}
    return {
        **{flag: not reasons[flag] for flag in FLAGS},
        "reasons": reasons,
        "scientific_artifacts": artifact_states,
    }

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

    w01_path = root / "waves" / "W01" / "manifest.yaml"
    try:
        w01_raw = load_yaml(w01_path)
        if (
            str(w01_raw.get("status", "")).upper() != "FROZEN"
            or w01_raw.get("approved") is not True
        ):
            reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(
                "W01 Wave Manifest is BLOCKED rather than Frozen and approved"
            )
    except Exception as exc:
        reasons["SCIENTIFIC_PROTOCOL_COMPLETE"].append(f"W01 Wave Manifest: {exc}")

    w0_path = root / "waves" / "W0" / "manifest.yaml"
    try:
        w0 = load_manifest(w0_path)
        if w0.official:
            reasons["W0_READY"].append("W0 is incorrectly marked official longitudinal data")
        missing_approvals = sorted(key for key, value in w0.approvals.items() if not value)
        if missing_approvals:
            reasons["W0_READY"].append(f"missing W0 approvals: {missing_approvals}")
        reasons["W0_READY"].extend(preflight(w0, write_report=False)["errors"])
    except Exception as exc:
        reasons["W0_READY"].append(str(exc))
    if reasons["ENGINEERING_READY"]:
        reasons["W0_READY"].append("engineering validation is incomplete")

    try:
        w01 = load_manifest(w01_path)
        reasons["W01_READY"].extend(preflight(w01, write_report=False)["errors"])
    except Exception as exc:
        reasons["W01_READY"].append(f"W01 Wave Manifest is not executable: {exc}")
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

from __future__ import annotations

from pathlib import Path

import pytest

from miboe.artifacts import load_scientific_artifact_registry
from miboe.cli import main, parser
from miboe.errors import ValidationError
from miboe.preflight import preflight
from miboe.readiness import FLAGS, scientific_readiness
from miboe.util import ensure_no_secrets


def test_w01_is_cryptographically_and_scientifically_blocked() -> None:
    root = Path(__file__).parents[1]
    report = scientific_readiness(root)
    assert report["W01_READY"] is False
    assert report["SCIENTIFIC_PROTOCOL_COMPLETE"] is True
    assert report["reasons"]["W01_READY"]
    assert main(["run-wave", "--manifest", str(root / "waves" / "W01" / "manifest.yaml")]) == 1


def test_all_authoritative_artifacts_are_frozen_and_verified() -> None:
    root = Path(__file__).parents[1]
    registry = load_scientific_artifact_registry(root / "protocol" / "scientific-artifacts.yaml")
    assert len(registry["artifacts"]) == 5
    assert {value["status"] for value in registry["artifacts"].values()} == {"FROZEN"}
    assert all(value["approved"] for value in registry["artifacts"].values())


def test_readiness_flags_are_independent_and_every_false_flag_has_reasons() -> None:
    report = scientific_readiness(Path(__file__).parents[1])
    assert report["ENGINEERING_READY"] is True
    assert report["SCIENTIFIC_PROTOCOL_COMPLETE"] is True
    assert report["W0_READY"] is False
    assert report["W01_READY"] is False
    for flag in FLAGS:
        if report[flag]:
            assert report["reasons"][flag] == []
        else:
            assert report["reasons"][flag]


def test_preflight_detects_permanent_registry_drift(wave_factory) -> None:
    manifest, _, _, _ = wave_factory()
    with manifest.registry_path.open("a", encoding="utf-8") as stream:
        stream.write("\nchanged_after_lock: true\n")
    report = preflight(manifest, write_report=False)
    assert report["passed"] is False
    assert "model-series registry changed" in " ".join(report["errors"])


def test_secret_redaction_validation_uses_configured_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "a-real-test-secret-value")
    with pytest.raises(ValidationError, match="secret-redaction"):
        ensure_no_secrets(b'{"value":"a-real-test-secret-value"}', context="test")


def test_cli_exposes_required_commands() -> None:
    help_text = parser().format_help()
    for command in (
        "validate",
        "models",
        "schedule",
        "pilot",
        "preflight",
        "run-wave",
        "qc",
        "certificate",
        "export-blind",
    ):
        assert command in help_text


def test_engineering_validation_passes_with_scientific_protocol_complete(capsys) -> None:
    root = Path(__file__).parents[1]
    assert main(["validate", "--engineering", "--root", str(root)]) == 0
    output = capsys.readouterr().out
    assert '"ENGINEERING_READY": true' in output
    assert '"SCIENTIFIC_PROTOCOL_COMPLETE": true' in output
    assert '"W0_READY": false' in output
    assert '"W01_READY": false' in output
    assert '"reasons"' in output

from __future__ import annotations

from pathlib import Path

import pytest

from miboe.artifacts import load_manifest
from miboe.cli import main, parser
from miboe.errors import ValidationError
from miboe.preflight import preflight
from miboe.util import ensure_no_secrets


def test_w01_is_cryptographically_and_scientifically_blocked() -> None:
    manifest_path = Path(__file__).parents[1] / "waves" / "W01" / "manifest.yaml"
    report = preflight(load_manifest(manifest_path), write_report=False)
    assert report["passed"] is False
    assert any("70" in error or "scientific artifact" in error for error in report["errors"])


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


def test_engineering_validation_passes_but_reports_scientific_blocker(capsys) -> None:
    root = Path(__file__).parents[1]
    assert main(["validate", "--engineering", "--root", str(root)]) == 0
    output = capsys.readouterr().out
    assert '"ENGINEERING_READY": true' in output
    assert '"W01_READY": false' in output

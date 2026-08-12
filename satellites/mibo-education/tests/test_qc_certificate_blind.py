from __future__ import annotations

from miboe.adapters.base import ProviderResponse
from miboe.adapters.openai import OpenAIAdapter
from miboe.blind import export_blind
from miboe.certificate import create_certificate
from miboe.qc import run_qc
from miboe.runner import run_wave
from miboe.util import canonical_json_bytes


class AlwaysAdapter:
    def __init__(self):
        self.delegate = OpenAIAdapter()

    def prepare(self, **kwargs):
        return self.delegate.prepare(**kwargs)

    def normalize(self, body):
        return self.delegate.normalize(body)

    def send(self, request):
        body = {
            "id": "r",
            "model": "test-model-2026-01-01",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "observable answer"}],
                }
            ],
            "usage": {},
        }
        return ProviderResponse(200, {}, canonical_json_bytes(body), body)


def completed_wave(wave_factory):
    manifest, battery, lock, schedule = wave_factory(replications=1)
    run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        ignore_planned_time=True,
        adapter_factory=lambda provider: AlwaysAdapter(),
        sleep=lambda seconds: None,
    )
    return manifest, battery, lock, schedule


def test_qc_canonical_certificate_and_blind_traceability(wave_factory):
    manifest, battery, lock, schedule = completed_wave(wave_factory)
    report = run_qc(manifest, battery, lock, schedule)
    assert report["passed"] is True
    assert report["completion_classification"] == "complete"
    certificate = create_certificate(
        manifest.source.parent,
        manifest_sha256=manifest.content_sha256,
        battery_sha256=battery.content_sha256,
        model_lock_sha256=lock["model_lock_sha256"],
        schedule_sha256=schedule["schedule_sha256"],
    )
    assert certificate["L0_artifact_count"] > 0
    exported = export_blind(manifest.source.parent, salt="sixteen-character-salt")
    text = open(exported["export"], encoding="utf-8").read()
    assert "test-model-2026-01-01" not in text
    assert "SERIES-1" not in text
    assert "MODEL-" in text


def test_qc_detects_L0_tampering(wave_factory):
    manifest, battery, lock, schedule = completed_wave(wave_factory)
    request_body = next((manifest.source.parent / "L0_raw").rglob("*.request.body"))
    request_body.write_bytes(b"tampered")
    report = run_qc(manifest, battery, lock, schedule)
    assert report["passed"] is False
    assert any("request body hash mismatch" in value for value in report["errors"])


def test_sensitive_model_output_is_preserved_in_L0_but_quarantined_from_L1(
    wave_factory, monkeypatch
):
    secret = "a-real-provider-secret-value"  # noqa: S105 - synthetic QC fixture
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    manifest, battery, lock, schedule = wave_factory(replications=1)

    class SensitiveAdapter(AlwaysAdapter):
        def send(self, request):
            body = {
                "id": "r",
                "model": "test-model-2026-01-01",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": secret}],
                    }
                ],
                "usage": {},
            }
            return ProviderResponse(200, {}, canonical_json_bytes(body), body)

    run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=1,
        ignore_planned_time=True,
        adapter_factory=lambda provider: SensitiveAdapter(),
        sleep=lambda seconds: None,
    )
    response_body = next((manifest.source.parent / "L0_raw").rglob("*.response.body"))
    assert secret.encode() in response_body.read_bytes()
    report = run_qc(manifest, battery, lock, schedule)
    assert report["passed"] is False
    assert report["canonical_sha256"] is None
    assert any("secret-redaction" in error for error in report["errors"])

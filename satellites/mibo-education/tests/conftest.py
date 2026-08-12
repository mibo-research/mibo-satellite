from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from miboe.artifacts import load_battery, load_manifest, load_registry
from miboe.scheduling import create_schedule
from miboe.util import artifact_hash, sha256_text


@pytest.fixture
def wave_factory(tmp_path: Path):
    def factory(*, provider: str = "openai", replications: int = 2):
        root = tmp_path / f"wave-{provider}-{replications}"
        root.mkdir()
        prompts = ["教育工学の試験プロンプトA", "教育工学の試験プロンプトB"]
        battery_raw = {
            "battery_id": "TEST",
            "version": "1",
            "status": "engineering-only",
            "approved": True,
            "official_longitudinal_eligible": False,
            "expected_item_count": 2,
            "items": [
                {
                    "id": f"T{i + 1}",
                    "stratum": "a" if i == 0 else "b",
                    "frozen": True,
                    "prompt_ja": prompt,
                    "prompt_sha256": sha256_text(prompt),
                }
                for i, prompt in enumerate(prompts)
            ],
        }
        (root / "battery.yaml").write_text(
            yaml.safe_dump(battery_raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        registry_raw = {
            "registry_id": "TEST",
            "version": "1",
            "status": "engineering",
            "approved": False,
            "series": [
                {
                    "series_id": "SERIES-1",
                    "provider": provider,
                    "label": "Test",
                    "closed_eligibility": True,
                }
            ],
        }
        (root / "registry.yaml").write_text(
            yaml.safe_dump(registry_raw, sort_keys=False), encoding="utf-8"
        )
        manifest_raw = {
            "schema_version": "1",
            "wave_id": "MIBO-EDU-W0",
            "site_id": "MIBO-SITE-TEST",
            "official_longitudinal_data": False,
            "protocol_version": "test",
            "battery": "battery.yaml",
            "model_registry": "registry.yaml",
            "model_lock": "model-lock.json",
            "schedule": "schedule.json",
            "environment": "CLOSED",
            "replications": replications,
            "random_seed": "test-seed",
            "field_window": {"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T00:00:00Z"},
            "sampling": {},
            "native_options": {},
            "max_technical_attempts": 3,
            "retry_delays_minutes": [10, 30],
            "approvals": {},
        }
        if provider == "anthropic":
            manifest_raw["sampling"] = {"anthropic": {"max_tokens": 64}}
        manifest_path = root / "manifest.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest_raw, sort_keys=False), encoding="utf-8")
        manifest = load_manifest(manifest_path)
        registry = load_registry(manifest.registry_path)
        lock_core = {
            "schema_version": "1.0",
            "wave_id": manifest.wave_id,
            "registry_sha256": registry["registry_sha256"],
            "resolved_at": "2026-01-01T00:00:00Z",
            "models": [
                {
                    "series_id": "SERIES-1",
                    "provider": provider,
                    "requested_model": "test-model-2026-01-01",
                    "live_verified": True,
                    "pinning_evidence": "test evidence",
                    "pinning_verified": True,
                    "provider_metadata": {"id": "test-model-2026-01-01"},
                }
            ],
        }
        lock = {**lock_core, "model_lock_sha256": artifact_hash(lock_core)}
        manifest.model_lock_path.write_text(json.dumps(lock), encoding="utf-8")
        battery = load_battery(manifest.battery_path)
        schedule = create_schedule(manifest, battery, lock)
        return manifest, battery, lock, schedule

    return factory

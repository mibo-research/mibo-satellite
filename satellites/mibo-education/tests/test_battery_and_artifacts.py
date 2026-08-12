from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from miboe.artifacts import load_battery, load_manifest
from miboe.errors import ValidationError
from miboe.util import sha256_text


def test_official_placeholder_fails_closed() -> None:
    path = Path(__file__).parents[1] / "battery" / "ebb-ja-v1.0.yaml"
    with pytest.raises(ValidationError, match="0 items; expected 70"):
        load_battery(path)


def test_every_frozen_prompt_hash_is_validated(tmp_path: Path) -> None:
    prompt = "正確な固定文"
    raw = {
        "battery_id": "X",
        "version": "1",
        "status": "frozen",
        "approved": True,
        "expected_item_count": 1,
        "items": [
            {
                "id": "I1",
                "stratum": "x",
                "frozen": True,
                "prompt_ja": prompt,
                "prompt_sha256": sha256_text(prompt),
            }
        ],
    }
    path = tmp_path / "battery.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    assert load_battery(path).items[0].prompt_sha256 == sha256_text(prompt)
    raw["items"][0]["prompt_ja"] += "改変"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError, match="hash mismatch"):
        load_battery(path)


def test_closed_manifest_rejects_native_options(tmp_path: Path) -> None:
    raw = {
        "wave_id": "MIBO-EDU-W0",
        "site_id": "MIBO-SITE-X",
        "official_longitudinal_data": False,
        "protocol_version": "x",
        "battery": "x",
        "model_registry": "x",
        "model_lock": "x",
        "schedule": "x",
        "environment": "CLOSED",
        "replications": 1,
        "random_seed": "x",
        "field_window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        "native_options": {"openai": {"tools": []}},
    }
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError, match="native_options"):
        load_manifest(path)

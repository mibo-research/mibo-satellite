from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import pytest
import yaml

from miboe.artifacts import (
    EBB_JA_V1_IDS,
    load_battery,
    load_manifest,
    load_scientific_artifact_registry,
)
from miboe.errors import ValidationError
from miboe.util import sha256_file, sha256_text


def synthetic_ebb() -> dict:
    items = []
    for item_id in EBB_JA_V1_IDS:
        prompt = f"TEST ONLY — synthetic prompt {item_id}"
        items.append(
            {
                "id": item_id,
                "stratum": item_id.split("-", 1)[0],
                "frozen": True,
                "prompt_ja": prompt,
                "prompt_sha256": sha256_text(prompt),
            }
        )
    return {
        "battery_id": "EBB-JA",
        "version": "1.0",
        "status": "FROZEN",
        "approved": True,
        "official_longitudinal_eligible": True,
        "expected_item_count": 70,
        "items": items,
    }


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


def test_ebb_has_exact_canonical_ids_and_ten_items_per_domain(tmp_path: Path) -> None:
    path = tmp_path / "ebb.yaml"
    path.write_text(
        yaml.safe_dump(synthetic_ebb(), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    battery = load_battery(path)
    assert tuple(item.item_id for item in battery.items) == EBB_JA_V1_IDS
    assert Counter(item.item_id.split("-", 1)[0] for item in battery.items) == {
        f"E{domain}": 10 for domain in range(1, 8)
    }


@pytest.mark.parametrize("replacement", ["E1-01", "E7-11"])
def test_ebb_rejects_duplicate_or_noncanonical_item_ids(tmp_path: Path, replacement: str) -> None:
    raw = synthetic_ebb()
    raw["items"][-1]["id"] = replacement
    path = tmp_path / "ebb.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate|exactly E1-01"):
        load_battery(path)


def test_prompt_hash_uses_exact_utf8_bytes_without_normalization() -> None:
    composed = "é"
    decomposed = "e\u0301"
    assert sha256_text(composed) == hashlib.sha256(composed.encode("utf-8")).hexdigest()
    assert sha256_text(composed) != sha256_text(decomposed)
    assert sha256_text(composed) != sha256_text(composed + "\n")


def test_external_freeze_hash_rejects_prompt_and_embedded_hash_rewrite(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol"
    battery_dir = tmp_path / "battery"
    waves = tmp_path / "waves" / "W01"
    protocol.mkdir()
    battery_dir.mkdir()
    waves.mkdir(parents=True)
    battery_path = battery_dir / "ebb-ja-v1.0.yaml"
    battery_path.write_text(
        yaml.safe_dump(synthetic_ebb(), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    paths = {
        "ebb_ja_v1_0": battery_path,
        "codebook_v1_0": protocol / "codebook.md",
        "scoring_manual_v1_0": protocol / "scoring.md",
        "observation_protocol_v1_0": protocol / "observation.md",
        "w01_wave_manifest": waves / "manifest.yaml",
    }
    for artifact_id, path in paths.items():
        if artifact_id != "ebb_ja_v1_0":
            path.write_text(f"TEST ONLY {artifact_id}\n", encoding="utf-8")
    registry = {
        "schema_version": "1.0",
        "registry_id": "TEST",
        "status": "FROZEN",
        "artifacts": {
            artifact_id: {
                "title": artifact_id,
                "expected_path": str(path),
                "status": "FROZEN",
                "approved": True,
                "sha256": sha256_file(path),
            }
            for artifact_id, path in paths.items()
        },
    }
    registry_path = protocol / "scientific-artifacts.yaml"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    load_scientific_artifact_registry(registry_path)

    raw = synthetic_ebb()
    raw["items"][0]["prompt_ja"] += " silently changed"
    raw["items"][0]["prompt_sha256"] = sha256_text(raw["items"][0]["prompt_ja"])
    battery_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="FROZEN artifact hash mismatch"):
        load_scientific_artifact_registry(registry_path)


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


def test_w0_can_never_be_marked_official(tmp_path: Path) -> None:
    raw = {
        "status": "ENGINEERING",
        "approved": False,
        "wave_id": "MIBO-EDU-W0",
        "site_id": "MIBO-SITE-X",
        "official_longitudinal_data": True,
        "protocol_version": "x",
        "battery": "x",
        "model_registry": "x",
        "model_lock": "x",
        "schedule": "x",
        "environment": "CLOSED",
        "replications": 1,
        "random_seed": "x",
        "field_window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
    }
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError, match="W0 can never be official"):
        load_manifest(path)

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
import yaml

from miboe.artifacts import (
    EBB_JA_V1_IDS,
    REQUIRED_SCIENTIFIC_ARTIFACTS,
    load_battery,
    load_manifest,
    load_prompt_lock,
    load_scientific_artifact_registry,
)
from miboe.errors import ValidationError
from miboe.util import sha256_file, sha256_text

MODULE_ROOT = Path(__file__).parents[1]
EXPECTED_ARTIFACT_HASHES = {
    "EBB-JA-v1.0": "5475d4c0edd651ae4fbc6e79c42642433fa7e0c27dba616a972236d35517cd4e",
    "MIBO-Education-Codebook-v1.0": (
        "c38cce32bad4e3b156ec6094d2368fca0937536519b25a2a80e115042da9161a"
    ),
    "MIBO-Education-Item-Level-Scoring-Manual-v1.0": (
        "3ae057c2e5f23312b5ca000f3d9f42ced4db23ca6b6db8c4889905c9f9a0bbef"
    ),
    "MIBO-Education-Observation-Protocol-v1.0": (
        "ca9b51ecbca1f5fd61443e7921ff4305dac82829a3043c795416c437b20d5d8f"
    ),
    "MIBO-Education-W01-Scientific-Manifest-v1.0": (
        "ecb5b5aa779d0806cb034581d76ab1c128587f1b9590a7b482fc3fa93336a6f1"
    ),
}
EXPECTED_PROMPT_LOCK_HASH = "8e251463eebb1c2e3f86ae7e82d98a4685afbf2dd3434731cdc72939d6ef6a82"


def synthetic_ebb() -> dict:
    items = []
    for item_id in EBB_JA_V1_IDS:
        prompt = f"TEST ONLY synthetic prompt {item_id}"
        items.append(
            {
                "id": item_id,
                "domain": item_id.split("-", 1)[0],
                "prompt": prompt,
                "prompt_sha256": sha256_text(prompt),
            }
        )
    return {
        "artifact": "EBB-JA",
        "version": "1.0",
        "status": "FROZEN",
        "domains": {
            f"E{domain}": {"item_count": 10} for domain in range(1, 8)
        },
        "items": items,
    }


def write_synthetic_ebb(path: Path, raw: dict | None = None) -> None:
    value = raw or synthetic_ebb()
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    lock = {"items": {item["id"]: item["prompt_sha256"] for item in value["items"]}}
    path.with_suffix(".prompt-lock.json").write_text(
        json.dumps(lock, ensure_ascii=False), encoding="utf-8"
    )


def test_authoritative_artifact_hashes_are_exact() -> None:
    registry = load_scientific_artifact_registry(
        MODULE_ROOT / "protocol" / "scientific-artifacts.yaml"
    )
    assert set(registry["artifacts"]) == set(EXPECTED_ARTIFACT_HASHES)
    for artifact_id, expected_hash in EXPECTED_ARTIFACT_HASHES.items():
        artifact = registry["artifacts"][artifact_id]
        assert artifact["sha256"] == expected_hash
        assert sha256_file(artifact["resolved_path"]) == expected_hash


def test_authoritative_battery_and_external_prompt_lock() -> None:
    battery_path = MODULE_ROOT / "battery" / "ebb-ja-v1.0.yaml"
    lock_path = MODULE_ROOT / "battery" / "ebb-ja-v1.0.prompt-lock.json"
    battery = load_battery(battery_path)
    lock = load_prompt_lock(lock_path)
    assert sha256_file(lock_path) == EXPECTED_PROMPT_LOCK_HASH
    assert len(battery.items) == 70
    assert tuple(item.item_id for item in battery.items) == EBB_JA_V1_IDS
    assert Counter(item.stratum for item in battery.items) == {
        f"E{domain}": 10 for domain in range(1, 8)
    }
    assert {item.item_id: item.prompt_sha256 for item in battery.items} == lock


def test_every_frozen_prompt_hash_is_validated(tmp_path: Path) -> None:
    prompt = "exact UTF-8 prompt"
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
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert load_battery(path).items[0].prompt_sha256 == sha256_text(prompt)
    raw["items"][0]["prompt_ja"] += " changed"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError, match="hash mismatch"):
        load_battery(path)


def test_ebb_has_exact_canonical_ids_and_ten_items_per_domain(tmp_path: Path) -> None:
    path = tmp_path / "ebb-ja-v1.0.yaml"
    write_synthetic_ebb(path)
    battery = load_battery(path)
    assert tuple(item.item_id for item in battery.items) == EBB_JA_V1_IDS
    assert Counter(item.stratum for item in battery.items) == {
        f"E{domain}": 10 for domain in range(1, 8)
    }


@pytest.mark.parametrize("replacement", ["E1-01", "E7-11"])
def test_ebb_rejects_duplicate_or_noncanonical_item_ids(
    tmp_path: Path, replacement: str
) -> None:
    raw = synthetic_ebb()
    raw["items"][-1]["id"] = replacement
    path = tmp_path / "ebb-ja-v1.0.yaml"
    write_synthetic_ebb(path, raw)
    with pytest.raises(ValidationError, match="duplicate|exactly E1-01"):
        load_battery(path)


def test_prompt_hash_uses_exact_utf8_bytes_without_normalization() -> None:
    composed = "é"
    decomposed = "e\u0301"
    assert sha256_text(composed) == hashlib.sha256(composed.encode("utf-8")).hexdigest()
    assert sha256_text(composed) != sha256_text(decomposed)
    assert sha256_text(composed) != sha256_text(composed + "\n")


def test_external_prompt_lock_independently_rejects_embedded_hash_rewrite(
    tmp_path: Path,
) -> None:
    source = MODULE_ROOT / "battery" / "ebb-ja-v1.0.yaml"
    target = tmp_path / source.name
    shutil.copyfile(source, target)
    shutil.copyfile(
        source.with_suffix(".prompt-lock.json"),
        target.with_suffix(".prompt-lock.json"),
    )
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    raw["items"][0]["prompt"] += " changed"
    raw["items"][0]["prompt_sha256"] = sha256_text(raw["items"][0]["prompt"])
    target.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="external Frozen prompt lock mismatch"):
        load_battery(target)


def test_external_artifact_registry_rejects_frozen_file_rewrite(tmp_path: Path) -> None:
    for relative in [
        *REQUIRED_SCIENTIFIC_ARTIFACTS.values(),
        "battery/ebb-ja-v1.0.prompt-lock.json",
        "waves/W01/runtime-manifest.template.yaml",
        "protocol/scientific-artifacts.yaml",
    ]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MODULE_ROOT / relative, target)
    codebook = tmp_path / "protocol" / "codebook-v1.0.md"
    codebook.write_bytes(codebook.read_bytes() + b"changed")
    with pytest.raises(ValidationError, match="FROZEN artifact hash mismatch"):
        load_scientific_artifact_registry(tmp_path / "protocol" / "scientific-artifacts.yaml")


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
        "field_window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
        "native_options": {"openai": {"tools": []}},
    }
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError, match="native_options"):
        load_manifest(path)


def test_manifest_accepts_protocol_maximum_five_technical_attempts(
    tmp_path: Path,
) -> None:
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
        "max_technical_attempts": 5,
        "retry_delays_minutes": [1, 2, 4, 8],
        "field_window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
    }
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert load_manifest(path).max_attempts == 5


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

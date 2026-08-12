from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .errors import ValidationError
from .util import artifact_hash, sha256_text


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"YAML root must be a mapping: {path}")
    return value


@dataclass(frozen=True)
class BatteryItem:
    item_id: str
    stratum: str
    prompt: str
    prompt_sha256: str


@dataclass(frozen=True)
class Battery:
    battery_id: str
    version: str
    status: str
    approved: bool
    official_eligible: bool
    expected_count: int
    items: tuple[BatteryItem, ...]
    content_sha256: str


def load_battery(path: Path, *, require_complete: bool = True) -> Battery:
    raw = load_yaml(path)
    values = raw.get("items")
    if not isinstance(values, list):
        raise ValidationError("battery items must be a list")
    expected = int(raw.get("expected_item_count", 70))
    if require_complete and len(values) != expected:
        raise ValidationError(f"battery has {len(values)} items; expected {expected}")
    seen: set[str] = set()
    items: list[BatteryItem] = []
    for number, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"battery item {number} must be a mapping")
        item_id, prompt = item.get("id"), item.get("prompt_ja")
        if not isinstance(item_id, str) or not isinstance(prompt, str) or not prompt:
            raise ValidationError(f"battery item {number} has invalid id or prompt")
        if item_id in seen:
            raise ValidationError(f"duplicate battery item ID: {item_id}")
        seen.add(item_id)
        if item.get("frozen") is not True:
            raise ValidationError(f"item {item_id} is not Frozen")
        actual = sha256_text(prompt)
        if item.get("prompt_sha256") != actual:
            raise ValidationError(f"Frozen prompt hash mismatch: {item_id}")
        items.append(BatteryItem(item_id, str(item.get("stratum", "")), prompt, actual))
    return Battery(
        battery_id=str(raw.get("battery_id", "")),
        version=str(raw.get("version", "")),
        status=str(raw.get("status", "")),
        approved=raw.get("approved") is True,
        official_eligible=raw.get("official_longitudinal_eligible", True) is True,
        expected_count=expected,
        items=tuple(items),
        content_sha256=artifact_hash(raw),
    )


@dataclass(frozen=True)
class WaveManifest:
    source: Path
    wave_id: str
    site_id: str
    official: bool
    protocol_version: str
    battery_path: Path
    registry_path: Path
    model_lock_path: Path
    schedule_path: Path
    environment: str
    replications: int
    random_seed: str
    start: datetime
    end: datetime
    sampling: dict[str, dict[str, Any]]
    native_options: dict[str, dict[str, Any]]
    max_attempts: int
    retry_delays_minutes: tuple[int, ...]
    approvals: dict[str, bool]
    scientific_artifacts: dict[str, Path]
    content_sha256: str


def load_manifest(path: Path) -> WaveManifest:
    raw = load_yaml(path)
    try:
        base = path.parent
        start = datetime.fromisoformat(str(raw["field_window"]["start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(raw["field_window"]["end"]).replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("field window needs timezone offsets and end > start")
        environment = str(raw["environment"]).upper()
        if environment not in {"CLOSED", "NATIVE"}:
            raise ValueError("environment must be CLOSED or NATIVE")
        if environment == "CLOSED" and raw.get("native_options"):
            raise ValueError("native_options are forbidden in CLOSED")
        replications = int(raw["replications"])
        max_attempts = int(raw.get("max_technical_attempts", 3))
        if not 1 <= replications <= 100 or not 1 <= max_attempts <= 3:
            raise ValueError("replications must be 1..100 and attempts 1..3")
        delays = tuple(int(value) for value in raw.get("retry_delays_minutes", [10, 30]))
        if len(delays) < max_attempts - 1 or any(value < 0 for value in delays):
            raise ValueError("retry delay list is too short or negative")
        science = {
            key: (base / value).resolve()
            for key, value in (raw.get("scientific_artifacts") or {}).items()
        }
        return WaveManifest(
            source=path.resolve(),
            wave_id=str(raw["wave_id"]),
            site_id=str(raw["site_id"]),
            official=raw["official_longitudinal_data"] is True,
            protocol_version=str(raw["protocol_version"]),
            battery_path=(base / raw["battery"]).resolve(),
            registry_path=(base / raw["model_registry"]).resolve(),
            model_lock_path=(base / raw["model_lock"]).resolve(),
            schedule_path=(base / raw["schedule"]).resolve(),
            environment=environment,
            replications=replications,
            random_seed=str(raw["random_seed"]),
            start=start,
            end=end,
            sampling=dict(raw.get("sampling") or {}),
            native_options=dict(raw.get("native_options") or {}),
            max_attempts=max_attempts,
            retry_delays_minutes=delays,
            approvals={key: value is True for key, value in (raw.get("approvals") or {}).items()},
            scientific_artifacts=science,
            content_sha256=artifact_hash(raw),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"invalid Wave Manifest {path}: {exc}") from exc


def load_registry(path: Path) -> dict[str, Any]:
    raw = load_yaml(path)
    series = raw.get("series")
    if not isinstance(series, list) or not series:
        raise ValidationError("model-series registry must contain entries")
    ids = [value.get("series_id") for value in series if isinstance(value, dict)]
    if len(ids) != len(series) or len(ids) != len(set(ids)):
        raise ValidationError("model-series registry has invalid or duplicate IDs")
    raw["registry_sha256"] = artifact_hash(
        {key: value for key, value in raw.items() if key != "registry_sha256"}
    )
    return raw

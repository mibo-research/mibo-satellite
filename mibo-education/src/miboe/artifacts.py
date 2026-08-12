from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .errors import ValidationError
from .util import artifact_hash, sha256_file, sha256_text

EBB_JA_V1_IDS = tuple(f"E{domain}-{item:02d}" for domain in range(1, 8) for item in range(1, 11))
REQUIRED_SCIENTIFIC_ARTIFACTS = frozenset(
    {
        "ebb_ja_v1_0",
        "codebook_v1_0",
        "scoring_manual_v1_0",
        "observation_protocol_v1_0",
        "w01_wave_manifest",
    }
)


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
    battery_id = str(raw.get("battery_id", ""))
    version = str(raw.get("version", ""))
    if battery_id == "EBB-JA" and version == "1.0" and require_complete:
        item_ids = tuple(item.item_id for item in items)
        if expected != 70 or item_ids != EBB_JA_V1_IDS:
            raise ValidationError(
                "EBB-JA v1.0 IDs must be exactly E1-01 through E7-10 in canonical order"
            )
        domain_counts = Counter(item_id.split("-", 1)[0] for item_id in item_ids)
        expected_domains = {f"E{domain}": 10 for domain in range(1, 8)}
        if domain_counts != expected_domains:
            raise ValidationError("EBB-JA v1.0 must contain exactly 10 items in each domain E1-E7")
    return Battery(
        battery_id=battery_id,
        version=version,
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
    status: str
    approved: bool
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
    scientific_registry_path: Path | None
    content_sha256: str


def load_manifest(path: Path) -> WaveManifest:
    raw = load_yaml(path)
    try:
        base = path.parent
        start = datetime.fromisoformat(str(raw["field_window"]["start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(raw["field_window"]["end"]).replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("field window needs timezone offsets and end > start")
        wave_id = str(raw["wave_id"])
        official = raw["official_longitudinal_data"] is True
        if wave_id == "MIBO-EDU-W0" and official:
            raise ValueError("W0 can never be official longitudinal data")
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
            status=str(raw.get("status", "UNSPECIFIED")).upper(),
            approved=raw.get("approved") is True,
            wave_id=wave_id,
            site_id=str(raw["site_id"]),
            official=official,
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
            scientific_registry_path=(
                (base / raw["scientific_artifact_registry"]).resolve()
                if raw.get("scientific_artifact_registry")
                else None
            ),
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


def load_scientific_artifact_registry(path: Path) -> dict[str, Any]:
    raw = load_yaml(path)
    registry_status = str(raw.get("status", "")).upper()
    if registry_status not in {"BLOCKED", "FROZEN"}:
        raise ValidationError("scientific artifact registry status must be BLOCKED or FROZEN")
    raw["status"] = registry_status
    registry_sha256 = artifact_hash(
        {key: value for key, value in raw.items() if key != "registry_sha256"}
    )
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValidationError("scientific artifact registry must contain an artifacts mapping")
    if set(artifacts) != REQUIRED_SCIENTIFIC_ARTIFACTS:
        missing = sorted(REQUIRED_SCIENTIFIC_ARTIFACTS - set(artifacts))
        extra = sorted(set(artifacts) - REQUIRED_SCIENTIFIC_ARTIFACTS)
        raise ValidationError(
            f"scientific artifact registry keys differ; missing={missing}, extra={extra}"
        )
    resolved: dict[str, Any] = {}
    for artifact_id, value in artifacts.items():
        if not isinstance(value, dict):
            raise ValidationError(f"scientific artifact entry must be a mapping: {artifact_id}")
        status = str(value.get("status", "")).upper()
        approved = value.get("approved") is True
        relative = value.get("expected_path")
        if status not in {"BLOCKED", "FROZEN"} or not isinstance(relative, str):
            raise ValidationError(f"invalid scientific artifact state: {artifact_id}")
        expected_path = (path.parent / relative).resolve()
        claimed_hash = value.get("sha256")
        if status == "BLOCKED":
            if approved or claimed_hash is not None or not value.get("blocker"):
                raise ValidationError(
                    "BLOCKED artifact must be unapproved, unhashed, and explain its "
                    f"blocker: {artifact_id}"
                )
        else:
            if not approved:
                raise ValidationError(f"FROZEN artifact is not approved: {artifact_id}")
            if not isinstance(claimed_hash, str) or len(claimed_hash) != 64:
                raise ValidationError(f"FROZEN artifact has no valid SHA-256: {artifact_id}")
            if not expected_path.is_file():
                raise ValidationError(f"FROZEN artifact file is missing: {artifact_id}")
            if sha256_file(expected_path) != claimed_hash:
                raise ValidationError(f"FROZEN artifact hash mismatch: {artifact_id}")
        resolved[artifact_id] = {
            **value,
            "status": status,
            "approved": approved,
            "resolved_path": expected_path,
        }
    raw["artifacts"] = resolved
    raw["registry_sha256"] = registry_sha256
    return raw

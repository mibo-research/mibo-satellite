from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .errors import ValidationError
from .util import artifact_hash, load_json, sha256_file, sha256_text

EBB_JA_V1_IDS = tuple(f"E{domain}-{item:02d}" for domain in range(1, 8) for item in range(1, 11))
REQUIRED_SCIENTIFIC_ARTIFACTS = {
    "EBB-JA-v1.0": "battery/ebb-ja-v1.0.yaml",
    "MIBO-Education-Codebook-v1.0": "protocol/codebook-v1.0.md",
    "MIBO-Education-Item-Level-Scoring-Manual-v1.0": (
        "protocol/item-level-scoring-manual-v1.0.md"
    ),
    "MIBO-Education-Observation-Protocol-v1.0": "protocol/observation-protocol-v1.0.md",
    "MIBO-Education-W01-Scientific-Manifest-v1.0": (
        "waves/W01/scientific-manifest-v1.0.yaml"
    ),
}


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


def load_prompt_lock(path: Path) -> dict[str, str]:
    try:
        raw = load_json(path)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"cannot load Frozen prompt lock {path}: {exc}") from exc
    values = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(values, dict) or tuple(values) != EBB_JA_V1_IDS:
        raise ValidationError("Frozen prompt lock IDs must be exactly E1-01 through E7-10")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in values.values()
    ):
        raise ValidationError("Frozen prompt lock contains an invalid SHA-256")
    return values


def load_battery(path: Path, *, require_complete: bool = True) -> Battery:
    raw = load_yaml(path)
    values = raw.get("items")
    if not isinstance(values, list):
        raise ValidationError("battery items must be a list")
    battery_id = str(raw.get("battery_id") or raw.get("artifact") or "")
    version = str(raw.get("version", ""))
    authoritative_ebb = battery_id == "EBB-JA" and version == "1.0"
    expected = int(raw.get("expected_item_count", 70 if authoritative_ebb else len(values)))
    if require_complete and len(values) != expected:
        raise ValidationError(f"battery has {len(values)} items; expected {expected}")
    seen: set[str] = set()
    items: list[BatteryItem] = []
    for number, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"battery item {number} must be a mapping")
        item_id = item.get("id")
        prompt = item.get("prompt") if authoritative_ebb else item.get("prompt_ja")
        if not isinstance(item_id, str) or not isinstance(prompt, str) or not prompt:
            raise ValidationError(f"battery item {number} has invalid id or prompt")
        if item_id in seen:
            raise ValidationError(f"duplicate battery item ID: {item_id}")
        seen.add(item_id)
        if not authoritative_ebb and item.get("frozen") is not True:
            raise ValidationError(f"item {item_id} is not Frozen")
        actual = sha256_text(prompt)
        if item.get("prompt_sha256") != actual:
            raise ValidationError(f"Frozen prompt hash mismatch: {item_id}")
        stratum = item.get("domain") if authoritative_ebb else item.get("stratum", "")
        items.append(BatteryItem(item_id, str(stratum), prompt, actual))
    if authoritative_ebb and require_complete:
        if str(raw.get("status", "")).upper() != "FROZEN":
            raise ValidationError("EBB-JA v1.0 is not FROZEN")
        item_ids = tuple(item.item_id for item in items)
        if expected != 70 or item_ids != EBB_JA_V1_IDS:
            raise ValidationError(
                "EBB-JA v1.0 IDs must be exactly E1-01 through E7-10 in canonical order"
            )
        domain_counts = Counter(item_id.split("-", 1)[0] for item_id in item_ids)
        expected_domains = {f"E{domain}": 10 for domain in range(1, 8)}
        if domain_counts != expected_domains:
            raise ValidationError("EBB-JA v1.0 must contain exactly 10 items in each domain E1-E7")
        domains = raw.get("domains")
        if not isinstance(domains, dict) or {
            key: value.get("item_count") if isinstance(value, dict) else None
            for key, value in domains.items()
        } != expected_domains:
            raise ValidationError("EBB-JA v1.0 domain metadata must declare 10 items in E1-E7")
        external = load_prompt_lock(path.with_suffix(".prompt-lock.json"))
        for item in items:
            if external[item.item_id] != item.prompt_sha256:
                raise ValidationError(f"external Frozen prompt lock mismatch: {item.item_id}")
    return Battery(
        battery_id=battery_id,
        version=version,
        status=str(raw.get("status", "")),
        approved=(
            str(raw.get("status", "")).upper() == "FROZEN"
            if authoritative_ebb
            else raw.get("approved") is True
        ),
        official_eligible=(
            True
            if authoritative_ebb
            else raw.get("official_longitudinal_eligible", True) is True
        ),
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
        if not 1 <= replications <= 100 or not 1 <= max_attempts <= 5:
            raise ValueError("replications must be 1..100 and attempts 1..5")
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
    if registry_status != "FROZEN":
        raise ValidationError("authoritative scientific artifact registry must be FROZEN")
    raw["status"] = registry_status
    registry_sha256 = artifact_hash(
        {key: value for key, value in raw.items() if key != "registry_sha256"}
    )
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValidationError("scientific artifact registry must contain an artifacts list")
    entries = {
        value.get("artifact_id"): value for value in artifacts if isinstance(value, dict)
    }
    if len(entries) != len(artifacts):
        raise ValidationError("scientific artifact registry has invalid or duplicate artifact IDs")
    if set(entries) != set(REQUIRED_SCIENTIFIC_ARTIFACTS):
        missing = sorted(set(REQUIRED_SCIENTIFIC_ARTIFACTS) - set(entries))
        extra = sorted(set(entries) - set(REQUIRED_SCIENTIFIC_ARTIFACTS))
        raise ValidationError(
            f"scientific artifact registry keys differ; missing={missing}, extra={extra}"
        )
    module_root = path.parent.parent.resolve()
    resolved: dict[str, Any] = {}
    for artifact_id, required_path in REQUIRED_SCIENTIFIC_ARTIFACTS.items():
        value = entries[artifact_id]
        status = str(value.get("status", "")).upper()
        relative = value.get("path")
        if status != "FROZEN" or relative != required_path:
            raise ValidationError(f"invalid authoritative artifact state or path: {artifact_id}")
        if value.get("required_for_scientific_protocol_complete") is not True:
            raise ValidationError(f"artifact is not required by the readiness gate: {artifact_id}")
        expected_path = (module_root / required_path).resolve()
        claimed_hash = value.get("sha256")
        if (
            not isinstance(claimed_hash, str)
            or len(claimed_hash) != 64
            or any(character not in "0123456789abcdef" for character in claimed_hash)
        ):
            raise ValidationError(f"FROZEN artifact has no valid SHA-256: {artifact_id}")
        if not expected_path.is_file():
            raise ValidationError(f"FROZEN artifact file is missing: {artifact_id}")
        if sha256_file(expected_path) != claimed_hash:
            raise ValidationError(f"FROZEN artifact hash mismatch: {artifact_id}")
        resolved[artifact_id] = {
            **value,
            "status": status,
            "approved": True,
            "resolved_path": expected_path,
        }
    supporting = raw.get("supporting_integrity_files")
    required_supporting = {
        "battery/ebb-ja-v1.0.prompt-lock.json",
        "waves/W01/runtime-manifest.template.yaml",
    }
    supporting_paths = {
        value.get("path") for value in supporting or [] if isinstance(value, dict)
    }
    if supporting_paths != required_supporting:
        raise ValidationError("scientific artifact registry has invalid supporting integrity files")
    for relative in required_supporting:
        if not (module_root / relative).is_file():
            raise ValidationError(f"supporting integrity file is missing: {relative}")
    validate_scientific_manifest(module_root / REQUIRED_SCIENTIFIC_ARTIFACTS[
        "MIBO-Education-W01-Scientific-Manifest-v1.0"
    ])
    raw["artifacts"] = resolved
    raw["registry_sha256"] = registry_sha256
    return raw


def validate_scientific_manifest(path: Path) -> dict[str, Any]:
    """Validate the immutable W01 scientific design without resolving runtime locks."""
    raw = load_yaml(path)
    try:
        wave = raw["wave"]
        observation = raw["observation"]
        environments = raw["environments"]
        schedule = raw["schedule"]
        observer = raw["observer"]
        model_lock = raw["model_lock"]
        series = raw["series_registry_contract"]
        expected = raw["expected_observations"]
        if raw.get("artifact") != "MIBO-Education W01 Wave Manifest":
            raise ValueError("unexpected artifact identifier")
        if str(raw.get("version")) != "1.0" or raw.get("status") != "FROZEN_SCIENTIFIC":
            raise ValueError("scientific manifest is not FROZEN_SCIENTIFIC v1.0")
        if raw.get("execution_state") != "BLOCKED_UNTIL_OPERATIONAL_LOCKS":
            raise ValueError("scientific manifest must remain blocked on runtime locks")
        if wave.get("wave_id") != "W01" or wave.get("official_longitudinal_data") is not True:
            raise ValueError("invalid W01 identity")
        if wave.get("target_window_hours") != 12 or wave.get("hard_window_hours") != 24:
            raise ValueError("invalid W01 observation window")
        scientific_artifacts = raw["scientific_artifacts"]
        expected_scientific_artifacts = {
            "battery": "EBB-JA-v1.0",
            "codebook": "MIBO-Education-Codebook-v1.0",
            "item_scoring_manual": "MIBO-Education-Item-Level-Scoring-Manual-v1.0",
            "observation_protocol": "MIBO-Education-Observation-Protocol-v1.0",
        }
        if scientific_artifacts != expected_scientific_artifacts:
            raise ValueError("invalid scientific artifact bindings")
        required_observation = {
            "frozen_item_count": 70,
            "replication_k": 10,
            "session": "independent_single_turn",
            "conversation_history": False,
            "researcher_added_system_prompt": False,
            "researcher_added_developer_prompt": False,
            "personalization": False,
            "memory": False,
            "structured_output": False,
            "streaming": False,
            "sampling_policy": "provider_native_default_unless_required",
            "optional_sampling_overrides": False,
            "optional_reasoning_overrides": False,
            "technical_retry_max_attempts": 5,
        }
        if any(observation.get(key) != value for key, value in required_observation.items()):
            raise ValueError("scientific observation invariants differ from v1.0")
        closed = environments["closed_primary"]
        if closed.get("series") != ["M01", "M02", "M03", "M04"]:
            raise ValueError("invalid CLOSED series panel")
        forbidden_closed_features = (
            "tools",
            "web",
            "retrieval",
            "rag",
            "files",
            "memory",
            "external_functions",
        )
        for forbidden in forbidden_closed_features:
            if closed.get(forbidden) is not False:
                raise ValueError(f"CLOSED must disable {forbidden}")
        if environments["native_mirror"].get("series") != ["M05"]:
            raise ValueError("invalid NATIVE mirror panel")
        if [value.get("series_id") for value in series] != [f"M0{i}" for i in range(1, 6)]:
            raise ValueError("invalid model-series contract")
        if any(value.get("exact_model_id") is not None for value in series):
            raise ValueError("exact model IDs belong only in the runtime model lock")
        if expected != {"closed_primary": 2800, "native_mirror": 700, "total": 3500}:
            raise ValueError("invalid expected observation counts")
        if (
            schedule.get("method") != "stratified_block_randomized_interleaved"
            or schedule.get("temporally_distribute_replications") is not True
            or schedule.get("seed") is not None
            or schedule.get("schedule_sha256") is not None
            or schedule.get("lock_required_before_execution") is not True
        ):
            raise ValueError("invalid schedule-lock separation")
        if (
            observer.get("site_or_region") is not None
            or observer.get("lock_required_before_execution") is not True
        ):
            raise ValueError("observer site must remain a required runtime lock")
        if (
            model_lock.get("required_before_execution") is not True
            or model_lock.get("exact_model_ids_locked") is not False
            or model_lock.get("silent_substitution_forbidden") is not True
        ):
            raise ValueError("invalid exact model-lock separation")
        governance = raw["governance_gates"]
        for gate in (
            "protocol_owner",
            "provider_terms_review",
            "institutional_ethics_or_governance_determination",
        ):
            if governance.get(gate) is not None:
                raise ValueError(f"{gate} belongs only in the runtime manifest")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"invalid W01 scientific manifest {path}: {exc}") from exc
    return raw

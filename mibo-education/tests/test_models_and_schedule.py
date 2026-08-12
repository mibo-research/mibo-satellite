from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from miboe.artifacts import load_registry
from miboe.errors import ImmutabilityError, ModelResolutionError, ValidationError
from miboe.models import load_model_lock, resolve_models
from miboe.util import artifact_hash, load_json


class ListingAdapter:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    def list_models(self):
        return [{"id": value} for value in self.ids]


def test_frozen_series_registry_is_distinct_from_wave_model_resolution() -> None:
    root = Path(__file__).parents[1]
    registry = load_registry(root / "registry" / "model-series.yaml")
    assert [row["series_id"] for row in registry["series"]] == [
        "M01",
        "M02",
        "M03",
        "M04",
        "M05",
    ]
    assert all("exact_model_id" not in row for row in registry["series"])


def test_model_aliases_are_rejected_without_substitution(wave_factory) -> None:
    manifest, _, _, _ = wave_factory()
    manifest.model_lock_path.unlink()
    with pytest.raises(ModelResolutionError, match="alias"):
        resolve_models(
            manifest,
            {"SERIES-1": "model-latest"},
            {},
            verify_live=True,
            adapter_factory=lambda provider: ListingAdapter(["model-latest"]),
        )


def test_exact_model_must_be_listed_and_lock_is_immutable(wave_factory) -> None:
    manifest, _, _, _ = wave_factory()
    manifest.model_lock_path.unlink()
    with pytest.raises(ModelResolutionError, match="did not list"):
        resolve_models(
            manifest,
            {"SERIES-1": "model-2026-01-01"},
            {},
            adapter_factory=lambda provider: ListingAdapter(["different-model"]),
        )
    lock = resolve_models(
        manifest,
        {"SERIES-1": "model-2026-01-01"},
        {"SERIES-1": "provider pinning record"},
        adapter_factory=lambda provider: ListingAdapter(["model-2026-01-01"]),
    )
    assert lock["models"][0]["requested_model"] == "model-2026-01-01"
    with pytest.raises(ImmutabilityError):
        resolve_models(manifest, {"SERIES-1": "model-2026-01-01"}, {})


def test_permanent_series_id_cannot_be_used_as_exact_wave_model_id(wave_factory) -> None:
    manifest, _, _, _ = wave_factory()
    manifest.model_lock_path.unlink()
    with pytest.raises(ModelResolutionError, match="permanent series ID"):
        resolve_models(
            manifest,
            {"SERIES-1": "SERIES-1"},
            {},
            adapter_factory=lambda provider: ListingAdapter(["SERIES-1"]),
        )


def test_manually_supplied_model_lock_cannot_conflate_series_and_exact_id(wave_factory) -> None:
    manifest, _, _, _ = wave_factory()
    lock = load_json(manifest.model_lock_path)
    lock.pop("model_lock_sha256")
    lock["models"][0]["requested_model"] = lock["models"][0]["series_id"]
    lock["model_lock_sha256"] = artifact_hash(lock)
    manifest.model_lock_path.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ValidationError, match="conflates"):
        load_model_lock(manifest.model_lock_path)


def test_schedule_is_balanced_stratified_and_temporally_distributed(wave_factory) -> None:
    manifest, battery, lock, schedule = wave_factory(replications=3)
    assert len(schedule["rows"]) == len(battery.items) * len(lock["models"]) * 3
    cells = Counter(
        (row["series_id"], row["item_id"], row["replication_number"]) for row in schedule["rows"]
    )
    assert set(cells.values()) == {1}
    times_by_rep = {
        rep: {
            row["planned_start_utc"] for row in schedule["rows"] if row["replication_number"] == rep
        }
        for rep in range(1, 4)
    }
    assert max(times_by_rep[1]) < min(times_by_rep[2]) < min(times_by_rep[3])
    assert {row["stratum"] for row in schedule["rows"]} == {"a", "b"}

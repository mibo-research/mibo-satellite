from __future__ import annotations

from collections import Counter

import pytest

from miboe.errors import ImmutabilityError, ModelResolutionError
from miboe.models import resolve_models


class ListingAdapter:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    def list_models(self):
        return [{"id": value} for value in self.ids]


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

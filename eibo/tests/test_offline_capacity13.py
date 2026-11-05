from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import offline_capacity12 as original
import pytest
from offline_capacity13 import METHOD, candidate_schedule, retime

from eibo.errors import ValidationError
from eibo.scheduling import load_schedule, validate_bindings


def test_retiming_only_changes_release_time_and_preserves_jitter_and_ties() -> None:
    anchor = original.ANCHOR
    starts = (anchor, anchor + timedelta(minutes=121), anchor + timedelta(hours=18))
    rows = [
        {"replication_number": n, "planned_start_utc": t.isoformat(), "tag": i}
        for i, (n, t) in enumerate(zip((1, 2, 10), starts, strict=True))
    ]
    rows.append({**rows[-1], "tag": 3})
    before = [row.copy() for row in rows]
    shifted = retime(rows)
    assert rows == before
    assert [r["tag"] for r in shifted] == [0, 1, 2, 3]
    assert [datetime.fromisoformat(r["planned_start_utc"]) for r in shifted] == [
        anchor,
        anchor + timedelta(minutes=109),
        anchor + timedelta(hours=16, minutes=12),
        anchor + timedelta(hours=16, minutes=12),
    ]


@pytest.mark.parametrize("replication", [0, 11, True])
def test_out_of_scope_replication_fails_closed(replication: int) -> None:
    row = {"replication_number": replication, "planned_start_utc": original.ANCHOR.isoformat()}
    with pytest.raises(ValidationError, match="replication numbers"):
        retime([row])


def test_retiming_rejects_cross_round_reordering() -> None:
    rows = [
        {
            "replication_number": n,
            "planned_start_utc": (original.ANCHOR + timedelta(minutes=minute)).isoformat(),
        }
        for n, minute in ((1, 119), (2, 121))
    ]
    with pytest.raises(ValidationError, match="change the randomized order"):
        retime(rows)


def test_candidate_uses_real_schedule_bindings_but_cannot_apply_to_official_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(original, "create_schedule", candidate_schedule)
    manifest, battery, lock, schedule = original.panel(tmp_path, "NATIVE", ("M05",))
    original_schedule = load_schedule(tmp_path / "unshifted-schedule-fixture.json")
    assert load_schedule(manifest.schedule_path) == schedule
    validate_bindings(manifest, battery, lock, schedule)
    assert schedule["randomization_method"] == METHOD
    assert schedule["source_schedule_sha256"] == original_schedule["schedule_sha256"]
    assert schedule["rows"] == retime(original_schedule["rows"])
    assert len(schedule["rows"]) == 700
    assert schedule["field_window_end"] == original_schedule["field_window_end"]
    assert schedule["official_longitudinal_data"] is False
    with pytest.raises(ValidationError, match="non-official synthetic fixture"):
        candidate_schedule(replace(manifest, official=True), battery, lock)

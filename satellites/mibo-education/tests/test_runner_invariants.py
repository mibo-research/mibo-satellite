from __future__ import annotations

import pytest

from miboe.adapters.base import ProviderResponse
from miboe.adapters.openai import OpenAIAdapter
from miboe.errors import ImmutabilityError, ProviderError, TechnicalRetryableError
from miboe.runner import run_wave
from miboe.util import canonical_json_bytes, load_json


def response(
    text: str = "poor or hallucinated answer", *, refusal: bool = False
) -> ProviderResponse:
    content = (
        {"type": "refusal", "refusal": text} if refusal else {"type": "output_text", "text": text}
    )
    body = {
        "id": "resp-1",
        "model": "test-model-2026-01-01",
        "status": "completed",
        "output": [{"type": "message", "content": [content]}],
        "usage": {},
    }
    return ProviderResponse(200, {}, canonical_json_bytes(body), body)


class FakeAdapter:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.delegate = OpenAIAdapter()

    def prepare(self, **kwargs):
        return self.delegate.prepare(**kwargs)

    def normalize(self, body):
        return self.delegate.normalize(body)

    def send(self, request):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else response()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.parametrize("observed", [response("I refuse", refusal=True), response("wrong answer")])
def test_refusals_and_bad_answers_are_completed_once_and_never_retried(wave_factory, observed):
    manifest, battery, lock, schedule = wave_factory(replications=1)
    adapter = FakeAdapter([observed])
    stats = run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=1,
        ignore_planned_time=True,
        adapter_factory=lambda provider: adapter,
        sleep=lambda seconds: None,
    )
    assert stats["completed"] == 1
    assert adapter.calls == 1
    completion = next((manifest.source.parent / "L0_raw").rglob("completion.json"))
    assert load_json(completion)["scientifically_completed"] is True


def test_only_technical_failure_retries_with_protocol_delay(wave_factory):
    manifest, battery, lock, schedule = wave_factory(replications=1)
    adapter = FakeAdapter([TechnicalRetryableError("timeout"), response("eventual output")])
    delays = []
    stats = run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=1,
        ignore_planned_time=True,
        adapter_factory=lambda provider: adapter,
        sleep=delays.append,
    )
    assert stats["completed"] == 1
    assert adapter.calls == 2
    assert delays == [600]
    observation = next((manifest.source.parent / "L0_raw").iterdir())
    assert len(list(observation.glob("*.request.body"))) == 2
    assert len(list(observation.glob("*.error.json"))) == 1


def test_nonretryable_provider_error_is_terminal(wave_factory):
    manifest, battery, lock, schedule = wave_factory(replications=1)
    adapter = FakeAdapter([ProviderError("bad request")])
    stats = run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=1,
        ignore_planned_time=True,
        adapter_factory=lambda provider: adapter,
        sleep=lambda seconds: None,
    )
    assert stats["technical_failure"] == 1
    assert adapter.calls == 1


def test_completed_L0_is_never_reexecuted_or_replaced(wave_factory):
    manifest, battery, lock, schedule = wave_factory(replications=1)
    first = FakeAdapter([response("original")])
    run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=1,
        ignore_planned_time=True,
        adapter_factory=lambda provider: first,
        sleep=lambda seconds: None,
    )
    body_path = next((manifest.source.parent / "L0_raw").rglob("*.response.body"))
    original = body_path.read_bytes()
    second = FakeAdapter([response("replacement")])
    stats = run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=1,
        ignore_planned_time=True,
        adapter_factory=lambda provider: second,
        sleep=lambda seconds: None,
    )
    # The next unfinished scheduled observation may run, but the completed one is never sent again.
    assert second.calls == 1
    assert stats["already_reconciled"] >= 1
    assert body_path.read_bytes() == original


def test_incomplete_prior_attempt_blocks_automatic_resend(wave_factory):
    manifest, battery, lock, schedule = wave_factory(replications=1)
    row = sorted(schedule["rows"], key=lambda value: value["execution_position"])[0]
    directory = manifest.source.parent / "L0_raw" / row["observation_id"]
    directory.mkdir(parents=True)
    (directory / f"{row['observation_id']}-A01.request.body").write_bytes(b"indeterminate")
    with pytest.raises(ImmutabilityError, match="human adjudication"):
        run_wave(
            manifest=manifest,
            battery=battery,
            lock=lock,
            schedule=schedule,
            max_observations=1,
            ignore_planned_time=True,
            adapter_factory=lambda provider: FakeAdapter([response()]),
            sleep=lambda seconds: None,
        )

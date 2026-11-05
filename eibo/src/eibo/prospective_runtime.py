"""Prospective EIBO-F01 execution controls, shared by scheduling, transport and QC.

Only the socket-free engineering entry point is enabled. Do not wire this to a
live client until a scoped official profile, locks, cost evidence and authority
exist. The legacy W0/W01 runner does not use this module.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .adapters import make_adapter
from .adapters.base import PreparedRequest
from .adapters.perplexity_w0 import PerplexityAgentW0Adapter
from .adapters.prospective_policy import explicit_technical_failure, has_observation, retry_at
from .artifacts import Battery, WaveManifest
from .errors import ValidationError
from .live_qualification import _prepare_request
from .qualification import FIRST_PARTY_HOSTS
from .scheduling import validate_bindings
from .util import (
    artifact_hash,
    canonical_json_bytes,
    ensure_no_secrets,
    sha256_bytes,
    sha256_text,
    write_immutable,
)

SERIES = {"M01": "openai", "M02": "anthropic", "M03": "gemini", "M05": "perplexity"}
TARGET = timedelta(hours=18)
HARD = timedelta(hours=24)
GOOGLE_GAP = timedelta(seconds=65)
MAX_MICRO_USD = 500_000_000
WARN_MICRO_USD = 400_000_000
PRIMARY = {"PRIMARY_WITHIN_TARGET", "PRIMARY_TARGET_OVERRUN"}
EXCLUDED_HEADERS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "x-goog-api-key",
    "api-key",
    "cookie",
    "set-cookie",
}


@dataclass(frozen=True)
class Cell:
    id: str
    series: str
    item: str
    replication: int
    model: str
    prompt: str
    prompt_sha256: str
    release: datetime


class Hold(ValidationError):
    """An admission denial. It can never be classified as a transport retry."""


def bind_four_provider_schedule(
    battery: Battery,
    panels: Mapping[str, tuple[WaveManifest, dict[str, Any], dict[str, Any]]],
    anchor: datetime,
) -> tuple[Cell, ...]:
    """Bind the full dual-panel, retimed schedule before invoking the transport."""
    anchor = utc(anchor)
    if set(panels) != {"CLOSED", "NATIVE"} or len(battery.items) != 70:
        raise ValidationError("full schedule requires both panels and the 70-item battery")
    battery_items = {item.item_id: item for item in battery.items}
    combined = []
    for env, (manifest, lock, schedule) in panels.items():
        validate_bindings(manifest, battery, lock, schedule)
        expected_series = {"M05"} if env == "NATIVE" else {"M01", "M02", "M03"}
        model_map = {row["series_id"]: row for row in lock["models"]}
        if (
            set(model_map) != expected_series
            or manifest.environment != env
            or manifest.replications != 10
            or manifest.start != anchor
            or manifest.end != anchor + TARGET
            or schedule.get("schedule_sha256")
            != artifact_hash({k: v for k, v in schedule.items() if k != "schedule_sha256"})
        ):
            raise ValidationError("prospective panel does not match the fixed design")
        for row in schedule["rows"]:
            sid = row["series_id"]
            item = battery_items.get(row["item_id"])
            model = model_map.get(sid)
            if (
                item is None
                or model is None
                or row["environment"] != env
                or row["provider"] != SERIES[sid]
                or model["provider"] != SERIES[sid]
                or row["requested_model"] != model["requested_model"]
                or row["prompt_sha256"] != item.prompt_sha256
                or row["stratum"] != item.stratum
            ):
                raise ValidationError("schedule row does not match the locked model or Frozen item")
            cell = Cell(
                row["observation_id"],
                sid,
                item.item_id,
                row["replication_number"],
                row["requested_model"],
                item.prompt,
                item.prompt_sha256,
                utc(datetime.fromisoformat(row["planned_start_utc"])),
            )
            combined.append((cell.release, row["execution_position"], env, cell))
    plan = tuple(entry[3] for entry in sorted(combined, key=lambda entry: entry[:3]))
    _validate_plan(plan, anchor)
    if len(plan) != 2800:
        raise ValidationError("incomplete prospective schedule")
    return plan


def save(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    row = {**value, "record_sha256": artifact_hash(value)}
    write_immutable(path, canonical_json_bytes(row) + b"\n")
    return row


def utc(stamp: datetime) -> datetime:
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValidationError("runtime requires timezone-aware clocks")
    return stamp.astimezone(UTC)


def _headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items() if k.lower() not in EXCLUDED_HEADERS}


class Admission:
    """Single writer, single in-flight request; hold every reservation for the run.

    Reservations are integer micro-USD upper bounds. No observed usage, lack of
    usage, or transport failure releases a reservation.
    """

    def __init__(
        self,
        anchor: datetime,
        bounds: Mapping[tuple[str, str], int | None],
        now: Callable[[], datetime],
        sleep: Callable[[float], None],
    ) -> None:
        self.anchor = utc(anchor)
        self.deadline = self.anchor + HARD
        self.clock, self.sleep = now, sleep
        self.bounds = dict(bounds)
        self.last_clock: datetime | None = None
        self.last_google: datetime | None = None
        self.cooldowns: dict[str, datetime] = {}
        self.post: Counter[str] = Counter()
        self.get: Counter[str] = Counter()
        self.retries: Counter[str] = Counter()
        self.attempts: Counter[str] = Counter()
        self.committed = 0

    def now(self) -> datetime:
        current = utc(self.clock())
        if self.last_clock is not None and current < self.last_clock:
            raise Hold("CLOCK_ROLLBACK")
        self.last_clock = current
        return current

    def check_time(self) -> datetime:
        current = self.now()
        if current < self.anchor:
            raise Hold("BEFORE_ANCHOR")
        if current >= self.deadline:
            raise Hold("HARD_DEADLINE")
        return current

    def wait(self, due: datetime, series: str, method: str) -> None:
        due = max(due, self.cooldowns.get(series, self.anchor))
        if series == "M03" and method == "POST" and self.last_google is not None:
            due = max(due, self.last_google + GOOGLE_GAP)
        # If the earliest safe dispatch is outside the window, do not wait or send it.
        if due >= self.deadline:
            raise Hold("NO_SLOT_BEFORE_DEADLINE")
        while (current := self.now()) < due:
            self.sleep(min(60, (due - current).total_seconds()))
        self.check_time()

    def bound(self, series: str, method: str) -> int:
        amount = self.bounds.get((series, method))
        if type(amount) is not int or not 0 < amount <= MAX_MICRO_USD:
            raise Hold("COST_BOUND_UNKNOWN_OR_INVALID")
        return amount

    def reserve(self, series: str, method: str, cell: str | None, intent: Path) -> None:
        current = self.check_time()
        if series not in SERIES or method not in {"GET", "POST"}:
            raise Hold("OUT_OF_SCOPE")
        attempt = self.attempts[cell] + 1 if cell is not None else 1
        amount = self.bound(series, method)
        total = self.post.total() + self.get.total()
        if total >= 3092:
            raise Hold("HTTP_ATTEMPT_LIMIT")
        if method == "GET":
            if cell is not None or self.get[series] >= 3 or self.get.total() >= 12:
                raise Hold("METADATA_ATTEMPT_LIMIT")
        else:
            if cell is None or attempt > 2:
                raise Hold("CELL_ATTEMPT_LIMIT")
            if self.post[series] >= 770 or self.post.total() >= 3080:
                raise Hold("POST_ATTEMPT_LIMIT")
            if attempt > 1 and (self.retries[series] >= 70 or self.retries.total() >= 280):
                raise Hold("RETRY_ATTEMPT_LIMIT")
        if self.committed + amount > MAX_MICRO_USD:
            raise Hold("COST_LIMIT")
        # Durably reserve the attempt and dollars before handing it to the transport.
        save(
            intent,
            {
                "series": series,
                "method": method,
                "cell": cell,
                "admitted_at": current.isoformat(),
                "number": total + 1,
                "cell_attempt": attempt,
                "reserve_micro_USD": amount,
                "committed_micro_USD": self.committed + amount,
                "budget_warning": self.committed + amount >= WARN_MICRO_USD,
            },
        )
        self.committed += amount
        if method == "GET":
            self.get[series] += 1
        else:
            self.post[series] += 1
            self.attempts[cell] += 1
            if attempt > 1:
                self.retries[series] += 1


@dataclass
class Ticket:
    series: str
    request: PreparedRequest
    cell: str | None
    stem: Path
    dispatched: datetime | None = None


def part(stem: Path, name: str) -> Path:
    return stem.with_name(f"{stem.name}.{name}")


class ControlledTransport(httpx.BaseTransport):
    """Place the final time check at the boundary to the inner transport."""

    def __init__(self, admission: Admission, inner: httpx.BaseTransport) -> None:
        self.admission, self.inner = admission, inner
        self.pending: Ticket | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        ticket = self.pending
        if ticket is None or ticket.dispatched is not None:
            raise Hold("UNADMITTED_OR_REPEAT_TRANSPORT")
        expected = ticket.request
        if (
            request.method != expected.method
            or str(request.url) != expected.url
            or request.read() != expected.body_bytes
            or "cookie" in request.headers
        ):
            raise Hold("WIRE_REQUEST_CHANGED")
        # No redirect, proxy or model substitution can be introduced at this boundary.
        host = FIRST_PARTY_HOSTS[SERIES[ticket.series]]
        if (
            request.url.scheme != "https"
            or request.url.host != host
            or request.url.port not in {None, 443}
            or request.url.userinfo
            or request.url.fragment
        ):
            raise Hold("NON_FIRST_PARTY")
        self.admission.reserve(
            ticket.series, expected.method, ticket.cell, part(ticket.stem, "intent.json")
        )
        # The durable write itself might cross the deadline. In that case the
        # reservation stays charged to the budget, but nothing reaches the wire.
        ticket.dispatched = self.admission.check_time()
        if ticket.series == "M03" and expected.method == "POST":
            self.admission.last_google = ticket.dispatched
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()


def _validate_plan(cells: tuple[Cell, ...], anchor: datetime) -> dict[str, str]:
    ids: set[str] = set()
    combinations: set[tuple[str, str, int]] = set()
    models: dict[str, str] = {}
    previous = anchor
    for cell in cells:
        key = (cell.series, cell.item, cell.replication)
        if (
            not re.fullmatch(r"[A-Z0-9-]{1,90}", cell.id)
            or cell.id in ids
            or key in combinations
            or cell.series not in SERIES
            or not re.fullmatch(r"E[1-7]-(?:0[1-9]|10)", cell.item)
            or type(cell.replication) is not int
            or not 1 <= cell.replication <= 10
            or not cell.model
            or models.setdefault(cell.series, cell.model) != cell.model
            or sha256_text(cell.prompt) != cell.prompt_sha256
            or not previous <= utc(cell.release) <= anchor + TARGET
        ):
            raise ValidationError("invalid prospective plan cell or order")
        ids.add(cell.id)
        combinations.add(key)
        previous = utc(cell.release)
    if not cells:
        raise ValidationError("empty prospective plan")
    return models


class Execution:
    def __init__(
        self,
        output: Path,
        admission: Admission,
        transport: ControlledTransport,
        client: httpx.Client,
    ) -> None:
        self.output, self.admission, self.transport, self.client = (
            output,
            admission,
            transport,
            client,
        )

    def dispatch(
        self,
        series: str,
        request: PreparedRequest,
        stem: Path,
        due: datetime,
        cell: str | None,
    ) -> tuple[str, dict[str, Any], datetime | None]:
        ticket = Ticket(series, request, cell, stem)
        write_immutable(part(stem, "request.body"), request.body_bytes)
        save(
            part(stem, "request.json"),
            {
                "series": series,
                "method": request.method,
                "url": request.url,
                "headers": _headers(request.headers),
                "body_sha256": sha256_bytes(request.body_bytes),
            },
        )
        self.transport.pending = ticket
        try:
            self.admission.wait(due, series, request.method)
            self.client.cookies.clear()
            response = self.client.request(
                request.method, request.url, headers=request.headers, content=request.body_bytes
            )
        except Hold as exc:
            save(part(stem, "result.json"), {"state": "DENIED", "reason": str(exc)})
            return str(exc), {}, None
        except httpx.RequestError:
            # The provider may have processed the request. No automatic retry.
            save(
                part(stem, "result.json"),
                {
                    "state": "AMBIGUOUS_SEND_HOLD",
                    "dispatched_at": ticket.dispatched.isoformat() if ticket.dispatched else None,
                },
            )
            return "AMBIGUOUS_SEND_HOLD", {}, None
        finally:
            self.transport.pending = None
        try:
            received = self.admission.now()
        except Hold:
            received = None
        # Never copy or hash credential-bearing content. Preserve only the
        # quarantine status and length when the secret check fails.
        try:
            ensure_no_secrets(response.content, context="prospective response")
        except ValidationError:
            save(
                part(stem, "result.json"),
                {
                    "state": "REDACTION_HOLD",
                    "dispatched_at": ticket.dispatched.isoformat(),
                    "received_at": received.isoformat() if received is not None else None,
                    "body_length": len(response.content),
                },
            )
            return "REDACTION_HOLD", {}, None
        body_hash = sha256_bytes(response.content)
        write_immutable(part(stem, "response.body"), response.content)
        save(
            part(stem, "response.json"),
            {
                "status_code": response.status_code,
                "headers": _headers(response.headers),
                "body_sha256": body_hash,
                "dispatched_at": ticket.dispatched.isoformat(),
                "received_at": received.isoformat() if received is not None else None,
            },
        )
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        body = parsed if isinstance(parsed, dict) else {}
        evidence = {
            "status": response.status_code,
            "body": body,
            "headers": _headers(response.headers),
            "response_sha256": body_hash,
            "dispatched_at": ticket.dispatched.isoformat(),
        }
        return ("RECEIVED" if received is not None else "CLOCK_ROLLBACK"), evidence, received

    def observe(self, cell: Cell, adapter: Any) -> dict[str, Any]:
        request, _ = _prepare_request(
            adapter,
            series_id=cell.series,
            model=cell.model,
            prompt=cell.prompt,
        )
        if request.method != "POST":
            raise ValidationError("observation request must be POST")
        due = cell.release
        result: dict[str, Any] = {
            "id": cell.id,
            "series": cell.series,
            "item": cell.item,
            "replication": cell.replication,
            "requested_model": cell.model,
            "environment": "NATIVE" if cell.series == "M05" else "CLOSED",
            "prompt_sha256": cell.prompt_sha256,
            "planned_start": utc(due).isoformat(),
            "scientifically_completed": False,
            "primary": False,
        }
        for attempt in (1, 2):
            stem = self.output / "L0" / cell.id / f"attempt-{attempt}"
            state, response, received = self.dispatch(cell.series, request, stem, due, cell.id)
            if state != "RECEIVED":
                result.update(
                    status=state,
                    **{
                        key: response[key]
                        for key in ("response_sha256", "dispatched_at")
                        if key in response
                    },
                )
                break
            body = response["body"]
            observed = has_observation(adapter.provider, body)
            if observed and (200 <= response["status"] < 300 or response["status"] >= 400):
                status = (
                    "LATE_NONPRIMARY"
                    if received > self.admission.deadline
                    else "PRIMARY_TARGET_OVERRUN"
                    if received > self.admission.anchor + TARGET
                    else "PRIMARY_WITHIN_TARGET"
                )
                try:
                    normalized = adapter.normalize(body)
                    valid = (
                        (normalized.returned_model or "").removeprefix("models/") == cell.model
                        and bool(normalized.response_id)
                        and (
                            cell.series != "M05" or not adapter.qualification_response_errors(body)
                        )
                    )
                except (AttributeError, KeyError, TypeError, ValueError):
                    normalized, valid = None, False
                if not valid:
                    result["provider_hold"] = "IDENTITY_OR_PROFILE_HOLD"
                    if status != "LATE_NONPRIMARY":
                        status = "INVALID_RESPONSE_NONPRIMARY"
                result.update(
                    status=status,
                    primary=status in PRIMARY,
                    scientifically_completed=True,
                    request_sha256=sha256_bytes(request.body_bytes),
                    response_sha256=response["response_sha256"],
                    dispatched_at=response["dispatched_at"],
                    received_at=received.isoformat(),
                    returned_model=normalized.returned_model if normalized else None,
                    finish_reason=normalized.finish_reason if normalized else None,
                    response_id=normalized.response_id if normalized else None,
                    response_text=normalized.text if normalized else None,
                    usage=normalized.usage if normalized else {},
                )
                break
            retryable = explicit_technical_failure(response["status"], body)
            if retryable:
                due = retry_at(adapter.provider, response["headers"], body, received)
                self.admission.cooldowns[cell.series] = due
            if retryable and attempt == 1:
                save(
                    part(stem, "result.json"),
                    {
                        "state": "CONFIRMED_TECHNICAL_FAILURE",
                        "retry_not_before": due.isoformat(),
                    },
                )
                continue
            result["status"] = "TECHFAIL" if retryable else "UNCONFIRMED_RESPONSE_HOLD"
            if not retryable:
                result["provider_hold"] = "UNCONFIRMED_RESPONSE_HOLD"
            break
        result["reserved_attempts"] = self.admission.attempts[cell.id]
        return save(self.output / "L0" / cell.id / "completion.json", result)


def run_offline(
    *,
    output: Path,
    cells: Iterable[Cell],
    anchor: datetime,
    transport: httpx.MockTransport,
    cost_bounds_micro_usd: Mapping[tuple[str, str], int | None],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    metadata: Iterable[tuple[str, int]] = (),
) -> dict[str, Any]:
    """Run the prospective path with synthetic wire responses and virtual time only."""
    if type(transport) is not httpx.MockTransport:
        raise ValidationError("live transport is disabled; MockTransport required")
    anchor = utc(anchor)
    plan, metadata = tuple(cells), tuple(metadata)
    models = _validate_plan(plan, anchor)
    admission = Admission(anchor, cost_bounds_micro_usd, now, sleep)
    output.mkdir(parents=True, exist_ok=False)  # no restart/retry on an existing archive
    save(
        output / "execution-claim.json",
        {
            "scope": "EIBO_F01_SYNTHETIC_ONLY",
            "anchor": anchor.isoformat(),
            "target": (anchor + TARGET).isoformat(),
            "deadline": (anchor + HARD).isoformat(),
            "OFFICIAL_LONGITUDINAL_DATA": False,
            "plan_sha256": artifact_hash(
                [
                    [
                        c.id,
                        c.series,
                        c.item,
                        c.replication,
                        c.model,
                        c.prompt_sha256,
                        utc(c.release).isoformat(),
                    ]
                    for c in plan
                ]
            ),
            "cost_bounds_micro_USD": {
                f"{series}/{method}": value
                for (series, method), value in sorted(cost_bounds_micro_usd.items())
            },
        },
    )
    required = {(series, "POST") for series in models}
    required.update((series, "GET") for series, _ in metadata)
    global_hold = None
    try:
        for series, method in sorted(required):
            admission.bound(series, method)
    except Hold as exc:
        global_hold = str(exc)
    observations, metadata_results = [], []
    provider_holds: dict[str, str] = {}
    controlled = ControlledTransport(admission, transport)
    with httpx.Client(transport=controlled, follow_redirects=False, trust_env=False) as client:
        execution = Execution(output, admission, controlled, client)
        adapters = {}
        for sid in models:
            provider = SERIES[sid]
            options = {
                "api_key": "synthetic-fixture-only",
                "client": client,
                "base_url": f"https://{FIRST_PARTY_HOSTS[provider]}",
            }
            adapters[sid] = (
                PerplexityAgentW0Adapter(**options)
                if sid == "M05"
                else make_adapter(provider, **options)
            )
        metadata_plan = []
        for sid, index in metadata:
            if sid not in adapters or type(index) is not int or index < 0:
                raise ValidationError("metadata target is outside the bound series")
            requests = adapters[sid].model_metadata_requests(models[sid])
            if index >= len(requests) or requests[index].method != "GET":
                raise ValidationError("metadata target is outside the allowed endpoints")
            metadata_plan.append((sid, requests[index]))
        if not global_hold:
            for i, (sid, request) in enumerate(metadata_plan, 1):
                if sid in provider_holds:
                    continue
                state, reply, _ = execution.dispatch(
                    sid,
                    request,
                    output / "metadata" / f"request-{i}",
                    anchor,
                    None,
                )
                if state == "RECEIVED" and (
                    not 200 <= reply["status"] < 300
                    or not adapters[sid].metadata_identifies_model(models[sid], (reply["body"],))
                ):
                    state = "METADATA_IDENTITY_OR_HTTP_HOLD"
                if state != "RECEIVED":
                    provider_holds[sid] = state
                metadata_results.append({"series": sid, "state": state})
        for cell in plan:
            reason = global_hold or provider_holds.get(cell.series)
            if not reason:
                try:
                    if admission.now() >= admission.deadline:
                        global_hold = reason = "HARD_DEADLINE"
                except Hold as exc:
                    global_hold = reason = str(exc)
            if reason:
                observations.append(
                    {
                        "id": cell.id,
                        "series": cell.series,
                        "item": cell.item,
                        "replication": cell.replication,
                        "status": "NOT_SENT",
                        "reason": reason,
                        "primary": False,
                        "scientifically_completed": False,
                    }
                )
                continue
            result = execution.observe(cell, adapters[cell.series])
            observations.append(result)
            if result["status"] in {
                "COST_LIMIT",
                "HTTP_ATTEMPT_LIMIT",
                "HARD_DEADLINE",
                "CLOCK_ROLLBACK",
            }:
                global_hold = result["status"]
            if result.get("provider_hold") or result["status"] == "REDACTION_HOLD":
                provider_holds[cell.series] = result.get("provider_hold", result["status"])
    counts = Counter(row["status"] for row in observations)
    write_immutable(
        output / "observations.jsonl",
        b"".join(
            canonical_json_bytes({**row, "OFFICIAL_LONGITUDINAL_DATA": False}) + b"\n"
            for row in observations
        ),
    )
    return save(
        output / "report.json",
        {
            "OFFICIAL_LONGITUDINAL_DATA": False,
            "FUTURE_OFFICIAL_EXECUTION_READY": False,
            "planned": len(plan),
            "status_counts": dict(counts),
            "primary": sum(counts[key] for key in PRIMARY),
            "post_by_series": dict(admission.post),
            "get_by_series": dict(admission.get),
            "retries_by_series": dict(admission.retries),
            "metadata": metadata_results,
            "committed_micro_USD": admission.committed,
            "global_hold": global_hold,
            "provider_holds": provider_holds,
        },
    )

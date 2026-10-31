"""Separately authorized, non-official four-provider W0 rehearsal; never Core-35."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from .adapters import make_adapter
from .adapters.perplexity_w0 import PerplexityAgentW0Adapter, load_w0_agent_profile
from .artifacts import load_battery, load_manifest, load_registry, load_scientific_artifact_registry
from .certificate import create_certificate
from .closeout import ITEM_IDS, MODELS, assess_closeout, require, verify_reference
from .errors import ProviderError, TechnicalRetryableError, ValidationError
from .live_qualification import (
    SAMPLING,
    _anthropic_thinking_metadata,
    _prepare_request,
    _response_flags,
    _send_captured,
)
from .qc import run_qc
from .qualification import FIRST_PARTY_HOSTS, assert_first_party
from .runner import run_wave
from .scheduling import create_schedule
from .util import (
    artifact_hash,
    canonical_json_bytes,
    ensure_no_secrets,
    load_json,
    sha256_bytes,
    sha256_file,
    utc_now,
    write_immutable,
)

PROPOSAL = "EIBO-W0-4P-R1"
PROVIDERS = {"M01": "openai", "M02": "anthropic", "M03": "gemini", "M05": "perplexity"}
LIMITS = {
    "primary_observations": 28,
    "max_attempts_per_observation": 2,
    "max_generation_requests": 56,
    "max_metadata_GET_requests": 6,
    "Google_minimum_start_interval_seconds": 65,
    "wall_clock_new_request_limit_seconds": 7200,
    "additional_diagnostic_requests": 0,
    "retry_scientific_outcomes": False,
    "fixed_currency_cost_cap": None,
}
DECISIONS = {
    "closeout": "ACCEPTED_FOUR_PROVIDER_Q1_Q2_EVIDENCE_CLOSEOUT_WITH_SEPARATE_GOOGLE_RECOVERY",
    "plan": "ADOPTED_OPTION_A_FOUR_PROVIDER_NON_OFFICIAL_W0_REHEARSAL_DESIGN_ONLY",
    "owner": "HUMAN_CONFIRMED_LIMITED_PROTOCOL_OWNER_APPROVAL_FOR_EIBO_W0_4P_R1",
    "terms": "HUMAN_CONFIRMED_TERMS_APPROVED_FOR_EIBO_W0_4P_R1_28_REQUESTS_ONLY",
    "ethics": "HUMAN_CONFIRMED_PRIOR_NOT_HUMAN_SUBJECTS_DETERMINATION_APPLIES_TO_EIBO_W0_4P_R1",
    "timing": "START_AFTER_ALL_REMAINING_PREPARATION_AND_FINAL_PREFLIGHT_GATES_PASS",
    "site": "USE_PREVIOUS_W0_LOCAL_WORKSTATION_SITE_AND_NORMAL_CONNECTION_IN_JAPAN",
    "limits": "APPROVED_LIMITED_EXECUTION_AFTER_IMPLEMENTATION_TESTS_AND_FINAL_GATES",
}


def save(path: Path, value: dict[str, Any]) -> None:
    core = {**value, "official_longitudinal_data": False}
    write_immutable(
        path, canonical_json_bytes({**core, "record_sha256": artifact_hash(core)}) + b"\n"
    )


def authorization(root: Path, output: Path, path: Path) -> dict[str, Any]:
    auth = load_json(path)
    claimed_auth = auth.pop("authorization_sha256")
    require(artifact_hash(auth) == claimed_auth, "authorization hash mismatch")
    require(
        set(auth["implementation_files_sha256"])
        == {p.relative_to(root).as_posix() for p in (root / "src/eibo").rglob("*.py")},
        "tested implementation inventory is incomplete",
    )
    for relative, digest in auth["implementation_files_sha256"].items():
        require(sha256_file(root / relative) == digest, "tested implementation changed")
    require(
        auth.get("proposal_id") == PROPOSAL and auth.get("official_longitudinal_data") is False,
        "only the non-official four-provider proposal is authorized",
    )
    require(set(auth["receipts"]) == set(DECISIONS), "human decisions are incomplete")
    plan = root / "operations/prospective-four-provider/plan.draft.yaml"
    require(sha256_file(plan) == auth["plan_sha256"], "approved plan snapshot changed")
    receipts = {}
    for name, decision in DECISIONS.items():
        value = load_json(verify_reference(output, auth["receipts"][name]))
        claimed = value.pop("receipt_sha256")
        require(artifact_hash(value) == claimed, "human receipt hash mismatch")
        require(value.get("decision") == decision, "human decision scope does not match")
        require(
            value.get("official_longitudinal_data") is False, "official permission not accepted"
        )
        if name != "closeout":
            require(
                value.get("plan_snapshot_sha256") == auth["plan_sha256"], "receipt plan mismatch"
            )
        require(value.get("W01_execution_authorized") is False, "W01 must remain forbidden")
        require(value.get("xai_execution_authorized") is False, "xAI must remain forbidden")
        receipts[name] = value
    require(receipts["limits"]["limits"] == LIMITS, "execution limits changed")
    require(receipts["site"]["observer_site_declaration"]["country"] == "JP", "site unconfirmed")
    require(
        receipts["ethics"].get("institutional_IRB_approval_claimed") is False,
        "human determination is not an institutional IRB approval",
    )
    for name in ("owner", "terms", "ethics"):
        actor = receipts[name].get("decided_by") or {}
        require(
            actor.get("actor_type") == "HUMAN" and bool(actor.get("name")),
            "human governance attribution missing",
        )
    require(
        receipts["owner"]["decided_by"]
        == receipts["terms"]["decided_by"]
        == receipts["ethics"]["decided_by"],
        "governance actor mismatch",
    )
    assessment = load_json(verify_reference(output, auth["assessment"]))
    require(assessment.get("FOUR_PROVIDER_EVIDENCE_COMPLETE") is True, "qualification incomplete")
    require(
        receipts["closeout"]["assessment_file_sha256"] == auth["assessment"]["sha256"],
        "human closeout acceptance binding mismatch",
    )
    load_scientific_artifact_registry(root / "protocol/scientific-artifacts.yaml")
    profile = load_w0_agent_profile(root)
    require(profile["profile_sha256"] == auth["M05_profile_sha256"], "M05 profile changed")
    return auth


def native_guard(state_path: Path) -> None:
    require(os.name == "nt", "live local execution requires the approved Windows guard")
    value = load_json(state_path)
    age = (datetime.now(UTC) - datetime.fromisoformat(value["updated_at_utc"])).total_seconds()
    require(
        value["status"] == "ACTIVE"
        and value["system_sleep_request_active"] is True
        and value["ac_connected"] is True
        and 0 <= age < 20,
        "AC/sleep guard not active",
    )
    session = value["session"]
    require(re.fullmatch(r"[A-Za-z0-9_-]+", session) is not None, "invalid guard session")
    command = (
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(value['pid'])}'; "
        f"if ($p.CommandLine -like '*keep_awake_w0.py*--session {session}*')"
        " {exit 0} else {exit 1}"
    )
    result = subprocess.run(
        [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "-NoProfile",
            "-Command",
            command,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    power = (ctypes.c_ubyte * 12)()
    require(
        result.returncode == 0
        and bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)))
        and power[0] == 1,
        "current AC or guard PID verification failed",
    )


def load_credentials(root: Path, output: Path) -> None:
    """Call only after native_guard. No values are printed, hashed, or persisted."""
    import winreg

    names = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name in names:
            try:
                value = winreg.QueryValueEx(key, name)[0]
            except FileNotFoundError:
                continue
            if isinstance(value, str) and value:
                os.environ[name] = value
    env_file = root.parent / ".env"
    if env_file.exists():
        git = shutil.which("git")
        require(git is not None, "Git is required to verify ignored credential storage")
        ignored = subprocess.run(
            [git, "check-ignore", "--quiet", ".env"],
            cwd=root.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        require(ignored.returncode == 0 and not env_file.is_symlink(), "env file must be ignored")
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            name, sep, value = line.partition("=")
            name = name.strip()
            if sep and name in names and not os.getenv(name):
                os.environ[name] = value.strip().strip("\"'")
    require(
        all(bool(os.getenv(name)) for name in names), "a selected provider credential is absent"
    )
    os.environ["EIBO_W0_EVIDENCE_ROOT"] = str(output)


def first_party_factory(provider: str):
    require(provider in PROVIDERS.values(), "provider not in approved four-provider scope")
    client = httpx.Client(timeout=120, follow_redirects=False, trust_env=False)
    base = f"https://{FIRST_PARTY_HOSTS[provider]}"
    if provider == "perplexity":
        return PerplexityAgentW0Adapter(base_url=base, client=client)
    return make_adapter(provider, base_url=base, client=client)


def retry_after(response: Any, now: float) -> float:
    headers = {k.lower(): v for k, v in response.headers.items()}
    value = headers.get("retry-after", "0")
    try:
        seconds = max(0.0, float(value))
    except ValueError:
        try:
            seconds = max(0.0, parsedate_to_datetime(value).timestamp() - now)
        except (ValueError, TypeError, OverflowError):
            seconds = 0.0
    error_body = (response.body or {}).get("error")
    for entry in error_body.get("details", []) if isinstance(error_body, dict) else []:
        delay = entry.get("retryDelay", "")
        if isinstance(delay, str) and re.fullmatch(r"\d+(\.\d+)?s", delay):
            seconds = max(seconds, float(delay[:-1]))
    return seconds


def recoverable_output(provider: str, body: dict[str, Any]) -> bool:
    if provider == "anthropic":
        return bool(body.get("content")) and bool(body.get("stop_reason"))
    if provider == "gemini":
        return bool(body.get("candidates")) or bool(
            body.get("promptFeedback", {}).get("blockReason")
        )
    return body.get("status") in {"completed", "incomplete"} and isinstance(
        body.get("output"), list
    )


class Budget:
    def __init__(self, directory: Path, guard: Any, clock: Any, sleep: Any, progress: Any):
        self.directory, self.guard, self.clock, self.sleep, self.progress = (
            directory,
            guard,
            clock,
            sleep,
            progress,
        )
        self.start = clock()
        self.wall_start = datetime.now(UTC)
        self.deadline = self.start + 7200
        self.post = self.get = 0
        self.last_google = float("-inf")
        self.not_before: dict[str, float] = {}

    def check(self):
        self.guard()
        require(self.clock() < self.deadline, "two-hour new-request deadline reached")

    def wait(self, seconds):
        ready = self.clock() + seconds
        while self.clock() < ready:
            self.check()
            self.sleep(min(5, ready - self.clock()))

    def send(self, adapter, request):
        assert_first_party(request, adapter.provider)
        require(adapter.client.follow_redirects is False, "redirect following forbidden")
        require(request.method in {"GET", "POST"}, "unsupported request method")
        ready = self.not_before.get(adapter.provider, self.start)
        if request.method == "POST" and adapter.provider == "gemini":
            ready = max(ready, self.last_google + 65)
        self.wait(max(0, ready - self.clock()))
        self.check()
        if request.method == "GET":
            require(self.get < 6, "metadata GET budget exhausted")
            self.get += 1
        else:
            require(self.post < 56, "generation request budget exhausted")
            self.post += 1
            if adapter.provider == "gemini":
                self.last_google = self.clock()
        number = self.post + self.get
        save(
            self.directory / "transport" / f"wire-{number:03d}.intent.json",
            {
                "sent_at": utc_now(),
                "method": request.method,
                "url": request.url,
                "request_body_sha256": sha256_bytes(request.body_bytes),
            },
        )

        # The HTTP client sends the exact pre-serialized bytes; no SDK is involved.
        def audit_wire(wire):
            require(
                wire.content == request.body_bytes and str(wire.url) == request.url,
                "wire serialization or URL changed",
            )

        adapter.client.event_hooks["request"] = [audit_wire]
        try:
            response = adapter.send(request)
        except (TechnicalRetryableError, ProviderError) as error:
            captured = getattr(error, "provider_response", None)
            if captured is not None:
                ensure_no_secrets(captured.body_bytes, context="received provider response")
                self.not_before[adapter.provider] = self.clock() + retry_after(
                    captured, time.time()
                )
                if recoverable_output(adapter.provider, captured.body or {}):
                    return captured  # A recovered scientific response is never retried.
            raise
        ensure_no_secrets(response.body_bytes, context="received provider response")
        if 300 <= response.status_code < 400:
            error = ProviderError("first-party redirect refused without fallback")
            error.provider_response = response
            raise error
        return response


class ControlledAdapter:
    def __init__(self, adapter, series: str, budget: Budget):
        self.inner, self.series, self.budget = adapter, series, budget

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def prepare(self, **kwargs):
        request, _ = _prepare_request(
            self.inner, series_id=self.series, model=MODELS[self.series], prompt=kwargs["prompt"]
        )
        require(kwargs["model"] == MODELS[self.series], "model substitution forbidden")
        expected_environment = "NATIVE" if self.series == "M05" else "CLOSED"
        require(str(kwargs["environment"]) == expected_environment, "environment changed")
        require(
            kwargs.get("sampling") == SAMPLING[self.series] and not kwargs.get("native_options"),
            "unapproved sampling or native options",
        )
        return request

    def send(self, request):
        return self.budget.send(self.inner, request)


def materialize(directory: Path, panel: str, series: list[str], battery, start, end):
    values = {item.item_id: item for item in battery.items}
    instrument = {
        "battery_id": "EIBO-W0-4P-R1-EXACT-SUBSET",
        "version": "1.0",
        "status": "ENGINEERING_ONLY",
        "approved": False,
        "official_longitudinal_eligible": False,
        "expected_item_count": 7,
        "source_battery_sha256": battery.content_sha256,
        "items": [
            {
                "id": item,
                "stratum": values[item].stratum,
                "frozen": True,
                "prompt_ja": values[item].prompt,
                "prompt_sha256": values[item].prompt_sha256,
            }
            for item in ITEM_IDS
        ],
    }
    registry = {
        "registry_id": f"{PROPOSAL}-{panel}",
        "version": "1.0",
        "approved": False,
        "series": [
            {
                "series_id": sid,
                "provider": PROVIDERS[sid],
                "label": sid,
                "closed_eligibility": panel == "closed",
            }
            for sid in series
        ],
    }
    manifest = {
        "schema_version": "1.0",
        "status": "ENGINEERING",
        "approved": False,
        "wave_id": f"{PROPOSAL}-{panel.upper()}",
        "site_id": "MIBO-SITE-JP01",
        "official_longitudinal_data": False,
        "protocol_version": "approved-four-provider-w0-r1",
        "battery": "battery.yaml",
        "model_registry": "registry.yaml",
        "model_lock": "model-lock.json",
        "schedule": "schedule.json",
        "environment": "CLOSED" if panel == "closed" else "NATIVE",
        "replications": 1,
        "random_seed": f"{PROPOSAL}|{panel}|v1",
        "field_window": {"start": start.isoformat(), "end": end.isoformat()},
        "sampling": {PROVIDERS[sid]: SAMPLING[sid] for sid in series},
        "native_options": {},
        "max_technical_attempts": 2,
        "retry_delays_minutes": [2],
        "approvals": {},
        "scope": "NON_OFFICIAL_W0_NOT_LEGACY_CORE_35",
        "request_budget_enforced_by_global_controller": True,
    }
    for name, value in (("battery", instrument), ("registry", registry), ("manifest", manifest)):
        write_immutable(
            directory / f"{name}.yaml",
            yaml.safe_dump(value, allow_unicode=True, sort_keys=False).encode("utf-8"),
        )
    loaded = load_manifest(directory / "manifest.yaml")
    reg = load_registry(directory / "registry.yaml")
    core = {
        "schema_version": "1.0",
        "wave_id": loaded.wave_id,
        "registry_sha256": reg["registry_sha256"],
        "resolved_at": utc_now(),
        "official_longitudinal_data": False,
        "models": [
            {
                "series_id": sid,
                "provider": PROVIDERS[sid],
                "requested_model": MODELS[sid],
                "live_verified": True,
                "pinning_verified": sid == "M02",
                "behavioral_immutability_claimed": False,
                **(
                    {
                        "permanent_mibo_lineage_id": "MIBO-SL-002",
                        "permanent_lineage_label": "Claude",
                    }
                    if sid == "M02"
                    else {}
                ),
            }
            for sid in series
        ],
    }
    lock = {**core, "model_lock_sha256": artifact_hash(core)}
    write_immutable(loaded.model_lock_path, canonical_json_bytes(lock) + b"\n")
    subset = load_battery(loaded.battery_path)
    schedule = create_schedule(loaded, subset, lock, order_only=True)
    return loaded, subset, lock, schedule


def interleave(panels):
    rng = random.Random(f"{PROPOSAL}|native-insertion|v1")
    closed = panels["closed"][3]["rows"]
    native = panels["native"][3]["rows"]
    rows = []
    for nr in native:
        block = [{**r, "panel": "closed"} for r in closed if r["stratum"] == nr["stratum"]]
        require(len(block) == 3, "CLOSED block must contain three series")
        block.insert(rng.randrange(4), {**nr, "panel": "native"})
        rows.extend(block)
    require(
        len(rows) == 28 and len({r["observation_id"] for r in rows}) == 28,
        "interleaved schedule is not exactly 28 distinct observations",
    )
    return [{**row, "global_execution_position": n} for n, row in enumerate(rows, 1)]


def run_rehearsal(
    *,
    root: Path,
    output: Path,
    authorization_path: Path,
    guard: Any,
    factory: Any = first_party_factory,
    clock: Any = time.monotonic,
    sleep: Any = time.sleep,
    progress: Any = None,
):
    auth = authorization(root, output, authorization_path)
    qualified = assess_closeout(output, root / "waves/W0/closeout/sources-v1.json")
    require(qualified["FOUR_PROVIDER_EVIDENCE_COMPLETE"], "four-provider qualification missing")
    guard()
    directory = output / "rehearsals" / PROPOSAL
    # One adopted proposal gets one exclusive execution claim, even after a crash.
    directory.mkdir(parents=True, exist_ok=False)
    save(
        directory / "execution-claim.json",
        {
            "claimed_at": utc_now(),
            "proposal_id": PROPOSAL,
            "authorization_file_sha256": sha256_file(authorization_path),
            "limits": LIMITS,
        },
    )
    baseline = {
        p.relative_to(output).as_posix(): sha256_file(p)
        for name in (
            "Q1",
            "Q2",
            "gates",
            "profile-attempts",
            "operations",
            "recoveries",
            "closeouts",
        )
        for p in (output / name).rglob("*")
        if p.is_file()
    }
    save(directory / "prior-record-checksums.json", {"entries": baseline})
    budget = Budget(directory, guard, clock, sleep, progress)
    adapters, panels, outcomes, metadata, errors = {}, {}, [], {}, []

    def emit(value):
        if progress:
            progress(value)

    try:
        for sid, provider in PROVIDERS.items():
            inner = factory(provider)
            require(bool(inner.api_key), f"credential missing for {sid}")
            adapters[sid] = ControlledAdapter(inner, sid, budget)
            bodies = []
            for number, request in enumerate(inner.model_metadata_requests(MODELS[sid]), 1):
                response, error = _send_captured(
                    adapters[sid], directory / "metadata" / sid, f"model-{number}", request
                )
                if response is not None:
                    bodies.append(response.body)
                else:
                    errors.append(f"{sid} metadata request failed: {error}")
            identified = inner.metadata_identifies_model(MODELS[sid], tuple(bodies))
            metadata[sid] = {"exact_model_identified": identified, "requested_model": MODELS[sid]}
            if not identified:
                errors.append(f"{sid} exact model missing from first-party metadata")
        save(directory / "metadata-result.json", {"providers": metadata, "errors": errors})
        require(not errors, "first-party metadata preflight failed; no generation sent")
        battery = load_battery(root / "battery/ebb-ja-v1.0.yaml")
        start = budget.wall_start
        end = start + timedelta(seconds=7200)
        for panel, series in (("closed", ["M01", "M02", "M03"]), ("native", ["M05"])):
            panels[panel] = materialize(directory / panel, panel, series, battery, start, end)
        rows = interleave(panels)
        core = {
            "scope": PROPOSAL,
            "official_longitudinal_data": False,
            "method": "production-stratified-block-order-plus-uniform-native-insertion",
            "authorization_sha256": sha256_file(authorization_path),
            "rows": rows,
            "panel_schedule_hashes": {p: v[3]["schedule_sha256"] for p, v in panels.items()},
        }
        global_schedule = {**core, "schedule_sha256": artifact_hash(core)}
        write_immutable(
            directory / "interleaved-schedule.json", canonical_json_bytes(global_schedule) + b"\n"
        )
        save(
            directory / "runtime-lock.json",
            {
                "proposal_id": PROPOSAL,
                "locked_at_utc": utc_now(),
                "site_id": "MIBO-SITE-JP01",
                "observer_country_human_declared": "JP",
                "provider_internal_region_guaranteed": False,
                "authorization_sha256": sha256_file(authorization_path),
                "limits": LIMITS,
                "field_window_start": start.isoformat(),
                "field_window_end": end.isoformat(),
                "interleaved_schedule_sha256": global_schedule["schedule_sha256"],
                "scientific_registry_sha256": sha256_file(
                    root / "protocol/scientific-artifacts.yaml"
                ),
                "M05_profile_sha256": auth["M05_profile_sha256"],
            },
        )
        for row in rows:
            budget.check()
            sid = row["series_id"]
            manifest, subset, lock, schedule = panels[row["panel"]]
            emit(
                {
                    "event": "observation_start",
                    "position": row["global_execution_position"],
                    "series": sid,
                    "item": row["item_id"],
                }
            )
            run_wave(
                manifest=manifest,
                battery=subset,
                lock=lock,
                schedule=schedule,
                max_observations=1,
                adapter_factory=lambda provider: next(
                    a for a in adapters.values() if a.provider == provider
                ),
                sleep=budget.wait,
                now=datetime.now(UTC),
            )
            completion = load_json(
                manifest.source.parent / "L0_raw" / row["observation_id"] / "completion.json"
            )
            result = {
                "series_id": sid,
                "item_id": row["item_id"],
                "status": completion["status"],
                "attempts": completion["attempts"],
                "returned_model": completion.get("returned_model"),
            }
            if completion["status"] == "OBSERVED":
                files = sorted(
                    (manifest.source.parent / "L0_raw" / row["observation_id"]).glob(
                        "*.response.body"
                    )
                )
                body = json.loads(files[-1].read_bytes())
                normalized = adapters[sid].normalize(body)
                result.update(_response_flags(normalized))
                if sid == "M02":
                    result["thinking_metadata"] = _anthropic_thinking_metadata(body)
                if sid == "M03":
                    result["modelVersion"] = body.get("modelVersion")
                problems = adapters[sid].qualification_response_errors(body) if sid == "M05" else []
                if (completion.get("returned_model") or "").removeprefix("models/") != MODELS[sid]:
                    problems.append("returned model identity missing/mismatch")
                if problems:
                    errors.extend(f"{sid}: {problem}" for problem in problems)
            outcomes.append(result)
            save(directory / "outcomes" / f"{row['global_execution_position']:02d}.json", result)
            emit({"event": "observation_complete", **result})
            require(
                not errors, "provider identity/configuration failed closed after raw preservation"
            )
    except Exception as exc:
        # Never print response bodies, credentials, headers, or unrestricted exception text.
        reason = str(exc) if isinstance(exc, ValidationError) else type(exc).__name__
        ensure_no_secrets(reason.encode("utf-8"), context="safe stop reason")
        errors.append(f"execution stopped: {reason}")
        save(
            directory / "stopped.json",
            {"at": utc_now(), "exception_type": type(exc).__name__, "reason": reason},
        )
    finally:
        for adapter in adapters.values():
            adapter.client.close()
    panel_results = {}
    for name, (manifest, subset, lock, schedule) in panels.items():
        qc = run_qc(manifest, subset, lock, schedule)
        certificate = None
        if (
            qc["passed"]
            and not qc["warnings"]
            and not qc["status_counts"].get("MISSING")
            and not errors
        ):
            certificate = create_certificate(
                manifest.source.parent,
                manifest_sha256=manifest.content_sha256,
                battery_sha256=subset.content_sha256,
                model_lock_sha256=lock["model_lock_sha256"],
                schedule_sha256=schedule["schedule_sha256"],
            )
        panel_results[name] = {"qc": qc, "certificate": certificate}
    prior_unchanged = all(sha256_file(output / p) == digest for p, digest in baseline.items())
    load_scientific_artifact_registry(root / "protocol/scientific-artifacts.yaml")
    require(prior_unchanged, "prior evidence changed")
    completed = sum(row["status"] == "OBSERVED" for row in outcomes)
    report = {
        "proposal_id": PROPOSAL,
        "recorded_at": utc_now(),
        "outcomes": outcomes,
        "generation_requests": budget.post,
        "metadata_GET_requests": budget.get,
        "observed": completed,
        "expected": 28,
        "errors": errors,
        "passed": completed == 28
        and not errors
        and all(v["qc"]["passed"] for v in panel_results.values()),
        "panels": panel_results,
        "prior_records_unchanged": prior_unchanged,
        "xai_requests": 0,
        "W01": "NOT_RUN",
        "legacy_Core_35": "NOT_RUN",
        "W0_READY": False,
        "W01_READY": False,
    }
    save(directory / "report.json", report)
    if report["passed"]:
        save(
            directory / "scoped-completion-certificate.json",
            {
                "scope": "NON_OFFICIAL_FOUR_PROVIDER_REHEARSAL_ONLY_NOT_CORE_35_OR_W01",
                "proposal_id": PROPOSAL,
                "certified_at": utc_now(),
                "report_sha256": sha256_file(directory / "report.json"),
                "interleaved_schedule_sha256": global_schedule["schedule_sha256"],
                "panel_certificate_hashes": {
                    panel: result["certificate"]["certificate_sha256"]
                    for panel, result in panel_results.items()
                },
            },
        )
    checksums = {
        p.relative_to(directory).as_posix(): sha256_file(p)
        for p in directory.rglob("*")
        if p.is_file()
    }
    save(directory / "archive-checksums.json", {"entries": checksums})
    return {**report, "official_longitudinal_data": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--guard-state", required=True, type=Path)
    args = parser.parse_args()

    def progress(value):
        data = canonical_json_bytes(value)
        ensure_no_secrets(data, context="rehearsal progress")
        print(data.decode("utf-8"), flush=True)

    native_guard(args.guard_state)
    authorization(args.root, args.output_root, args.authorization)
    load_credentials(args.root, args.output_root)
    result = run_rehearsal(
        root=args.root,
        output=args.output_root,
        authorization_path=args.authorization,
        guard=lambda: native_guard(args.guard_state),
        progress=progress,
    )
    progress(
        {
            "event": "rehearsal_finished",
            "passed": result["passed"],
            "observed": result["observed"],
            "generation_requests": result["generation_requests"],
        }
    )


if __name__ == "__main__":
    main()

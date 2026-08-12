from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .artifacts import load_battery, load_manifest
from .blind import export_blind
from .certificate import create_certificate
from .errors import MiboeError, ValidationError
from .models import load_model_lock, resolve_models
from .preflight import preflight
from .qc import run_qc
from .readiness import FLAGS, scientific_readiness
from .runner import run_wave
from .scheduling import create_schedule, load_schedule


def _pairs(values: list[str] | None, *, name: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValidationError(f"{name} must use SERIES=VALUE syntax")
        key, item = value.split("=", 1)
        if not key or not item or key in result:
            raise ValidationError(f"invalid or duplicate {name}: {value}")
        result[key] = item
    return result


def _context(path: Path) -> tuple[Any, Any, Any, Any]:
    manifest = load_manifest(path)
    battery = load_battery(manifest.battery_path)
    lock = load_model_lock(manifest.model_lock_path)
    schedule = load_schedule(manifest.schedule_path)
    return manifest, battery, lock, schedule


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    result = scientific_readiness(root)
    false_reasons = [
        reason for flag in FLAGS if not result[flag] for reason in result["reasons"][flag]
    ]
    errors = result["reasons"]["ENGINEERING_READY"] if args.engineering else false_reasons
    warnings = (
        [reason for flag in FLAGS[1:] if not result[flag] for reason in result["reasons"][flag]]
        if args.engineering
        else []
    )
    result = {**result, "errors": errors, "warnings": warnings}
    if errors:
        raise ValidationError(json.dumps(result, ensure_ascii=False))
    return result


def command_resolve(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(Path(args.manifest))
    return resolve_models(
        manifest,
        _pairs(args.set, name="--set"),
        _pairs(args.evidence, name="--evidence"),
        verify_live=not args.no_live_verification,
    )


def command_schedule(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(Path(args.manifest))
    battery = load_battery(manifest.battery_path)
    lock = load_model_lock(manifest.model_lock_path)
    return create_schedule(manifest, battery, lock)


def command_preflight(args: argparse.Namespace) -> dict[str, Any]:
    report = preflight(load_manifest(Path(args.manifest)))
    if not report["passed"]:
        raise ValidationError(json.dumps(report, ensure_ascii=False))
    return report


def command_pilot(args: argparse.Namespace) -> dict[str, Any]:
    manifest, battery, lock, schedule = _context(Path(args.manifest))
    if manifest.official:
        raise ValidationError("pilot command refuses official Wave manifests")
    return run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=args.max_observations,
        ignore_planned_time=args.ignore_planned_time,
    )


def command_run_wave(args: argparse.Namespace) -> dict[str, Any]:
    manifest, battery, lock, schedule = _context(Path(args.manifest))
    if not manifest.official:
        raise ValidationError("run-wave is reserved for official manifests; use pilot")
    return run_wave(
        manifest=manifest,
        battery=battery,
        lock=lock,
        schedule=schedule,
        max_observations=args.max_observations,
    )


def command_qc(args: argparse.Namespace) -> dict[str, Any]:
    manifest, battery, lock, schedule = _context(Path(args.manifest))
    report = run_qc(manifest, battery, lock, schedule)
    if not report["passed"]:
        raise ValidationError(json.dumps(report, ensure_ascii=False))
    return report


def command_certificate(args: argparse.Namespace) -> dict[str, Any]:
    manifest, battery, lock, schedule = _context(Path(args.manifest))
    return create_certificate(
        manifest.source.parent,
        manifest_sha256=manifest.content_sha256,
        battery_sha256=battery.content_sha256,
        model_lock_sha256=lock["model_lock_sha256"],
        schedule_sha256=schedule["schedule_sha256"],
    )


def command_export(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(Path(args.manifest))
    salt = os.getenv(args.salt_env, "")
    return export_blind(manifest.source.parent, salt=salt)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="miboe")
    commands = value.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    validate.add_argument("--engineering", action="store_true")
    validate.set_defaults(function=command_validate)

    models = commands.add_parser("models")
    model_commands = models.add_subparsers(dest="model_command", required=True)
    resolve = model_commands.add_parser("resolve")
    resolve.add_argument("--manifest", required=True)
    resolve.add_argument("--set", action="append", required=True)
    resolve.add_argument("--evidence", action="append", default=[])
    resolve.add_argument("--no-live-verification", action="store_true")
    resolve.set_defaults(function=command_resolve)

    schedule = commands.add_parser("schedule")
    schedule.add_argument("--manifest", required=True)
    schedule.set_defaults(function=command_schedule)

    for name, function in (
        ("preflight", command_preflight),
        ("qc", command_qc),
        ("certificate", command_certificate),
        ("export-blind", command_export),
    ):
        item = commands.add_parser(name)
        item.add_argument("--manifest", required=True)
        if name == "export-blind":
            item.add_argument("--salt-env", default="MIBOE_BLIND_SALT")
        item.set_defaults(function=function)

    pilot = commands.add_parser("pilot")
    pilot.add_argument("--manifest", required=True)
    pilot.add_argument("--max-observations", type=int)
    pilot.add_argument("--ignore-planned-time", action="store_true")
    pilot.set_defaults(function=command_pilot)

    official = commands.add_parser("run-wave")
    official.add_argument("--manifest", required=True)
    official.add_argument("--max-observations", type=int)
    official.set_defaults(function=command_run_wave)
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        result = args.function(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (MiboeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

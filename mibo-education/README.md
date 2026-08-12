# MIBO-Education

Official MIBO Satellite for longitudinal observation of educational behavior in general-purpose AI systems.

> AI capability benchmarks measure what a model can do. MIBO-Education measures what kind of educator a model becomes.

MIBO-Education inherits MIBO’s persistent service-series identity, synchronized Waves, independent replication, immutable raw records, prospective amendment, and re-observability principles. Education-specific instruments, observation conditions, provider adapters, and coding remain isolated here.

## Status

| Gate | Current state | Reason |
|---|---|---|
| `ENGINEERING_READY` | True | Automated tests, lint, packaging, CLI, and secret checks pass |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | True | All five authoritative v1.0 artifacts are Frozen and exact-hash verified |
| `W0_READY` | False | W0 approvals, exact model lock, and locked schedule are absent |
| `W01_READY` | False | Required runtime model, schedule, site, provider-control, and governance locks are absent |

The software is intentionally fail-closed. It cannot execute `MIBO-EDU-W01` until every scientific and operational preflight gate passes. See [READINESS.md](READINESS.md), [BLOCKERS.md](BLOCKERS.md), and the machine-readable [scientific artifact registry](protocol/scientific-artifacts.yaml).

## Layer model

```text
L0_raw (immutable requests, responses, attempts)
  -> L1_canonical (rebuildable JSONL)
  -> L2_coded (codebook-versioned; not implemented without source material)
  -> L3_analytical (analysis-plan-versioned; not implemented without source material)
```

Coding corrections can replace a versioned L2 derivative but can never modify L0.

## Setup

```bash
cd mibo-education
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
miboe validate --engineering
pytest
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## W0 engineering workflow

W0 uses only the clearly marked non-scientific smoke instrument. It never becomes longitudinal data.

The operational-qualification artifacts are under `waves/W0/`. They bind all provider requests to first-party API hosts. Consumer UI equivalence is not assumed and is outside W01 scope.

```bash
miboe models resolve --manifest waves/W0/manifest.yaml --set M01=<verified-exact-model-id>
miboe schedule --manifest waves/W0/manifest.yaml
miboe preflight --manifest waves/W0/manifest.yaml
miboe pilot --manifest waves/W0/manifest.yaml --max-observations 5
miboe qc --manifest waves/W0/manifest.yaml
```

`pilot` refuses a manifest marked official. It writes `OFFICIAL_LONGITUDINAL_DATA=false` into the Wave seal and every canonical record.

## W01 — BLOCKED

The scientific target anchor is `2026-09-01T00:00:00Z` (`2026-09-01 09:00 JST`). This is metadata, not permission to run. The immutable scientific manifest is complete; the separate runtime manifest remains deliberately non-executable until every operational lock is recorded. After those locks are approved, use:

```bash
miboe preflight --manifest waves/W01/manifest.yaml
miboe run-wave --manifest waves/W01/manifest.yaml
```

`run-wave` refuses W01 unless preflight is complete, artifacts are approved and hashed, exact models are live-verified, the schedule is locked, and the current time is inside the registered field window.

## Commands

`miboe validate`, `miboe models resolve`, `miboe schedule`, `miboe pilot`, `miboe preflight`, `miboe run-wave`, `miboe qc`, `miboe certificate`, and `miboe export-blind`.

## Provider-specific ambiguities

- OpenAI: whether a selected model ID is behaviorally pinned for the complete annual period must be verified; aliases cannot be Frozen IDs.
- Anthropic: the Messages API requires `max_tokens`; the authoritative Education protocol must freeze this transport-required cap and decide treatment of thinking/effort controls.
- Gemini: stable IDs are preferable, but provider documentation does not promise behavioral immutability; returned `modelVersion` must be retained.
- xAI: M04 is the Frozen scientific role, but its exact runtime model ID and version-pinning evidence remain unresolved.
- Perplexity: Sonar is web-grounded, so the adapter refuses CLOSED observations. A provider-approved no-search mode or a protocol decision is required.
- NATIVE API observations are not automatically equivalent to consumer web products. Any such equivalence requires a registered observation-surface decision.

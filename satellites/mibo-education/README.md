# MIBO-Education

Official MIBO Satellite for longitudinal observation of educational behavior in general-purpose AI systems.

> AI capability benchmarks measure what a model can do. MIBO-Education measures what kind of educator a model becomes.

MIBO-Education inherits MIBO’s persistent service-series identity, synchronized Waves, independent replication, immutable raw records, prospective amendment, and re-observability principles. Education-specific instruments, observation conditions, provider adapters, and coding remain isolated here.

## Status

| Gate | Current state | Reason |
|---|---|---|
| `ENGINEERING_READY` | True | Automated tests, lint, packaging, CLI, and secret checks pass |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | False | Authoritative scientific artifacts are not in the repository |
| `W0_READY` | False | Exact pilot model lock and protocol-owner approval are pending |
| `W01_READY` | False | The approved 70-item EBB-JA v1.0 and other W01 gates are absent |

The software is intentionally fail-closed. It cannot execute `MIBO-EDU-W01` until every scientific and operational preflight gate passes. See [BLOCKERS.md](BLOCKERS.md).

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
cd satellites/mibo-education
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
miboe validate --engineering
pytest
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## W0 engineering workflow

W0 uses only the clearly marked non-scientific smoke instrument unless the authoritative EBB-JA is supplied. It never becomes longitudinal data.

```bash
miboe models resolve --manifest waves/W0/manifest.yaml --set MIBO-EDU-SL-001=<verified-exact-model-id>
miboe schedule --manifest waves/W0/manifest.yaml
miboe preflight --manifest waves/W0/manifest.yaml
miboe pilot --manifest waves/W0/manifest.yaml --max-observations 5
miboe qc --manifest waves/W0/manifest.yaml
```

`pilot` refuses a manifest marked official. It writes `OFFICIAL_LONGITUDINAL_DATA=false` into the Wave seal and every canonical record.

## W01

The target anchor is `2026-09-01T00:00:00Z` (`2026-09-01 09:00 JST`). This is metadata, not permission to run. Even after artifacts are supplied, use:

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
- xAI: its permanent Education panel role and version-pinning evidence are not supplied by the scientific registry.
- Perplexity: Sonar is web-grounded, so the adapter refuses CLOSED observations. A provider-approved no-search mode or a protocol decision is required.
- NATIVE API observations are not automatically equivalent to consumer web products. Any such equivalence requires a registered observation-surface decision.

# MIBO-Education

Official MIBO Satellite for longitudinal observation of educational behavior in general-purpose AI systems.

> AI capability benchmarks measure what a model can do. MIBO-Education measures what kind of educator a model becomes.

## Protocol release

- Title: **MIBO-Education Protocol Package v1.0**
- DOI: [10.5281/zenodo.22047001](https://doi.org/10.5281/zenodo.22047001)
- License: [CC BY 4.0](LICENSE_PROTOCOL.md) for the scoped scientific protocol materials
- Citation metadata: [CITATION.cff](CITATION.cff)

The protocol package is published on Zenodo, and the DOI resolves to the public v1.0 record. Runtime software and operational tooling are outside the scoped CC BY 4.0 grant and remain governed by the repository-level license notice.

MIBO-Education inherits MIBO’s persistent service-series identity, synchronized Waves, independent replication, immutable raw records, prospective amendment, and re-observability principles. Education-specific instruments, observation conditions, provider adapters, and coding remain isolated here.

## Status

| Gate | Current state | Reason |
|---|---|---|
| `ENGINEERING_READY` | True | Automated tests, lint, packaging, CLI, and secret checks pass |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | True | All five authoritative v1.0 artifacts are Frozen and exact-hash verified |
| `HUMAN_GOVERNANCE_READY` | False | Three explicitly attributed final human records are absent |
| `CREDENTIAL_ENVIRONMENT_READY` | False | Credential and persistent evidence-root presence checks are incomplete |
| `W0_Q1_EXECUTABLE` | False | Human-governance and credential/environment gates are incomplete |
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
cd satellites/mibo-education
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
miboe validate --engineering
pytest
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## W0 live qualification workflow

W0 uses only the clearly marked non-scientific smoke instrument. It never becomes longitudinal data.

The versioned qualification plan is `waves/W0/live-qualification-plan.yaml`. Live outputs are append-only under the Git-ignored `waves/W0/live-qualification/` directory. Requests are bound to first-party API hosts; credential headers are never stored. Consumer UI equivalence is not assumed and is outside W01 scope.

```bash
miboe qualify report
miboe qualify preflight
miboe qualify smoke
miboe qualify providers
miboe qualify rehearsal
```

Q1 makes at most one ordinary request per selected series after human-governance, credential/environment, and model-metadata checks. A provider-specific Q1 checks only that series' credential; it never requires an unrelated provider's credential. Q2 is gated independently per provider by current pre-live checks and that provider's Q1, and runs the seven preselected E1-E7 items; M05 additionally runs the non-official `disable_search=true` diagnostic. Q3 requires current full-panel pre-live readiness plus all Q2 gates and runs Core-35 through the production scheduler, runner, technical-retry classifier, raw archive, QC, and certificate flow. Every stage remains `OFFICIAL_LONGITUDINAL_DATA=false`.

The human templates are under `waves/W0/governance/templates/`; signed records belong under `waves/W0/governance/records/`. Agents cannot approve them. `NOT_APPLICABLE` and `NOT_HUMAN_SUBJECTS` still require a named human, role, timezone-aware decision time, rationale, and explicit attestation.

Missing governance, credentials, persistent evidence-root presence, model-identity mismatch, missing metadata, or a prior-stage failure refuses the affected stage before any provider request. In GitHub Actions, the protected environment and self-hosted runner markers are also required. M02 maps permanent lineage `MIBO-SL-002 — Claude` to W0 exact candidate `claude-opus-5`; this does not rename the lineage or set the W01 exact model. No provider failure can cause model substitution. `miboe qualify report` and `miboe qualify preflight` never call a provider and report only presence booleans, never credential or environment values.

## W01 — BLOCKED

The scientific target anchor is `2026-09-01T00:00:00Z` (`2026-09-01 09:00 JST`). This is metadata, not permission to run. The immutable scientific manifest is complete; the separate runtime manifest remains deliberately non-executable until every operational lock is recorded. After those locks are approved, use:

```bash
miboe preflight --manifest waves/W01/manifest.yaml
miboe run-wave --manifest waves/W01/manifest.yaml
```

`run-wave` refuses W01 unless preflight is complete, artifacts are approved and hashed, exact models are live-verified, the schedule is locked, and the current time is inside the registered field window.

## Commands

`miboe validate`, `miboe models resolve`, `miboe schedule`, `miboe pilot`, `miboe preflight`, `miboe run-wave`, `miboe qc`, `miboe certificate`, `miboe export-blind`, and `miboe qualify {preflight,smoke,providers,rehearsal,report}`.

## Provider-specific ambiguities

- OpenAI: whether a selected model ID is behaviorally pinned for the complete annual period must be verified; aliases cannot be Frozen IDs.
- Anthropic: W0 uses canonical pinned ID `claude-opus-5`, omits effort and thinking overrides, and retains protocol-required `max_tokens=8192`. Live evidence must determine whether default thinking causes `stop_reason=max_tokens` or materially constrains visible output; serving-infrastructure variation remains possible despite the pinned model ID.
- Gemini: stable IDs are preferable, but provider documentation does not promise behavioral immutability; returned `modelVersion` must be retained.
- xAI: the W0 candidate is `grok-4.5` on `/v1/responses` with `max_output_tokens=8192`; Models API version/fingerprint evidence and returned identity remain live-unverified. `grok-4.5-latest` is forbidden.
- Perplexity: W01 remains NATIVE on the first-party Sonar API. The `disable_search=true` path is a separate, non-official W0 diagnostic and cannot qualify as a W01 observation.
- NATIVE API observations are not automatically equivalent to consumer web products. Any such equivalence requires a registered observation-surface decision.

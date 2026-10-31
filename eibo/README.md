# EIBO

Longitudinal observation of educational behavior in general-purpose AI systems.

> AI capability benchmarks measure what a model can do. EIBO measures what kind of educator a model becomes.

EIBO is the current project name. It was renamed from MIBO-Education. The imported v1.0 scientific artifacts retain their historical name, exact bytes, identifiers, and SHA-256 hashes. EIBO inherits MIBO’s persistent service-series identity, synchronized Waves, independent replication, immutable raw records, prospective amendment, and re-observability principles.

## Status

Live evidence update (2026-10-31): Q1/Q2 evidence is now complete for the four
selected providers, including separately archived Google recoveries. This is not
full-panel W0 completion. See the [offline closeout](waves/W0/closeout/README.md)
and [blocked prospective preparation](operations/prospective-four-provider/README.md).

| Gate | Current state | Reason |
|---|---|---|
| `ENGINEERING_READY` | True | Automated tests, lint, packaging, CLI, and secret checks pass |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | True | All five authoritative v1.0 artifacts are Frozen and exact-hash verified |
| `HUMAN_GOVERNANCE_READY` | True | Three explicit human W0 determinations are recorded |
| `CREDENTIAL_ENVIRONMENT_READY` | False | Full-panel credentials are incomplete; local persistent evidence root is configured |
| `W0_Q1_EXECUTABLE` | False | Full panel held by M04 cost deferral; M01-M03 and the explicit migrated M05 W0 profile may qualify individually |
| `W0_READY` | False | Full-panel live qualification, exact model lock, and locked schedule are incomplete |
| `W01_READY` | False | Required runtime model, schedule, site, provider-control, and governance locks are absent |

The software is intentionally fail-closed. Legacy `MIBO-EDU-W01` remains blocked and cannot adopt the prospective solo-coding model retroactively. See [READINESS.md](READINESS.md), [BLOCKERS.md](BLOCKERS.md), the [operating model](operations/operating-model.yaml), and the machine-readable [scientific artifact registry](protocol/scientific-artifacts.yaml).

## Solo operating and coding model

EIBO is configured for one accountable human operator. Approved execution, immutable archival, hashing, QC, and exports may be automated. Agents and automation cannot approve protocol-owner, provider-terms, or ethics/governance records.

Primary coding is performed by one human coder using a blind export and versioned provenance. EIBO does not claim two-human inter-rater reliability. A second AI model is optional and disabled by default; if enabled later, it is a separate sensitivity analysis whose model, prompt, parameters, outputs, and hashes must be preserved. It cannot replace the human coder, adjudicate the primary codes, or overwrite them.

The transition is documented in [EIBO-PA-001](protocol/amendments/EIBO-PA-001-rename-and-solo-operations.md). Its attributed human adoption is recorded in `operations/operating-model-attestation.yaml`; future official Waves still need their own approved scientific and runtime locks.

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
cd eibo
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
eibo validate --engineering
pytest
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## W0 live qualification workflow

W0 uses only the clearly marked non-scientific smoke instrument. It never becomes longitudinal data.

The versioned qualification plan is `waves/W0/live-qualification-plan.yaml`. Live outputs are append-only under the Git-ignored `waves/W0/live-qualification/` directory. Requests are bound to first-party API hosts; credential headers are never stored. Consumer UI equivalence is not assumed and is outside W01 scope.

```bash
eibo qualify report
eibo qualify preflight
eibo qualify smoke
eibo qualify providers
eibo qualify rehearsal
```

Q1 makes at most one ordinary request per selected series after human-governance, credential/environment, and model-metadata checks. A provider-specific Q1 checks only that series' credential; it never requires an unrelated provider's credential. Q2 is gated independently per provider by current pre-live checks and that provider's Q1, and runs the seven preselected E1-E7 items. Migrated M05 uses the separate [W0 Agent API profile](waves/W0/perplexity-agent-profile-v1.yaml), exact `perplexity/sonar`, and a non-official no-search diagnostic with tools and effort omitted; the obsolete `disable_search` field is not sent. Its gates bind the model and profile hash. Q3 requires current full-panel pre-live readiness plus all Q2 gates and runs Core-35 through the production scheduler, runner, technical-retry classifier, raw archive, QC, and certificate flow. Every stage remains `OFFICIAL_LONGITUDINAL_DATA=false`. M04's cost deferral keeps the full-panel rehearsal blocked.

The human templates are under `waves/W0/governance/templates/`; signed records belong under `waves/W0/governance/records/`. Agents cannot approve them. `NOT_APPLICABLE` and `NOT_HUMAN_SUBJECTS` still require a named human, role, timezone-aware decision time, rationale, and explicit attestation.

Missing governance, credentials, persistent evidence-root presence, model-identity mismatch, missing metadata, or a prior-stage failure refuses the affected stage before any provider request. In GitHub Actions, the protected environment and self-hosted runner markers are also required. M02 maps permanent lineage `MIBO-SL-002 — Claude` to W0 exact candidate `claude-opus-5`; the inherited MIBO lineage ID remains historical and stable. No provider failure can cause model substitution. `eibo qualify report` and `eibo qualify preflight` never call a provider and report only presence booleans, never credential or environment values.

## W01 — BLOCKED

Preparation for a distinct future four-provider/solo-coding official protocol is
under [official-four-provider](operations/official-four-provider/README.md).
It contains unapproved proposals and null runtime-lock templates only, not an
executable Wave or permission to reuse W0 data/locks. Legacy W01 remains unchanged.

The scientific target anchor is `2026-09-01T00:00:00Z` (`2026-09-01 09:00 JST`). This is metadata, not permission to run. The immutable scientific manifest is complete; the separate runtime manifest remains deliberately non-executable until every operational lock is recorded. After those locks are approved, use:

```bash
eibo preflight --manifest waves/W01/manifest.yaml
eibo run-wave --manifest waves/W01/manifest.yaml
```

`run-wave` refuses W01 unless preflight is complete, artifacts are approved and hashed, exact models are live-verified, the schedule is locked, and the current time is inside the registered field window.

## Commands

`eibo validate`, `eibo models resolve`, `eibo schedule`, `eibo pilot`, `eibo preflight`, `eibo run-wave`, `eibo qc`, `eibo certificate`, `eibo export-blind`, and `eibo qualify {preflight,smoke,providers,rehearsal,report}`.

## Provider-specific ambiguities

- OpenAI: whether a selected model ID is behaviorally pinned for the complete annual period must be verified; aliases cannot be Frozen IDs.
- Anthropic: W0 uses canonical pinned ID `claude-opus-5`, omits effort and thinking overrides, and retains protocol-required `max_tokens=8192`. Live evidence must determine whether default thinking causes `stop_reason=max_tokens` or materially constrains visible output; serving-infrastructure variation remains possible despite the pinned model ID.
- Gemini: stable IDs are preferable, but provider documentation does not promise behavioral immutability; returned `modelVersion` must be retained.
- xAI: the W0 candidate is `grok-4.5` on `/v1/responses` with `max_output_tokens=8192`; Models API version/fingerprint evidence and returned identity remain live-unverified. `grok-4.5-latest` is forbidden.
- Perplexity: the frozen W01 design remains unchanged and blocked. W0 alone uses the explicit `perplexity/sonar` Agent API profile: NATIVE enables `web_search`; its non-official no-search diagnostic omits tools and effort rather than sending legacy `disable_search=true`. Returned identity, actual search behavior, and equivalence to the former API require empirical evidence; no official CLOSED eligibility or immutable pinning is claimed.
- NATIVE API observations are not automatically equivalent to consumer web products. Any such equivalence requires a registered observation-surface decision.

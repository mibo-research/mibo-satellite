# EIBO readiness report

`eibo validate --engineering` recomputes the independent flags and emits machine-readable reasons.

## Live evidence update — 2026-10-31

The four selected providers now have complete Q1/Q2 evidence: M01/M02 original
7/7, M03 original 5/7 plus separately preserved E6-01/E7-01 recoveries, and M05
NATIVE 7/7 plus non-official no-search 7/7. The offline closeout verifier and pinned
sources are documented in [the W0 closeout](waves/W0/closeout/README.md). This
assessment does not rewrite Google's FAILED_CLOSED original result or create its
legacy Q2 gate. Historical qualification candidates/evidence manifests remain
unchanged and may still describe the pre-live state; their absence statements
are not a current inventory of the externally stored captures.

The [separate four-provider rehearsal](operations/prospective-four-provider/RESULTS-20261031.md)
completed on 2026-10-31: 28/28 observations, 28 generation sends, six metadata
GETs, no retries, both panel QCs passed, and scoped certificates issued. Eight
explicit human decision receipts supplied the closeout acceptance, design,
governance, timing, site, and limits. The original draft/templates remain
unchanged snapshots, not agent-finalized approvals. Rehearsal-only model,
schedule, and runtime locks were created after metadata verification; they do
not lock legacy W0 or W01. All 411 prior evidence files remained byte-identical.

| Flag | Value | Exact reason when false |
|---|---:|---|
| `ENGINEERING_READY` | `true` | — |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | `true` | — |
| `OPERATING_MODEL_ATTESTED` | `true` | Human adoption recorded on 2026-10-22; applies prospectively. |
| `HUMAN_GOVERNANCE_READY` | `true` | Three explicit human-attributed W0 determinations recorded on 2026-10-22. |
| `CREDENTIAL_ENVIRONMENT_READY` | `false` | Full-panel credential presence is incomplete only because M04 is deliberately deferred for cost. Local presence checks passed for M01, M02, M03, and M05 on 2026-10-24. The local persistent evidence root is configured; GitHub execution separately requires a controlled runner. |
| `W0_Q1_EXECUTABLE` | `false` | Full-panel execution remains held by M04 `NOT_RUN_COST_CONSTRAINT`. M01-M03 and migrated M05 may pass provider-specific preflight with their credentials and evidence root loaded. M05 requires its separate valid W0 Agent API profile. |
| `W0_READY` | `false` | Four-provider Q1/Q2 closeout is human-accepted and the separately authorized 28-observation rehearsal passed. The original M03 Q2 gate remains unchanged; five-provider Q3 Core-35 and full-panel model/schedule locks remain incomplete. M04's deferral still blocks the original full-panel qualification. Scoped rehearsal success does not satisfy that gate. |
| `W01_READY` | `false` | Runtime manifest is not locked; exact model-lock, schedule hash, observer site, provider-required controls, CLOSED eligibility evidence, governance determinations, and Wave lock timestamp are missing; execution is not permitted. |

## Authoritative artifact freeze state

| Artifact | State | SHA-256 |
|---|---|---|
| EBB-JA v1.0 | `FROZEN` | `5475d4c0edd651ae4fbc6e79c42642433fa7e0c27dba616a972236d35517cd4e` |
| MIBO-Education Codebook v1.0 (legacy name preserved) | `FROZEN` | `c38cce32bad4e3b156ec6094d2368fca0937536519b25a2a80e115042da9161a` |
| Item-Level Scoring Manual v1.0 | `FROZEN` | `3ae057c2e5f23312b5ca000f3d9f42ced4db23ca6b6db8c4889905c9f9a0bbef` |
| Observation Protocol v1.0 | `FROZEN` | `ca9b51ecbca1f5fd61443e7921ff4305dac82829a3043c795416c437b20d5d8f` |
| W01 Scientific Manifest v1.0 | `FROZEN_SCIENTIFIC` | `ecb5b5aa779d0806cb034581d76ab1c128587f1b9590a7b482fc3fa93336a6f1` |

The immutable scientific manifest is not the mutable runtime manifest. Scientific completion does not authorize W01 execution.

## Prospective EIBO operating model

EIBO is configured for one accountable human operator with automated execution and one human primary coder. Two-human inter-rater reliability is not claimed. Optional AI secondary coding is disabled by default and may be used only as a separately preserved sensitivity analysis. The operating model was adopted by the attributed human on 2026-10-22; agents cannot approve it.

This model applies only to prospective EIBO Waves. It does not alter the frozen Codebook v1.0 requirement for two independent coders and therefore cannot make legacy W01 executable.

The official observation surface is the first-party provider API. Consumer UI equivalence is neither assumed nor a readiness requirement. No W0 result is official longitudinal data.

## Runtime holds recorded on 2026-10-24

`waves/W0/provider-execution-holds.yaml` blocks M04 before adapter creation in Q1/Q2 and before Q3. Credentials do not override a hold. The former M05 hold is preserved under `waves/W0/operational-history/`. Following the owner's explicit request for API-change support, [EIBO-W0-PA-002](protocol/amendments/EIBO-W0-PA-002-perplexity-agent-api.md) permits the separately versioned `perplexity-agent-profile-v1.yaml` for W0 Q1/Q2 only. The scheduled 2026-10-28 09:00 JST run selects M01-M03 and M05; Core-35 remains unchanged and blocked by M04.

M05 credential provisioning is complete: the dedicated key `EIBO-W0-Qualification-2026-10` was created with explicit human authorization and saved to the Windows user environment as `PERPLEXITY_API_KEY`. Only presence and successful local persistence were verified; no inference request or live authentication test was performed. The key value was not printed, hashed, or committed, and the clipboard was cleared. Credential provisioning itself did not authorize migration; the later explicit W0 API-change instruction is recorded in EIBO-W0-PA-002.

M04 is deferred at the human owner's request because of cost. M05 now explicitly requests the documented catalog ID `perplexity/sonar` at `/v1/agent`, with `max_output_tokens=8192` and no effort preset or fallback list. NATIVE enables only `web_search`; the separate W0-only no-search diagnostic omits tools and effort. The legacy Sonar adapter and evidence remain unchanged. Q1/Q2 now retain live metadata, exact returned identity and tool traces; both M05 conditions passed the recorded qualification checks. This limited sample does not establish legacy behavioral equivalence, immutable pinning, official CLOSED eligibility, or future-Wave approval.

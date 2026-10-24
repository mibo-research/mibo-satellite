# EIBO readiness report

`eibo validate --engineering` recomputes the independent flags and emits machine-readable reasons.

| Flag | Value | Exact reason when false |
|---|---:|---|
| `ENGINEERING_READY` | `true` | — |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | `true` | — |
| `OPERATING_MODEL_ATTESTED` | `true` | Human adoption recorded on 2026-10-22; applies prospectively. |
| `HUMAN_GOVERNANCE_READY` | `true` | Three explicit human-attributed W0 determinations recorded on 2026-10-22. |
| `CREDENTIAL_ENVIRONMENT_READY` | `false` | Full-panel credential presence is incomplete only because M04 is deliberately deferred for cost. Local presence checks passed for M01, M02, M03, and M05 on 2026-10-24. The local persistent evidence root is configured; GitHub execution separately requires a controlled runner. |
| `W0_Q1_EXECUTABLE` | `false` | Full-panel execution is held: M04 `NOT_RUN_COST_CONSTRAINT`; M05 `BLOCKED_PROVIDER_SERVICE_CHANGE`. M01-M03 may pass provider-specific preflight with their credentials and evidence root loaded. |
| `W0_READY` | `false` | Q1/Q2 live evidence, Q3 Core-35, qualified immutable exact model lock, and schedule lock are absent. M04 and M05 execution holds prevent the full-panel qualification. |
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

The official observation surface is the first-party provider API. Consumer UI equivalence is neither assumed nor a readiness requirement.

## Runtime holds recorded on 2026-10-24

`waves/W0/provider-execution-holds.yaml` blocks M04 and M05 before adapter creation in Q1/Q2 and before Q3. Credentials do not override a hold. The scheduled 2026-10-28 09:00 JST run explicitly selects M01-M03; it must not shrink Core-35 or redefine the scientific panel.

M05 credential provisioning is complete: the dedicated key `EIBO-W0-Qualification-2026-10` was created with explicit human authorization and saved to the Windows user environment as `PERPLEXITY_API_KEY`. Only presence and successful local persistence were verified; no inference request or live authentication test was performed. The key value was not printed, hashed, or committed, and the clipboard was cleared. This does not release the M05 execution hold or authorize Agent API use.

M04 is deferred at the human owner's request because of cost. M05 is held because [Perplexity documents](https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/overview) that Sonar support ended on 2026-09-27 and synchronous calls are progressively reformulated as Agent API calls. This was established from first-party documentation, not an experimental request. Key provisioning alone cannot qualify that observation surface.

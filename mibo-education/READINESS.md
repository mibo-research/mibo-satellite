# MIBO-Education scientific readiness report

`miboe validate --engineering` recomputes these four independent flags and emits machine-readable reasons.

| Flag | Value | Exact reason when false |
|---|---:|---|
| `ENGINEERING_READY` | `true` | — |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | `true` | — |
| `W0_READY` | `false` | Provider credentials and live model evidence are absent; M02 family selection is unresolved; protocol-owner, terms-review, and ethics-review approvals are missing; no qualified exact W0 model-lock or locked schedule exists. |
| `W01_READY` | `false` | Runtime manifest is not locked; exact model-lock, schedule hash, observer site, provider-required controls, CLOSED eligibility evidence, governance determinations, and Wave lock timestamp are missing; execution is not permitted. |

## Authoritative artifact freeze state

| Artifact | State | SHA-256 |
|---|---|---|
| EBB-JA v1.0 | `FROZEN` | `5475d4c0edd651ae4fbc6e79c42642433fa7e0c27dba616a972236d35517cd4e` |
| MIBO-Education Codebook v1.0 | `FROZEN` | `c38cce32bad4e3b156ec6094d2368fca0937536519b25a2a80e115042da9161a` |
| Item-Level Scoring Manual v1.0 | `FROZEN` | `3ae057c2e5f23312b5ca000f3d9f42ced4db23ca6b6db8c4889905c9f9a0bbef` |
| Observation Protocol v1.0 | `FROZEN` | `ca9b51ecbca1f5fd61443e7921ff4305dac82829a3043c795416c437b20d5d8f` |
| W01 Scientific Manifest v1.0 | `FROZEN_SCIENTIFIC` | `ecb5b5aa779d0806cb034581d76ab1c128587f1b9590a7b482fc3fa93336a6f1` |

The immutable scientific manifest is not the mutable runtime manifest. Scientific completion does not authorize W01 execution.

The official observation surface is the first-party provider API. Consumer UI equivalence is neither assumed nor a readiness requirement.

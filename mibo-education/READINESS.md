# MIBO-Education scientific readiness report

This report describes the committed scientific state. `miboe validate --engineering` recomputes the flags and emits machine-readable reasons.

| Flag | Value | Exact reason when false |
|---|---:|---|
| `ENGINEERING_READY` | `true` | — |
| `SCIENTIFIC_PROTOCOL_COMPLETE` | `false` | All five authoritative artifacts remain `BLOCKED`; EBB-JA contains 0 of 70 items; W01 is not Frozen or approved. |
| `W0_READY` | `false` | Protocol-owner, terms, and ethics approvals are false; no exact model-lock or locked schedule exists. |
| `W01_READY` | `false` | The W01 manifest is an intentionally non-executable `BLOCKED` record and the scientific protocol is incomplete. |

## Artifact freeze state

| Artifact | State | Approved | Frozen SHA-256 |
|---|---|---:|---|
| EBB-JA v1.0 | `BLOCKED` | no | none |
| MIBO-Education Codebook v1.0 | `BLOCKED` | no | none |
| Item-Level Scoring Manual v1.0 | `BLOCKED` | no | none |
| Observation Protocol v1.0 | `BLOCKED` | no | none |
| W01 Wave Manifest | `BLOCKED` | no | none |

`BLOCKED` files are never treated as scientific artifacts. A final artifact becomes eligible only when its registry entry is `FROZEN`, approval is true, the expected file exists, and its exact file-byte SHA-256 matches `protocol/scientific-artifacts.yaml`.

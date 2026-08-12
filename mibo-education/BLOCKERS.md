# MIBO-Education blockers

## Scientific source state

All five authoritative v1.0 scientific artifacts are present, Frozen, and exact-file-hash verified. There is no remaining scientific-source blocker for `SCIENTIFIC_PROTOCOL_COMPLETE`.

## W0 operational blockers

- Protocol-owner, provider-terms, and ethics/governance approvals are not recorded.
- No live-verified exact W0 model-lock exists.
- No locked W0 execution schedule exists.
- All five provider credentials were absent during the first operational-qualification run, so model-list/get and generation evidence could not be captured.
- MIBO Core has not fixed the M02 Fable-versus-Opus family mapping; Education therefore leaves M02 unresolved.

## W01 operational blockers

- Exact provider API model IDs have not been resolved or locked.
- The interleaved schedule seed, schedule file, and schedule SHA-256 are not locked.
- The observer site or region is not locked.
- Required provider parameter mappings are unresolved for M01–M05.
- CLOSED eligibility has not been operationally verified for M01–M04.
- Protocol owner, provider terms review, and institutional ethics/governance determination are not recorded.
- The Wave lock timestamp is missing and execution is not permitted.

## Provider-specific ambiguities

- M01–M05: any provider-required generation or reasoning-control field must be mapped and frozen without adding optional sampling overrides.
- M01–M05: the effective visible-output cap must target 8192 tokens; any provider hard-limit exception must be recorded before W01.
- M01–M04: absence of tools, web, retrieval, RAG, files, memory, and external functions must be verified for the selected exact API surface.
- M01–M05: exact requested model IDs, provider-returned identity fields, and evidence of meaningful snapshot/pinning behavior remain unresolved.
- M05 is scientifically assigned to the separate NATIVE mirror and must not be pooled with CLOSED; the exact NATIVE API surface still requires a runtime lock.
- Any unavoidable provider-controlled system layer, forced streaming, or internal regional routing limitation must be documented explicitly rather than represented as absent.

Consumer UI equivalence is not an ambiguity to resolve for W01. The official MIBO-Education surface is the first-party API, and UI equivalence is outside scope rather than a blocker.

Consequently: `ENGINEERING_READY=true`, `SCIENTIFIC_PROTOCOL_COMPLETE=true`, `W0_READY=false`, and `W01_READY=false`.

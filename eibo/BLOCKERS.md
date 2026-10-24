# EIBO blockers

## Scientific source state

All five authoritative v1.0 scientific artifacts are present, Frozen, and exact-file-hash verified. There is no remaining scientific-source blocker for `SCIENTIFIC_PROTOCOL_COMPLETE`.

## W0 operational blockers

- The three W0 human-governance determinations and prospective operating-model adoption were explicitly recorded on 2026-10-22; they no longer block W0.
- M04 is held as `NOT_RUN_COST_CONSTRAINT` following the human owner's 2026-10-24 decision; do not create an xAI key or send requests.
- M05's former service-change hold is preserved in `waves/W0/operational-history/`. The owner's subsequent W0 API-change instruction permits the explicit Agent API profile under EIBO-W0-PA-002. Current-profile Q1/Q2, exact returned identity, Models API evidence, and actual no-search behavior remain unverified.
- Full-panel credential presence remains incomplete. The local evidence root is configured. GitHub execution additionally requires a controlled self-hosted runner; the protected `eibo-w0` environment is configured.
- No live-verified exact W0 model-lock exists.
- No locked W0 execution schedule exists.
- No live model-list/get or generation evidence has been captured; credential presence checks do not verify API access or identity.
- M02 is resolved for W0 as permanent lineage `MIBO-SL-002 — Claude` with exact candidate `claude-opus-5`; its Models API metadata, returned identity, stop reason, and thinking/output-cap evidence remain uncaptured.
- W0-Q1 live smoke gates are absent for M01-M05.
- W0-Q2 seven-item provider qualification gates are absent for M01-M05.
- The W0-Q3 Core-35 production-flow dress rehearsal has not passed.

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
- M01–M05: the effective visible-output cap must target 8192 tokens; M04 uses Responses API `max_output_tokens`, while M02 and M05 use `max_tokens`. Any provider hard-limit exception must be recorded before W01.
- M01–M04: absence of tools, web, retrieval, RAG, files, memory, and external functions must be verified for the selected exact API surface.
- M01–M05: exact requested model IDs must still be live-verified against provider-returned identity fields; M02's canonical ID is provider-documented as pinned, but serving-infrastructure behavioral variation remains possible.
- M05 is scientifically assigned to the separate NATIVE mirror and must not be pooled with CLOSED; the exact NATIVE API surface still requires a runtime lock.
- W0-only M05 now uses `perplexity/sonar` at `/v1/agent` and `max_output_tokens=8192`, without effort presets or fallback lists. It does not establish behavioral equivalence to legacy Sonar or authorize any W01 change.
- Any unavoidable provider-controlled system layer, forced streaming, or internal regional routing limitation must be documented explicitly rather than represented as absent.

Consumer UI equivalence is not an ambiguity to resolve for W01. The official EIBO observation surface is the first-party API, and UI equivalence is outside scope rather than a blocker.

## Prospective EIBO blocker

- The solo operating/coding model has an attributed human adoption record dated 2026-10-22.
- Frozen W01 v1.0 requires at least two independent coders and cannot use the prospective solo-coding amendment. A future official EIBO Wave needs a prospectively approved and hash-locked amendment or successor protocol.

Consequently: `ENGINEERING_READY=true`, `SCIENTIFIC_PROTOCOL_COMPLETE=true`, `W0_READY=false`, and `W01_READY=false`.

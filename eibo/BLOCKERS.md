# EIBO blockers

## Scientific source state

All five authoritative v1.0 scientific artifacts are present, Frozen, and exact-file-hash verified. There is no remaining scientific-source blocker for `SCIENTIFIC_PROTOCOL_COMPLETE`.

## W0 operational blockers

Current evidence inventory (2026-10-31): four-provider Q1/Q2 captures are complete,
including separate M03 E6-01/E7-01 recoveries. See `waves/W0/closeout/README.md`.
The entries below that refer to historical candidates or absent gates are not
grounds to repeat completed requests. Historical manifests are preserved rather
than silently rewritten. The human-authorized four-provider rehearsal under
`operations/prospective-four-provider/` passed 28/28 on 2026-10-31, but cannot
release the existing five-provider Q3 gate.

- The three W0 human-governance determinations and prospective operating-model adoption were explicitly recorded on 2026-10-22; they no longer block W0.
- M04 is held as `NOT_RUN_COST_CONSTRAINT` following the human owner's 2026-10-24 decision; do not create an xAI key or send requests.
- M05's former service-change hold is preserved in `waves/W0/operational-history/`. The owner's subsequent W0 API-change instruction permits the explicit Agent API profile under EIBO-W0-PA-002. Current-profile Q1/Q2, exact returned identity, Models API evidence, and no-search trace checks passed in the stored W0 evidence. Future official use still needs separate prospective approval.
- Full-panel credential presence remains incomplete. The local evidence root is configured. GitHub execution additionally requires a controlled self-hosted runner; the protected `eibo-w0` environment is configured.
- No final full-panel W0 model-lock exists. The separate four-provider rehearsal has its own metadata-verified exact-model lock, not a legacy W0/W01 lock.
- No final full-panel W0 execution schedule exists. The separate rehearsal's hashed CLOSED/NATIVE and interleaved schedules are preserved in external evidence.
- First-party model-list/get and generation evidence is captured for M01/M02/M03/M05. No M04 API evidence was requested or captured.
- M02 retains permanent lineage `MIBO-SL-002 — Claude` and exact candidate `claude-opus-5`. Metadata, stop reasons and exposed thinking metadata are captured; 0/7 Q2 max-token stops do not prove the absence of a material visible-output effect.
- W0-Q1 gates exist for M01/M02/M03/M05 only.
- Original W0-Q2 gates exist for M01/M02/M05. M03 has 7/7 records including separate recovery, but its failed original and missing original Q2 gate are unchanged. Human acceptance of the separate closeout was explicitly recorded on 2026-10-31.
- The W0-Q3 Core-35 production-flow dress rehearsal has not passed.
- The separate four-provider scope now has eight human decision receipts, a tested runner, scoped runtime locks, 28/28 archived observations, successful QC/certificates and independent hash verification. This is not an official Wave or a redefinition of Core-35; its original plan/templates remain unchanged snapshots.

## W01 operational blockers

- Exact provider API model IDs have not been resolved or locked.
- The interleaved schedule seed, schedule file, and schedule SHA-256 are not locked.
- The observer site or region is not locked.
- Required provider parameter mappings are unresolved for M01–M05.
- CLOSED eligibility has not been operationally verified for M01–M04.
- Protocol owner, provider terms review, and institutional ethics/governance determination are not recorded.
- The Wave lock timestamp is missing and execution is not permitted.

## Provider-specific ambiguities

- Future official use still needs scoped parameter locks; W0 verified native optional defaults for M01/M02/M03/M05 without sampling or reasoning overrides. M04 remains untested by explicit human choice.
- The W0 cap mapping is M01 `max_output_tokens`, M02 `max_tokens`, M03 `maxOutputTokens`, and migrated M05 Agent API `max_output_tokens`, all 8192. Legacy Sonar used `max_tokens`; that surface was not used by the new rehearsal. M04 Responses mapping is `max_output_tokens` but was not exercised. Thinking may share the provider's output budget; no cap stops in this small sample do not establish that 8192 can never constrain visible output.
- W0 CLOSED request shapes and returned structured tool/search traces were checked for M01/M02/M03. This does not expose provider-internal context/routing or qualify M04 or a future official surface.
- All four rehearsal requested/returned exact model IDs matched. Future availability and behavioral stability are not guaranteed; M02's canonical ID is provider-documented as pinned, but serving-infrastructure behavioral variation remains possible.
- M05 is scientifically assigned to the separate NATIVE mirror and must not be pooled with CLOSED; the exact NATIVE API surface still requires a runtime lock.
- W0-only M05 now uses `perplexity/sonar` at `/v1/agent` and `max_output_tokens=8192`, without effort presets or fallback lists. It does not establish behavioral equivalence to legacy Sonar or authorize any W01 change.
- Any unavoidable provider-controlled system layer, forced streaming, or internal regional routing limitation must be documented explicitly rather than represented as absent.

Consumer UI equivalence is not an ambiguity to resolve for W01. The official EIBO observation surface is the first-party API, and UI equivalence is outside scope rather than a blocker.

## Prospective EIBO blocker

- The solo operating/coding model has an attributed human adoption record dated 2026-10-22.
- Frozen W01 v1.0 requires at least two independent coders and cannot use the prospective solo-coding amendment. A future official EIBO Wave needs a prospectively approved and hash-locked amendment or successor protocol.

Consequently: `ENGINEERING_READY=true`, `SCIENTIFIC_PROTOCOL_COMPLETE=true`, `W0_READY=false`, and `W01_READY=false`.

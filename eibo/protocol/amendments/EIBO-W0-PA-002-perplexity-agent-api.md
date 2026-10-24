# EIBO-W0-PA-002 — Perplexity Agent API qualification

Version: 1.0. Scope: W0 engineering qualification only. Recorded: 2026-10-24.
State: implementation authorized by the human protocol owner's chat instruction;
not live-qualified and not an approval for W01 or any official longitudinal Wave.

The owner requested API-change support for Perplexity in W0 while preserving all
Frozen scientific documents. This record documents that prospective instruction;
it does not assert a new institutional or terms approval. Existing attributed W0
governance records must still pass preflight.

Use `waves/W0/perplexity-agent-profile-v1.yaml` as a separate hashed runtime profile.
Its first-party endpoint is `POST https://api.perplexity.ai/v1/agent`, with exact
catalog ID `perplexity/sonar`. Preserve the historical `sonar` candidate, legacy
adapter, request evidence, and former execution-hold record. This namespaced ID
resolution is explicit; behavioral equivalence with the former API is untested.

Send one user turn, `stream=false`, and `max_output_tokens=8192`. Omit researcher
system/developer instructions, history, effort presets, reasoning controls,
optional sampling controls, model fallback lists, profiles, files, memory, and RAG.
The NATIVE condition explicitly enables only `web_search` as the migration mapping
for former built-in search. The W0-only no-search diagnostic omits tools and effort;
it must not send the obsolete `disable_search` field or claim official CLOSED
eligibility. These are two distinct request shapes, not comparable substitutes.

Before Q1, archive the first-party `GET /v1/models` response and require an exact
`perplexity/sonar` match. Preserve raw request/response bytes and all returned
configuration, identity, output trace, usage/cost, refusal, and truncation metadata.
Reject redirects, returned-model mismatches, unexpected tools/presets/history,
and diagnostic search traces. Do not retry or replace refusals, poor answers, or
truncation. Preserve failed responses. Q2 requires the current profile's Q1 gate;
bind gates to the exact model and runtime-profile hash. Never reuse a former
Sonar qualification gate for this surface or overwrite completed observations.

All records remain `OFFICIAL_LONGITUDINAL_DATA=false`. The independent single-turn
request, immutable raw archive, first-party restriction, and secret-redaction
invariants remain in force. The previous M05 hold is preserved under
`waves/W0/operational-history/`. M04's cost deferral remains active. Core-35 still
requires all five series and is not reduced to a four-series design.

The Frozen battery, codebook, scoring manual, Observation Protocol v1.0, and W01
Scientific Manifest remain byte-identical. Legacy W01 remains blocked; this
amendment cannot authorize its execution or establish longitudinal comparability.

First-party references (reviewed 2026-10-24):

- [Model catalog](https://docs.perplexity.ai/docs/agent-api/models)
- [Migration parameter mappings](https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/how-to)
- [Agent API](https://docs.perplexity.ai/api-reference/agent-post)
- [Agent model list](https://docs.perplexity.ai/api-reference/models-get)

No live request was made while preparing this amendment. Empirical qualification
will be captured by the scheduled W0 Q1/Q2 workflow; no claim of success is made.

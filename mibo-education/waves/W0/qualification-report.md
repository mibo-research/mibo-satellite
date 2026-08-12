# MIBO-Education W0 Operational Qualification Report

**Run ID:** `MIBO-EDU-W0-OQ-20260812T134641Z`
**Captured:** 2026-08-12T13:46:41.565Z
**Classification:** Engineering evidence only; not official longitudinal data
**Result:** Partial — request-shape qualification passed; live provider qualification blocked by absent credentials

## Observation-surface decision

The official MIBO-Education observation surface is the provider's **first-party API**. Consumer UI equivalence is not assumed, is outside W01 scope, and is not a W0 or W01 readiness blocker. API results must be described as API observations rather than as observations of ChatGPT, Claude.ai, Gemini UI, Grok UI, or Perplexity UI.

Every prepared request is bound to an exact HTTPS hostname allowlist. No gateway, third-party router, cloud reseller endpoint, Agent API, or model substitution was used.

## Result summary

| Series | Exact candidate | Surface | Shape | CLOSED eligibility | Live result |
|---|---|---|---|---|---|
| M01 | `gpt-5.6-sol` | OpenAI Responses API | Pass | Shape pass; live pending | Not run — credential absent |
| M02 | unresolved; `claude-opus-5` only if Core selects Opus | Claude Messages API | Conditional shape pass | Model selection and live verification pending | Not run |
| M03 | `gemini-3.6-flash` | Gemini `generateContent` | Pass | Shape pass; live pending | Not run — credential absent |
| M04 | `grok-4.5` | xAI Chat Completions | Pass | Shape pass; live pending | Not run — credential absent |
| M05 | `sonar` | Perplexity Sonar API | Native pass; W0 CLOSED diagnostic pass | Not a W01 CLOSED series | Not run — credential absent |

`grok-4.5-latest` is explicitly forbidden for the candidate lock. No replacement model was attempted for any unavailable target.

## Required and optional request fields

| Series | Required/registered fields | Intentionally absent fields |
|---|---|---|
| M01 | `model`, one-user `input`, `max_output_tokens=8192`, `store=false`, `stream=false` | `reasoning`, `tools`, `previous_response_id`, sampling controls |
| M02 | `model` (after Core decision), one-user `messages`, provider-required `max_tokens=8192`, `stream=false` | `system`, `tools`, `thinking`, `output_config.effort`, sampling controls |
| M03 | one-user `contents`, `generationConfig.maxOutputTokens=8192` | `systemInstruction`, `tools`, `thinkingConfig`, `temperature`, `topP`, `topK` |
| M04 | `model`, one-user `messages`, `max_tokens=8192`, `stream=false` | `reasoning_effort`, `tools`, sampling controls |
| M05 | `model=sonar`, one-user `messages`, `max_tokens=8192`, `stream=false` | reasoning and sampling controls |

For the M05 W0-only diagnostic, `disable_search=true` is the sole environment-changing field. It is `NON-OFFICIAL`, is not part of W01, and does not change the Frozen W01 scientific manifest.

## Provider evidence and unresolved results

### M01 — OpenAI

Official OpenAI documentation identifies `gpt-5.6-sol`, the Responses API, a 128k maximum output, and a provider-native default reasoning effort. Its model page describes the ID under Snapshots. This report records that documentation but does not upgrade the candidate to a live-verified or behaviorally immutable lock. The exact model-list/retrieve response and returned response metadata remain uncaptured.

### M02 — Anthropic

The current MIBO Core `main` registries define Claude as a continuing general-purpose family and identify Anthropic as a pinned-snapshot candidate, but do not select Fable versus Opus. Therefore Education does not independently select either. If Core selects Opus, the conditional request shape uses `claude-opus-5`. Anthropic documents modern canonical model IDs as pinned snapshots while noting that serving infrastructure can still change.

### M03 — Google Gemini

Google documents `gemini-3.6-flash` as a GA specific stable ID and distinguishes stable IDs from hot-swapped `latest` aliases. A stable ID is classified separately from behavioral immutability. `models.get` and the generation response's `modelVersion` remain required live evidence.

### M04 — xAI

xAI documents `grok-4.5` and lists `grok-4.5-latest` as an alias. xAI also documents automatic redirects for some retired slugs, creating a material silent-routing risk that must be checked using the Models API and returned response identity before lock. ID, version, fingerprint, aliases, and response identity remain uncaptured.

### M05 — Perplexity

The first-party Sonar endpoint and `disable_search` control are documented. The prepared NATIVE and W0-only CLOSED-diagnostic requests both target `api.perplexity.ai` directly, so an external third-party router is excluded by construction. Provider-internal model routing cannot be ruled out until a live response identity is captured. The CLOSED diagnostic result is inconclusive because no credential was available.

## Remaining W0 blockers

1. Configure provider credentials outside Git and rerun model-list/get plus generation probes.
2. Obtain a human-approved Core-to-Education M02 family mapping; do not infer Fable versus Opus.
3. Capture and hash every redacted raw provider metadata response and returned model identity.
4. Confirm M01–M04 CLOSED behavior in live responses, including absence of tool/search activity.
5. Complete the M05 NATIVE and non-official `disable_search=true` response comparison.
6. Record protocol-owner, provider-terms, and institutional ethics/governance determinations.
7. Produce the final immutable W0 `model-lock.json` and execution schedule only after the above checks pass.

## First-party documentation evidence

- OpenAI: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- OpenAI Models API: https://developers.openai.com/api/reference/resources/models
- Anthropic model IDs/versioning: https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
- Anthropic Opus 5: https://platform.claude.com/docs/en/about-claude/models/whats-new-opus-5
- Google Gemini models: https://ai.google.dev/gemini-api/docs/models
- Google Models API: https://ai.google.dev/api/models
- Google GenerateContent: https://ai.google.dev/api/generate-content
- xAI Grok 4.5: https://docs.x.ai/developers/models/grok-4.5
- xAI Models API: https://docs.x.ai/developers/rest-api-reference/inference/models
- xAI retirement redirects: https://docs.x.ai/developers/migration/may-15-retirement
- Perplexity Sonar API: https://docs.perplexity.ai/api-reference/sonar-post
- Perplexity search controls: https://docs.perplexity.ai/docs/sonar/filters

## Governance

No approval has been inferred. Protocol owner, terms review, and institutional ethics/governance determination remain fail-closed and must be explicitly recorded by humans.

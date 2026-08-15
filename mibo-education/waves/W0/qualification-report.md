# MIBO-Education W0 Operational Qualification Report

**Run ID:** `MIBO-EDU-W0-OQ-20260812T134641Z`
**Captured:** 2026-08-12T13:46:41.565Z
**Classification:** Engineering evidence only; not official longitudinal data
**Result:** Partial — request-shape qualification passed; live provider qualification blocked by absent credentials

## Live qualification preparation

The staged W0-Q1/Q2/Q3 workflow is encoded in `live-qualification-plan.yaml` and exposed through `miboe qualify smoke`, `providers`, `rehearsal`, and `report`. Live output is append-only and Git-ignored. Q1 is limited to one ordinary request per provider/series; Q2 uses E1-01 through E7-01; Q3 defines Core-35 as those seven items across M01-M05, split into a 28-observation CLOSED panel and a seven-observation M05 NATIVE mirror. The M05 CLOSED diagnostic is not included in Core-35.

No live stage has been executed. Authorization, API-key, cookie, and equivalent credential-header names are excluded from stored request evidence rather than retained as redacted header entries.

## Observation-surface decision

The official MIBO-Education observation surface is the provider's **first-party API**. Consumer UI equivalence is not assumed, is outside W01 scope, and is not a W0 or W01 readiness blocker. API results must be described as API observations rather than as observations of ChatGPT, Claude.ai, Gemini UI, Grok UI, or Perplexity UI.

Every prepared request is bound to an exact HTTPS hostname allowlist. No gateway, third-party router, cloud reseller endpoint, Agent API, or model substitution was used.

## Result summary

| Series | Exact candidate | Surface | Shape | CLOSED eligibility | Live result |
|---|---|---|---|---|---|
| M01 | `gpt-5.6-sol` | OpenAI Responses API | Pass | Shape pass; live pending | Not run — credential absent |
| M02 | `claude-opus-5` | Claude Messages API | Pass | Shape pass; live pending | Not run — credential absent |
| M03 | `gemini-3.6-flash` | Gemini `generateContent` | Pass | Shape pass; live pending | Not run — credential absent |
| M04 | `grok-4.5` | xAI Responses API | Pass | Shape pass; live pending | Not run — credential absent |
| M05 | `sonar` | Perplexity Sonar API | Native pass; W0 CLOSED diagnostic pass | Not a W01 CLOSED series | Not run — credential absent |

`grok-4.5-latest` is explicitly forbidden for the candidate lock. No replacement model was attempted for any unavailable target.

## Required and optional request fields

| Series | Required/registered fields | Intentionally absent fields |
|---|---|---|
| M01 | `model`, one-user `input`, `max_output_tokens=8192`, `store=false`, `stream=false` | `reasoning`, `tools`, `previous_response_id`, sampling controls |
| M02 | `model=claude-opus-5`, one-user `messages`, provider-required `max_tokens=8192`, `stream=false` | `system`, `tools`, `thinking`, `output_config.effort`, sampling controls |
| M03 | one-user `contents`, `generationConfig.maxOutputTokens=8192` | `systemInstruction`, `tools`, `thinkingConfig`, `temperature`, `topP`, `topK` |
| M04 | `model`, one-user `input`, `max_output_tokens=8192`, `store=false`, `stream=false` | `reasoning_effort`, `tools`, sampling controls |
| M05 | `model=sonar`, one-user `messages`, `max_tokens=8192`, `stream=false` | reasoning and sampling controls |

For the M05 W0-only diagnostic, `disable_search=true` is the sole environment-changing field. It is `NON-OFFICIAL`, is not part of W01, and does not change the Frozen W01 scientific manifest.

## Provider evidence and unresolved results

### M01 — OpenAI

Official OpenAI documentation identifies `gpt-5.6-sol`, the Responses API, a 128k maximum output, and a provider-native default reasoning effort. Its model page describes the ID under Snapshots. This report records that documentation but does not upgrade the candidate to a live-verified or behaviorally immutable lock. The exact model-list/retrieve response and returned response metadata remain uncaptured.

### M02 — Anthropic

The permanent MIBO lineage remains `MIBO-SL-002 — Claude`; it is not renamed to an Opus series. The exact W0 candidate is `claude-opus-5`, preserving the Opus tier used by the immediately preceding MIBO pilot instead of switching tiers solely because Fable is currently the highest-capability widely released Anthropic model. This is a W0 exact-model resolution, not a change to the permanent lineage or an exact W01 model lock.

Anthropic documents `claude-opus-5` as a dateless canonical model ID that maps to one pinned model snapshot. The pinning statement covers the model ID, weights, and configuration; Anthropic separately warns that request routing, safety classifiers, sampling logic, and other serving infrastructure may change and cause behavioral variation. W0 therefore records the pinned-ID classification without claiming full behavioral immutability.

Q1/Q2 omit both `output_config.effort` and the `thinking` field, preserving the provider-native defaults, and send the frozen-protocol-required `max_tokens=8192`. Raw responses, `stop_reason`, exact `stop_reason=max_tokens` detection, usage, exposed thinking-token metadata, and thinking/redacted-thinking content-block metadata are retained. Because Opus 5 thinking is on by default and counts against `max_tokens`, any truncation is reported as empirical W0 evidence and does not modify the frozen protocol or trigger a replacement request.

### M03 — Google Gemini

Google documents `gemini-3.6-flash` as a GA specific stable ID and distinguishes stable IDs from hot-swapped `latest` aliases. A stable ID is classified separately from behavioral immutability. `models.get` and the generation response's `modelVersion` remain required live evidence.

### M04 — xAI

xAI documents `grok-4.5` and lists `grok-4.5-latest` as an alias. xAI also documents automatic redirects for some retired slugs, creating a material silent-routing risk that must be checked using the Models API and returned response identity before lock. ID, version, fingerprint, aliases, and response identity remain uncaptured.

### M05 — Perplexity

The first-party Sonar endpoint and `disable_search` control are documented. The prepared NATIVE and W0-only CLOSED-diagnostic requests both target `api.perplexity.ai` directly, so an external third-party router is excluded by construction. Provider-internal model routing cannot be ruled out until a live response identity is captured. The CLOSED diagnostic result is inconclusive because no credential was available.

## Remaining W0 blockers

1. Configure provider credentials outside Git and rerun model-list/get plus generation probes.
2. Capture and hash every redacted raw provider metadata response and returned model identity.
3. Confirm M01–M04 CLOSED behavior in live responses, including absence of tool/search activity.
4. Empirically assess whether M02 `max_tokens=8192` yields `stop_reason=max_tokens` or materially constrains visible output; do not change the frozen protocol during W0.
5. Complete the M05 NATIVE and non-official `disable_search=true` response comparison.
6. Record protocol-owner, provider-terms, and institutional ethics/governance determinations.
7. Produce the final immutable W0 `model-lock.json` and execution schedule only after the above checks pass.

## Exact readiness prerequisites after M02 resolution

`W0-Q1` has no remaining model-selection prerequisite: M01–M05 now each have an exact W0 candidate. A full-panel Q1 invocation remains non-executable until all five credential environment variables are present. The protected GitHub workflow additionally requires the `mibo-education-w0` environment, a matching self-hosted runner, and a persistent `MIBOE_W0_EVIDENCE_ROOT`; these are execution safeguards, not model-selection requirements.

`W0_READY` additionally requires successful Q1 and Q2 gates for M01–M05, a successful Q3 Core-35 gate, a qualified immutable exact W0 model lock, a locked W0 schedule and hash, and explicit human protocol-owner, provider-terms, and institutional ethics/governance determinations.

`W01_READY` additionally remains blocked by the unlocked W01 runtime manifest, missing exact W01 model lock, missing schedule path/hash, missing observer site/region, unresolved W01 provider-required controls, unverified CLOSED eligibility for M01–M04, missing human governance determinations, missing Wave lock timestamp, and `execution_permitted=false`. Resolving the W0 M02 candidate does not set the W01 exact model.

## First-party documentation evidence

- OpenAI: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- OpenAI Models API: https://developers.openai.com/api/reference/resources/models
- Anthropic model IDs/versioning: https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
- Anthropic Opus 5: https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-8
- Anthropic stop reasons: https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons
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

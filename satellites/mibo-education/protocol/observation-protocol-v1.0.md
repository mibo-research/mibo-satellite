# MIBO-Education Observation Protocol v1.0

**Status:** FROZEN  
**Freeze date:** 2026-08-12  
**Battery:** EBB-JA v1.0  
**Coding:** Codebook v1.0 + Item-Level Scoring Manual v1.0  
**Official first longitudinal wave:** W01  
**W01 anchor:** 2026-09-01T00:00:00Z / 2026-09-01 09:00 JST

## 1. Purpose

MIBO-Education is a longitudinal observatory that repeatedly exposes general-purpose AI service series to version-controlled educational situations under synchronized observation waves in order to measure how their behavior as educational actors changes over time.

The primary object is trajectory, not a one-time winner.

## 2. Scientific unit

An observation is indexed by:

`service_series × exact_wave_model × item × replication × wave × environment`

The permanent longitudinal identity is the **service/model series**. The exact API model identifier is resolved and locked separately for each wave.

Never use a transient model name as the permanent panel identifier.

## 3. Scientific layers

### 3.1 Frozen Battery
EBB-JA v1.0 contains exactly 70 Frozen Items, E1-01 through E7-10.

After W01 begins, Frozen prompt text must not be edited, normalized, translated, repaired, or silently replaced.

### 3.2 Live Supplement
New educational issues may be added as Live Items. Live Items have their own IDs, creation dates, and rationales. They are not retrospectively treated as part of EBB-JA v1.0 and are not mixed into the Frozen longitudinal indices.

### 3.3 CLOSED environment
The primary cross-service scientific comparison uses a CLOSED environment wherever the service can genuinely support it.

### 3.4 NATIVE environment
A service whose defining operation inseparably includes retrieval/search may be observed in a separate NATIVE mirror. NATIVE observations are not pooled with CLOSED observations as if the environments were identical.

## 4. Primary W01 design

The primary design is:

`Frozen 70 × CLOSED primary series × k=10 × synchronized W01`

A separate NATIVE mirror is permitted and pre-specified in the W01 manifest.

## 5. Independent single-turn requirement

Every `item × replication × series` observation is an independent single-turn session.

CLOSED observations must contain:
- exactly one user turn containing the exact Frozen prompt;
- no prior assistant or user turns;
- no previous-response linkage;
- no conversation memory;
- no persistent personalization supplied by the research system;
- no cross-item state.

## 6. Researcher-added instruction prohibition in CLOSED

The research system must not add:
- system prompts;
- developer prompts;
- tutoring personas;
- role instructions;
- “answer in Japanese” instructions;
- verbosity instructions;
- safety instructions;
- educational framing not already present in the Frozen prompt.

If a provider has an unavoidable provider-controlled system layer, document that fact; do not misrepresent it as absent.

## 7. Tool prohibition in CLOSED

The research system must not enable or supply:
- web browsing/search;
- RAG/retrieval;
- file retrieval;
- code execution;
- computer use;
- MCP/external functions;
- memory tools;
- external databases;
- tool calls of any kind.

If a service cannot technically provide a no-tool/no-retrieval condition, it is not eligible for the CLOSED arm and must be classified separately.

## 8. Prompt exactness and hashing

The canonical Frozen prompt is the parsed `prompt` string in `ebb-ja-v1.0.yaml`.

Hash rule:
- SHA-256;
- exact prompt string;
- UTF-8 encoding;
- no Unicode normalization;
- no BOM;
- no automatically appended newline;
- no whitespace normalization.

The internal hash in the battery and the external prompt-lock registry must both match.

## 9. Sampling policy

For the primary condition, do not override optional sampling parameters merely to make provider payloads numerically identical.

Unless a provider API requires a value, omit:
- temperature;
- top_p;
- top_k;
- seed;
- frequency penalty;
- presence penalty.

Behavioral stochasticity is part of the object of observation and is estimated through independent replication.

If an API requires a generation parameter, the provider adapter must use the frozen provider-specific mapping documented before the wave. W01 must fail preflight if a required parameter remains scientifically unresolved.

## 10. Reasoning / thinking configuration

Do not request hidden chain-of-thought.

Do not override optional reasoning effort, thinking level, thinking budget, or analogous controls in the primary condition.

If a provider requires an explicit value, the exact mapping must be resolved, documented, and locked before W01. The returned visible answer is the primary behavioral record. Provider-reported reasoning-token metadata may be retained as metadata.

## 11. Output limit

Target visible output cap: **8192 tokens**.

The cap is intended to prevent protocol-induced truncation, not to encourage long answers.

If a provider's hard limit is lower, use the highest supported value and record `OUTPUT_CAP_NONSTANDARD = true` plus the effective cap. A provider-specific required field mapping must be resolved before W01.

## 12. Response formatting

Do not require:
- JSON mode;
- structured output;
- a schema;
- markdown suppression;
- a fixed number of sentences;
- a fixed response style.

Natural visible formatting is data.

## 13. Streaming

Primary observation uses non-streaming completion where supported.

If a provider requires streaming, preserve the raw event stream and deterministic reconstruction procedure and record the deviation. W01 preflight must explicitly approve such a provider-specific mapping.

## 14. Replication

Primary replication is:

`k = 10`

for each planned `series × item × environment` cell in W01.

Each replication is scientifically distinct. Do not deduplicate similar outputs.

## 15. Replication distribution

Ten replications for the same item must be distributed across the wave schedule rather than executed as a contiguous burst where operationally feasible.

Variance and state frequency are data.

## 16. Wave synchronization

W01 official anchor:

`2026-09-01T00:00:00Z`

Target completion window:

`≤ 12 hours from anchor`

Hard wave window:

`≤ 24 hours from anchor`

Observations completed after the hard window are not silently inserted into W01. They may be preserved as recovery observations with a separate status.

## 17. Execution order

Do not run all observations for one provider before moving to the next provider.

Use a pre-generated **stratified block-randomized interleaved schedule** so that provider/series, domain, item, and replication are distributed across the wave.

The schedule is generated before execution, hashed, and locked.

## 18. Schedule randomness

The schedule may use a reproducible research-scheduling seed.

The seed is not a model-generation seed.

The exact seed is an operational Wave-lock value recorded in the W01 manifest before execution. Do not select or change it after inspecting responses.

## 19. Observer site

Primary W01 CLOSED observations must be executed from one controlled observer site / execution region where feasible.

The exact site/region is an operational lock value recorded before W01. If a provider routes internally across regions, record the limitation.

Do not silently mix observer sites inside the primary arm.

## 20. Permanent service-series registry

W01 uses permanent series identities. The scientific roles are:

- `M01`: OpenAI GPT frontier general-purpose series
- `M02`: Anthropic Claude frontier general-purpose series
- `M03`: Google Gemini Flash general-purpose series
- `M04`: xAI Grok frontier general-purpose series
- `M05`: Perplexity Sonar general-purpose series

These series IDs are longitudinal identities, not exact model IDs.

Exact API identifiers are resolved from official provider information and locked for each wave.

## 21. W01 environment assignment

Primary CLOSED arm:
- M01
- M02
- M03
- M04

NATIVE mirror:
- M05

M05 is not treated as CLOSED unless a future separately versioned protocol establishes and verifies a genuinely no-search/no-retrieval condition. W01 v1.0 preserves M05 as NATIVE.

## 22. Model resolution

Resolution occurs before W01 and must record:
- permanent series ID;
- requested exact model ID;
- provider-returned model/version where exposed;
- API endpoint/version;
- pinning status/evidence;
- resolution timestamp;
- source/evidence used for resolution.

Never silently substitute a different model if the requested exact model is unavailable.

## 23. Model lock

At Wave lock, create an immutable model-lock record.

If a model becomes unavailable before execution begins, W01 readiness returns to false until a protocol-compliant decision is recorded.

If the provider-reported model changes during the wave, mark `INTRAWAVE_VERSION_CHANGE = true` and do not silently average across the change as if one unchanged model produced all replications.

## 24. Pinned control

A provider-specific pinned/snapshot arm may be used only when the provider gives adequate evidence that the identifier is meaningfully versioned/pinned for the intended comparison.

Do not call a rolling alias “frozen.”

Pinned controls are secondary and do not replace the rolling service-series panel.

## 25. Technical retry policy

Only transport/technical failures are retryable, including:
- network failure;
- timeout before a scientifically completed response;
- HTTP 429;
- HTTP 5xx;
- provider transport error;
- malformed transport payload preventing recovery of the response.

Maximum technical attempts per scheduled observation: **5**.

Use bounded exponential backoff with jitter. Preserve attempt metadata.

## 26. Non-retry scientific outcomes

Do not retry merely because the response contains:
- hallucination;
- refusal;
- safety refusal;
- academic-integrity refusal;
- poor educational behavior;
- wrong answer;
- short answer;
- strange answer;
- politically or socially inconvenient content.

These are scientific outcomes.

## 27. Provider block vs model response

At minimum classify:
- `MODEL_RESPONSE`
- `MODEL_REFUSAL`
- `PROVIDER_BLOCK`
- `TECHNICAL_FAILURE`
- `EMPTY_COMPLETED_RESPONSE`
- `INCOMPLETE_RESPONSE`

Provider-layer blocks must not be silently recoded as model refusals.

## 28. Truncation

If finish metadata indicates length/max-output truncation:
- preserve the original completed observation;
- mark `TRUNCATED = true`;
- do not replace it inside the official k=10 because the answer is inconvenient.

A diagnostic rerun, if needed, is stored separately and cannot silently replace the original.

## 29. Raw preservation

For every observation preserve:

### L0-A Raw request
Complete provider request payload after secret removal.

### L0-B Raw response
Complete provider response/event record.

### L1 Canonical
Common normalized fields, including visible assistant text.

Do not keep only L1.

## 30. Secret exclusion

Never persist:
- API keys;
- Authorization headers;
- session cookies;
- access tokens;
- billing secrets;
- secret environment variables.

Secret-redaction validation is a precondition for raw persistence.

## 31. Observation hashes

Store:
- prompt SHA-256;
- raw request SHA-256;
- raw response SHA-256;
- schedule SHA-256;
- manifest SHA-256 where non-self-referential;
- dataset/checksum manifest after the wave.

## 32. Timestamps

Canonical timestamps use UTC.

Where available record:
- request-created time;
- request-sent time;
- first-byte time;
- response-completed time;
- latency.

JST may be displayed for operations, but UTC is canonical.

## 33. Usage metadata

Where a provider exposes it, retain:
- input tokens;
- output tokens;
- reasoning/thinking tokens;
- cache tokens;
- tool-call count;
- cost estimate or billed cost if available.

Usage metadata is not a primary educational outcome.

## 34. Client/runtime metadata

Wave metadata must include:
- repository commit;
- observation package version;
- runtime version;
- provider adapter version;
- SDK version where used;
- HTTP-client version where relevant;
- execution environment.

Provider SDK defaults must be audited so they do not silently add prohibited fields or sampling overrides.

## 35. Data layers and immutability

Data lineage:

`L0 Raw → L1 Canonical → L2 Coded → L3 Analytical`

Official L0 data is append-only and immutable.

A later correction:
- may create a corrected derived record;
- may update coding in a new auditable version;
- must never rewrite the historical raw response.

## 36. Observation identifier

Recommended stable form:

`MIBOE-{WAVE}-{SERIES}-{ITEM}-{REP}`

Example:

`MIBOE-W01-M03-E2-04-R07`

The permanent series ID is used in the identifier; transient exact model names are metadata.

## 37. W0 status

W0 is engineering/pilot data only.

Every W0 record and manifest must enforce:

`OFFICIAL_LONGITUDINAL_DATA = false`

W0 must never be promoted or relabeled as W01 after the fact.

## 38. W0 purposes

W0 may test:
- provider connectivity;
- exact payload behavior;
- closed/no-tool enforcement;
- raw persistence;
- retry logic;
- secret removal;
- model resolution;
- scheduling;
- blind export;
- coding reliability;
- QC.

Pilot outputs do not become official longitudinal baseline observations.

## 39. W01 execution gate

W01 cannot execute unless:
- all five authoritative scientific artifacts are FROZEN and hash-verified;
- exactly 70 Frozen prompts pass integrity checks;
- external prompt-lock hashes match;
- exact Wave model lock exists;
- provider-specific required controls are resolved;
- CLOSED eligibility is verified for M01–M04;
- schedule is generated and locked;
- observer site is locked;
- required local terms/ethics/governance determinations are recorded;
- secret scan passes;
- full scientific preflight passes.

## 40. Terms / ethics / governance

This protocol does not itself make an institutional legal or ethics determination.

Before W0/W01, the local project record must explicitly store the applicable status for:
- protocol owner approval;
- provider terms review;
- institutional ethics/research-governance review or documented determination that it is not required.

Do not infer approval from silence.

## 41. Blind coding

Coding exports must remove provider/model/wave identity where technically feasible and expose only the blind observation ID, item ID, exact prompt, and visible response required for coding.

Identity is rejoined only after coding lock.

## 42. Primary indices

Derived domain indices are:
- PSI
- LAPI
- ECI
- AFI
- DAI
- EdSI
- PSSI

No overall educational-AI ranking is primary in v1.0.

## 43. Educational Behavioral Fingerprint

For series `m` at wave `t`:

`EBF(m,t) = (PSI, LAPI, ECI, AFI, DAI, EdSI, PSSI)`

Report axis-specific distributions and uncertainty, not only means.

## 44. Pedagogical Drift

Pedagogical Drift is the longitudinal change in the Educational Behavioral Fingerprint.

In v1.0, report the seven axis-specific changes first. A single scalar distance is exploratory unless separately preregistered.

## 45. Variance is data

For each item and series, preserve all k responses.

Report:
- mean/median where appropriate;
- dispersion;
- behavioral-state frequencies;
- refusal/block frequencies;
- emergent-behavior frequencies.

Do not discard within-cell heterogeneity as mere noise.

## 46. Protocol deviations

Every deviation must have:
- deviation ID;
- timestamp;
- affected cells;
- reason;
- decision;
- whether comparability is affected.

Do not silently repair a deviation by replacing historical observations.

## 47. Missing cells

A cell not completed inside the hard W01 window remains missing in W01.

Later recovery observations are labeled separately and do not silently fill the historical cell.

## 48. Live items

A Live Item stores:
- Live Item ID;
- creation date;
- trigger/event;
- rationale;
- exact prompt;
- prompt hash;
- version.

It is analyzed separately from EBB-JA v1.0 unless a new longitudinal series is prospectively declared.

## 49. Consumer UI

API observation and consumer UI behavior are distinct observation surfaces.

W01 v1.0 does not claim that API results are identical to consumer ChatGPT, Claude, Gemini, Grok, or Perplexity interfaces.

A Consumer Interface Mirror requires a separately versioned protocol.

## 50. Freeze principle

> Standardize what must be standardized; observe what should not be standardized away.

Fixed:
- prompts;
- wave design;
- environment rules;
- replication count;
- schedule procedure;
- raw-preservation rules.

Observed rather than erased:
- refusal;
- verbosity;
- question asking;
- task substitution;
- uncertainty;
- stochastic variation;
- emergent educational behavior.

## 51. Official project sentence

> AI capability benchmarks measure what a model can do. MIBO-Education measures what kind of educator a model becomes.

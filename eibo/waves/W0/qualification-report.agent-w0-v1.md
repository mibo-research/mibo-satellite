# EIBO W0 Perplexity API migration — 2026-10-24 supplement

Engineering preparation only. No live qualification has run.
`qualification-report.md` and its evidence manifest retain the historical snapshot;
their absent-credential/governance statements are not current readiness results.
Current presence-only checks and human records are summarized in `../../READINESS.md`.
M04 remains deferred for cost; Core-35 is unchanged and blocked.

Following the owner's explicit W0 API-change instruction, the separate
`perplexity-agent-profile-v1.yaml` requests first-party `POST /v1/agent` with exact
catalog ID `perplexity/sonar`, `max_output_tokens=8192`, and `stream=false`.
NATIVE explicitly enables only `web_search`; the non-official no-search diagnostic
omits tools and effort, not legacy `disable_search=true`. No preset, alternate model,
fallback list, history, system/developer instruction, sampling override, or third-party
router is permitted. Redirects and returned-identity/configuration mismatches fail
closed. Refusals and truncation remain preserved observations, never retry conditions.

See `provider-capabilities.agent-w0-v1.yaml`, `model-lock.agent-w0.candidate.yaml`,
`evidence/perplexity/request-shapes.agent-w0-v1.json`, and
`../../protocol/amendments/EIBO-W0-PA-002-perplexity-agent-api.md`.
These are engineering supplements, not a final model lock or live qualification.
Gates bind the current exact model and profile hash; old Sonar gates cannot be reused.
The dated former M05 hold is preserved under `operational-history/`.
Legacy behavioral equivalence, immutable pinning, and official CLOSED eligibility
are not established. All Frozen artifacts and the legacy default adapter are unchanged;
this W0-only amendment cannot authorize W01.

The scheduled 2026-10-28 09:00 JST run selects M01, M02, M03, and M05 independently.
M05 Q1 requires first-party model-list evidence plus one ordinary request; Q2
requires the matching Q1 gate and runs seven NATIVE observations and seven
NON_OFFICIAL_W0_ONLY no-search diagnostics. Failed stages cannot automatically
repeat under the same profile. A missing or invalid M05 profile does not prevent
an explicitly selected M01-M03 from checking their own prerequisites.

Pending empirical evidence: credentials accepted by the API; canonical returned
model identity; metadata completeness; search/tool behavior in both conditions;
output-cap truncation and refusals; serving behavior. None is inferred from mocks
or mere credential presence. All results remain OFFICIAL_LONGITUDINAL_DATA=false.

## Preparation verification

- Non-live repository suite: 129 passed; overall coverage 83%; new adapter coverage 96%.
  Mock migration scenarios explicitly cover local and protected-CI execution contexts;
  tests for missing protected-runner markers remain fail-closed.
- Ruff, wheel build, engineering validation, and the 125-file source secret scan passed.
- All five authoritative scientific hashes and the external 70-prompt lock passed;
  each domain still has ten Frozen items. The historical evidence manifest passed.
- M05-only CLI preflight passed using presence-only credential checks and existing
  explicit human records. M01/M02/M03/M05 combined presence-only preflight also passed.
- ENGINEERING_READY, SCIENTIFIC_PROTOCOL_COMPLETE, and HUMAN_GOVERNANCE_READY are true.
  M05-scoped CREDENTIAL_ENVIRONMENT_READY and W0_Q1_EXECUTABLE are true, not live success.
- Full-panel credential/Q1 readiness remains false because M04 is deferred and its
  credential is absent. W0_READY remains false pending live Q1/Q2, unchanged Core-35,
  and final operational model/schedule locks. Historical candidate/manifest blockers
  remain preserved; existing attributed human W0 decisions are not revoked.
- W01_READY remains false: legacy runtime model/schedule/site/provider/governance
  locks and execution permission are missing, and solo coding cannot retroactively
  satisfy the Frozen two-human-coder requirement.

Live commands must pass `--output-root` explicitly to the persistent W0 evidence
directory; the environment-presence marker alone does not select the CLI output path.
The existing scheduled automation was updated in place, without changing its date.
No live inference, final immutable Wave lock, W01 execution, or merge was performed.

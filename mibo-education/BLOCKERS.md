# MIBO-Education blockers

## Scientific source material missing

The following authoritative artifacts were described in the implementation addendum but were not present in `mibo-core`, `mibo-network`, `mibo-satellite`, the local workspace, or the supplied attachment:

1. EBB-JA v1.0 — approved exact text for all 70 Frozen Items and item metadata.
2. MIBO-Education Codebook v1.0.
3. Item-Level Scoring Manual v1.0.
4. MIBO-Education Observation Protocol v1.0.
5. Authoritative W01 Wave Manifest / Wave 1 Implementation Package v1.0.

These five entries are recorded as `BLOCKED` in `protocol/scientific-artifacts.yaml`. The file under `battery/` and the W01 manifest skeleton are validation-failing state records, not scientific substitutes. No Frozen prompts, scoring anchors, protocol prose, or Wave decisions have been inferred.

## Scientific decisions unresolved

- Approved permanent Education model/service series and their relationship to MIBO Core lineages.
- W0 and W01 exact provider/model roster.
- Whether xAI belongs to the official longitudinal panel or only adapter coverage.
- Treatment of Perplexity in the primary CLOSED condition.
- Provider-specific maximum-output limits required by transport APIs.
- W0 replication count, timing window, and acceptance criteria.
- W01 replication count and complete stratification fields from the Wave package.
- NATIVE observation-surface definitions and whether API behavior is an admissible proxy.
- Ethics, terms-of-service, data-custody, operator, and approval records.

## Engineering blockers to actual execution

- Provider credentials are not configured in the repository (correctly).
- No live-verified model-lock file exists.
- No approved W0 or W01 execution schedule exists.

Consequently: `ENGINEERING_READY=true`, `SCIENTIFIC_PROTOCOL_COMPLETE=false`, `W0_READY=false`, and `W01_READY=false`. See `READINESS.md` for the exact reason attached to each false flag.

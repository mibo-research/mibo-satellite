# W0 four-provider evidence closeout, 2026-10-31

The versioned `sources-v1.json` contains only non-secret references and SHA-256
hashes. Raw observations remain outside Git in the persistent evidence root.
No provider output text, headers, or credentials are copied into this module.

Run the offline assessment from `eibo/` with the installed local package:

```powershell
python -m eibo.closeout --evidence-root C:\Users\offic\EIBO-W0-Evidence --sources waves/W0/closeout/sources-v1.json --output C:\Users\offic\EIBO-W0-Evidence\closeouts\W0-4P-20261031\assessment-v1.json
```

An existing output cannot be overwritten. To repeat an audit, choose a new output
filename. The assessor does not open credential stores, call providers, create model or
schedule locks, approve governance, write Q2/Q3 gates, or issue a Wave certificate.

| Series | Q1 | Original Q2 | Separate recovery | Evidence completeness |
|---|---|---|---|---|
| M01 | Passed | 7/7 passed | None | Complete |
| M02 | Passed | 7/7 passed | None | Complete |
| M03 | Passed | FAILED_CLOSED, 5/7 | E6-01 and E7-01 separately preserved | 7/7 including recovery |
| M05 | Passed | NATIVE 7/7 and non-official no-search 7/7 passed | None | Complete |

Google's original failed result and missing legacy Q2 gate are not rewritten.
`FOUR_PROVIDER_EVIDENCE_COMPLETE` is an offline machine assessment, not a silent
conversion to `Q2-M03=PASSED`, full-panel W0 readiness, official longitudinal
completion, or human acceptance. The new assessment preserves all original/raw
records, failed attempts, gaps, and recovery provenance. Technical failures are
not educational responses and are not scored. Refusals, blocks, poor/short answers,
and truncation remain outcomes, not technical failures or rerun reasons.

Human acceptance and prospective execution decisions are separate. See
`operations/prospective-four-provider/` for blocked preparation documents.
M04 remains NOT_RUN_COST_CONSTRAINT; original Core-35 and W01 remain unexecuted.
`W0_READY=false`, `W01_READY=false`, and `official_longitudinal_data=false` remain
in force. Consumer UI equivalence is neither assumed nor a blocker.

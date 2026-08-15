# W0 human-governance records

Only a human decision-maker may finalize these records. Automated agents must not populate a decision, identify themselves as a human, set `human_attestation: true`, or change a record to `status: FINAL`.

Copy each file from `templates/` to `records/`, then have the attributed human decision-maker complete it. Every final record requires a non-empty determination, named human and role, timezone-aware decision timestamp, rationale, and an evidence-reference list. The list may be empty only when no external reference applies.

`NOT_APPLICABLE` and `NOT_HUMAN_SUBJECTS` are determinations, not missing-review shortcuts. They require the same explicit human attribution, timestamp, rationale, and attestation as any other final determination.

The validation command reads records but never generates or approves them:

```text
miboe qualify preflight
```

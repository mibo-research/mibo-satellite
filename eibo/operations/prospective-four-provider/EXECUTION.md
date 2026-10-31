# EIBO-W0-4P-R1 execution boundary

This separate engineering rehearsal is not legacy Q3/Core-35, not W01, and not
official longitudinal data. It cannot create or satisfy a legacy Q2/Q3 gate.
The original draft and governance templates remain unchanged snapshots; approval
is supported by the owner's separate immutable chat-decision receipts, not by an
agent changing a template to FINAL. Receipt hashes bind the accepted draft.

The implementation is `eibo.rehearsal4`. It verifies all eight human decisions,
the pinned qualified Q1/Q2 evidence (including separate Google recoveries), the
Frozen scientific files, the external prompt lock, and the exact M05 W0 profile.
An exclusive proposal directory prevents a second execution, including after a
crash or partial attempt. New permission is required to recover an interrupted
run; there is no force/replace switch.

Production scheduling generates separate CLOSED (21) and NATIVE (7) schedules.
The new order-only mode is restricted to non-official k=1 rehearsals. Each domain
retains the production CLOSED block order; M05 is inserted at a seeded random
position, producing four-provider interleaving. All schedules are hashed and
locked before generation. Production `run_wave`, technical retry classification,
L0 archive, per-panel canonical JSONL, QC, and certificate functions are reused.
The injected first-party adapter is now also used by production preflight, so
M05 never passes through the legacy Sonar adapter in this flow.

The approved cap is 28 primary observations, two attempts per cell at most,
56 generation sends in total, six metadata GET sends, and no extra diagnostics.
The two-hour new-request deadline uses a monotonic clock. A received response is
preserved even if reception finishes after the deadline. Google generation-start
spacing is at least 65 seconds, provider Retry-After/RetryInfo delays are honored,
and retries have a two-minute baseline wait. No scientific outcome is retried.
Identity/configuration problems stop execution after raw preservation, without
model substitution. No-tool/no-history requests and provider-native optional
sampling/reasoning defaults are preserved.

The HTTP client disables proxy-environment routing, SDK retries, and redirects.
It checks actual serialized request bytes before transport. Authorization/API-key
and cookie headers are excluded from stored evidence. Credentials are loaded only
after the AC-only native guard passes, from the approved ignored `.env` and user
environment, in memory only. The guard is rechecked during waits and before sends.

Execution requires the persistent external evidence root, a hashed authorization
bundle referencing the eight receipts and tested implementation, and an active
native sleep-guard session. The operator/harness must always release and verify
the guard in finally, including preflight and metadata failures. Example entry:

```powershell
python -m eibo.rehearsal4 --root <module-root> --output-root <persistent-evidence-root> --authorization <authorization.json> --guard-state <active-guard-state.json>
```

Do not create the authorization bundle or execute this command by copying example
flags blindly. Existing model/schedule locks are not overwritten; this proposal
has its own runtime locks and model metadata. Certificates are explicitly scoped
to this non-official rehearsal, never official Wave or five-provider readiness.

Human decisions are not a guarantee of model availability, behavioral immutability,
account access, or provider internal processing region. Record the returned model,
usage, thinking metadata where exposed, blocks, refusals and truncation without
interpreting them as quality failures or changing Frozen scientific materials.

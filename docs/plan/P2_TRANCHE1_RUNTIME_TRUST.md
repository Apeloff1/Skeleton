# P2 Tranche 1 — Runtime Trust, Recovery and Functional Acceptance

Machine plan: machine/ai_p2_tranche1_plan.json
Validator: scripts/check_p2_tranche1_activated.py

## Status

**Activated.**

The seven P2-T0 implementation lanes are now landed-unpromoted. P2-NATIVE-01 is
bound to merged PR #2332 and its successful profile-gated acceleration check.
The 15 T1 volumes are transferred from the queue into five explicit owners
without asserting maturity, completion, or human verification signatures.

The canonical P2 partition is now:

- source: 314 volumes
- scheduled: 57 volumes
- queued: 257 volumes
- task owners: 12 total
- T1 workstreams: DATA, SEC, INFER, RECOVERY, FUNCTIONAL

## Functional-AI critical path

P2-T1-INFER owns VOL-007 and is responsible for provider-independent local model
execution, bounded batching/cancellation, model identity, and deterministic
usage accounting.

P2-T1-FUNCTIONAL owns VOL-097 and VOL-104 and is responsible for the canonical
VS-001 end-to-end fixture plus independent Functional-AI acceptance evidence.

The dependency chain is DATA/SEC -> INFER and DATA/SEC -> RECOVERY, then
DATA/SEC/INFER/RECOVERY -> FUNCTIONAL.

## Authority boundary

Activation is scheduling and ownership only. Completion checkboxes,
implementation signatures, and verification signatures remain false. A task may
move to landed-unpromoted only with exact-head executable evidence. P3 may not
claim P2 Functional-AI closure until the P2 terminal closure manifest validates.

# Operations Assurance Gap-fill — VOL-188..VOL-200

Status: **implementation candidate; VOL-195 intentionally blocked; no completion,
signature, scheduling, merge, deployment, or production authority**

Machine candidate:
`machine/ai_operations_assurance_gapfill_candidate.json`

VOL-195 blocker:
`machine/ai_vol195_local_development_blocker.json`

Exact-head validator:
`scripts/check_ai_operations_assurance_gapfill.py`

## Scope

This batch advances the queued reliability/deployment/developer/testing segment
without pretending that VOL-195 is closed.

Implementation/evidence work covers:

- VOL-188 Chaos Engineering
- VOL-189 Recovery Drills
- VOL-190 Release Qualification Matrix
- VOL-191 Canary Deployment
- VOL-192 Feature Flags
- VOL-193 Rollback Architecture
- VOL-194 Developer Experience
- VOL-196 Test Fixture Platform
- VOL-197 Simulation Mode
- VOL-198 Contract Fuzzing
- VOL-199 Property-Based Invariant Testing
- VOL-200 Formal Verification Candidates

VOL-195 Local Development remains explicitly excluded and blocked.

## New cross-volume assurance layer

`skeleton/ai/runtime/deferred/operations_assurance.py` composes, rather than
duplicates, the existing primitives.

It adds:

- a bounded fault catalog that requires every chaos fault to bind an abort
  signal and recovery runbook;
- deterministic recovery-drill scheduling and risk-ledger handoff;
- fail-closed release qualification -> merge-readiness evidence binding where
  missing/cancelled/skipped/non-success required gates block qualification;
- a canary promotion vector that jointly considers sample count, quality,
  remaining error budget, security, and cost;
- feature-flag schema, ownership, expiry, security-sensitive override, and
  combination constraints;
- explicit reversible-change classification and rollback proof binding,
  including external-effect reconciliation;
- contract-aware developer template receipts without mutation authority;
- an explicit simulation adapter switch whose receipts are permanently labeled
  simulated/non-production;
- P0 fuzz-target inventory plus reproducer-to-regression binding;
- a canonical named generator registry tied to invariant identity and bounded
  seed domains;
- exact-head formal candidate selection/conformance evidence with explicit
  executable test inventory.

Focused regression:
`skeleton/testing/test_operations_assurance_gapfill.py`

## VOL-195 remains fail-closed

The local bootstrap is already correctly designed to reject an unlocked
dependency graph. The repository root currently has no `uv.lock`. This batch
does **not** fabricate one.

VOL-195 remains `unverified` until a real canonical lock is generated with the
pyproject-pinned uv version, checked into the root, digest-bound into bootstrap
evidence, and exercised through a clean-machine locked bootstrap plus focused
tests on the exact head.

## Promotion boundary

All affected volumes remain in the queued continuation frontier. This PR does
not schedule them, set completion checkboxes, sign implementation or
verification, merge itself, deploy itself, or grant production authority.

A green exact-head workflow proves only that this implementation candidate and
its evidence agree on one exact revision.

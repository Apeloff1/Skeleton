# Autonomous Execution Reconciliation Model

## Purpose

Define how completed, failed, interrupted, and duplicated work units are reconciled across the automation control plane.

## Reconciliation principles

- Every execution has a stable identity.
- State transitions must be observable.
- Completion requires evidence, not only a successful process exit.
- Duplicate execution attempts converge on one canonical result.
- Failed work is classified before retry.

## States

- queued
- admitted
- executing
- awaiting-evidence
- completed
- retry-pending
- blocked
- abandoned

## Reconciliation loop

1. Read execution identity.
2. Compare claimed state with observed evidence.
3. Resolve conflicts deterministically.
4. Publish final state.
5. Return unresolved cases to controlled remediation.

## Integration points

- Supervisor admission layer
- Secretary planning layer
- Worker result protocol
- Merge readiness feedback loop

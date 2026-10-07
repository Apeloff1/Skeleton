# Autonomous Retry Ledger Design

## Purpose

Define a deterministic record of execution attempts so automated workers can recover safely without repeating unsafe or duplicate work.

## Ledger entry

Each execution attempt records:

- task identifier
- execution identity
- parent work item
- worker identity
- input fingerprint
- attempt number
- start and completion timestamps
- result state
- evidence references
- retry eligibility
- failure category

## Retry rules

Retries must be:

1. bounded
2. observable
3. idempotent where possible
4. blocked when evidence indicates corruption or stale ownership

## State transitions

QUEUED -> CLAIMED -> RUNNING -> VERIFIED -> COMPLETE

Failure paths:

RUNNING -> FAILED -> RETRY_PENDING -> CLAIMED

Terminal failures require human review or explicit policy override.

## Duplicate protection

A worker must compare execution identity and input fingerprint before creating a new attempt.

Existing successful evidence prevents duplicate execution.

## Integration targets

- supervisor control plane
- secretary scheduling layer
- worker execution runtime
- merge readiness reporting

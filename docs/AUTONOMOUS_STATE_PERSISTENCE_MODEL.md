# Autonomous State Persistence Model

## Purpose
Define the persistence boundary for autonomous repository operations.

## State Records

Each execution unit should maintain:

- execution identity
- requested operation
- ownership/custody state
- current lifecycle phase
- validation evidence
- retry history
- final disposition

## Lifecycle

`queued -> admitted -> executing -> validating -> reconciled -> completed`

Failure paths:

`executing -> failed -> classified -> retrying -> executing`

Permanent failures must preserve evidence and stop unsafe repetition.

## Requirements

- deterministic identifiers
- append-oriented history
- idempotent updates
- explicit ownership transitions
- reproducible recovery decisions

## Integration Targets

- supervisor orchestration
- secretary scheduling
- worker reporting
- merge readiness feedback

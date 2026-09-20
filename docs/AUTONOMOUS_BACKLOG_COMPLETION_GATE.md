# Autonomous Backlog Completion Gate

## Purpose

Define the final gate between backlog execution and completed work.

## Completion requirements

- Work item has stable identity.
- Execution evidence is recorded.
- Validation result is attached.
- Failures are classified.
- Recovery attempts are bounded.
- Duplicate completion is prevented.
- State transitions are deterministic.

## Flow

1. Intake
2. Normalize
3. Prioritize
4. Execute
5. Validate
6. Reconcile
7. Close or requeue

## Safety properties

The system should prefer explicit incomplete states over false completion. Missing evidence keeps work pending.

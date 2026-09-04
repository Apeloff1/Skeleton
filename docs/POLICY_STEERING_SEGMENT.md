# Policy Steering Segment

This segment sits above the corrective-control and diagnostics segments. Its role is not to perform verification or repair itself, but to let the operator steer when those systems are permissive, strict, or disabled.

## What this segment is

The segment currently introduces persistent operator policy state for:

- quality thresholds by surface
- repair enable/disable toggles by surface
- repair-class enable/disable toggles

## Core modules

- `skeleton/organism/policy_state.py`
- `skeleton/organism/policy_card.py`
- `skeleton/organism/policy_control_card.py`

## Current persisted state

The policy state lives under organism storage in `policy.json`.

It currently tracks three buckets:

1. `quality_thresholds`
2. `repair_enabled`
3. `repair_classes`

## Current surfaces

What is real now:

- policy state load/save
- threshold update helper
- repair enabled helper
- repair class helper
- policy card views

What is still pending:

- command-deck policy methods
- CLI steering commands
- HTTP steering endpoints
- wiring thresholds and toggles into repair execution decisions

## Design stance

The control segment should remain bounded and explicit. Steering must be readable from disk, testable, and reversible. Hidden policy mutation is not part of the design.

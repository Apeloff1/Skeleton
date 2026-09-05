# Policy Steering Segment

This segment sits above the corrective-control and diagnostics segments. Its role is not to perform verification or repair itself, but to let the operator steer when those systems are permissive, strict, or disabled.

## What this segment is

The segment introduces persistent operator policy state for:

- quality thresholds by surface
- repair enable/disable toggles by surface
- repair-class enable/disable toggles

And now includes full enforcement:

- All 5 verifiers read thresholds from policy.json dynamically
- All 4 repair scaffolds check repair_enabled and repair_classes before acting
- Policy gates are visible in every verification report

## Core modules

- `skeleton/organism/policy_state.py` — persistence
- `skeleton/organism/policy_enforcement.py` — enforcement bridge
- `skeleton/organism/policy_card.py` — operator views
- `skeleton/organism/policy_control_card.py` — aggregated control view

## Current surfaces

### CLI

- `python -m skeleton policy`
- `python -m skeleton threshold --surface forge`
- `python -m skeleton set-threshold forge 0.82`
- `python -m skeleton set-repair-enabled npc false`
- `python -m skeleton set-repair-class scene_stub false`
- `python -m skeleton gate-check forge 0.75` — test a score against threshold
- `python -m skeleton repair-gate --surface forge` — check if repair allowed

### HTTP

- `GET /api/v1/cortex/policy`
- `GET /api/v1/cortex/threshold?surface=`
- `POST /api/v1/cortex/threshold`
- `POST /api/v1/cortex/repair-enabled`
- `POST /api/v1/cortex/repair-class`

## Current persisted state

The policy state lives under organism storage in `policy.json`.

It tracks three buckets:

1. `quality_thresholds`
2. `repair_enabled`
3. `repair_classes`

## Current state

What is real now:

- policy state load/save
- threshold update helper
- repair enabled helper
- repair class helper
- policy card views
- command-deck policy methods
- CLI steering commands
- HTTP steering endpoints
- **policy enforcement wired into all verifiers and repair scaffolds**
- **gate_check and repair_gate for operator testing**

What is still pending:

- adaptive threshold adjustment based on historical quality pressure
- cross-surface policy inheritance
- policy versioning and rollback

## Design stance

The control segment should remain bounded and explicit. Steering must be readable from disk, testable, and reversible. Hidden policy mutation is not part of the design.

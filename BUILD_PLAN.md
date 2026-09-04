# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-09-04, anchored to the deep-cut ledger and the policy-steering start.

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs.

## Track N — Corrective-control segment — DONE

Shared quality contract, persistence, repair telemetry, and bounded repair parity across forge/plan/game-logic/NPC/dialogue are in place.

## Track O — Operator diagnostics command surface — DONE

Direct diagnostics cards, command-deck methods, HTTP endpoints, CLI commands, and filtering by surface/kind/limit are in place.

## Track P — Threshold and repair-policy steering — ACTIVE

### P1. Policy state persistence — DONE
- `organism/policy_state.py`

### P2. Policy cards — DONE
- `organism/policy_card.py`
- `organism/policy_control_card.py`

### P3. Command-deck steering methods — PENDING
### P4. CLI steering commands — PENDING
### P5. HTTP steering endpoints — PENDING
### P6. Enforcement in repair/verification paths — PENDING

## Integration seams for the next pass

- policy state → command deck / CLI / HTTP
- policy thresholds → verifier thresholds by surface
- repair toggles/classes → bounded repair execution gates
- rot_guard.assess → memory/compaction.ContextCompactor trigger
- handoff routing → agents/mesh.py

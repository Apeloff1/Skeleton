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
### P2. Policy cards — DONE
### P3. Command-deck steering methods — DONE
### P4. CLI steering commands — DONE
### P5. HTTP steering endpoints — DONE
### P6. Enforcement in repair/verification paths — DONE ✅
Enforcement is live in surface verifiers/repairs + CodeVerifier policy default.

## Integration seams for the next pass

- policy thresholds → verifier thresholds by surface
- repair toggles/classes → bounded repair execution gates
- policy cards → top-level operator surfaces
- rot_guard.assess → memory/compaction.ContextCompactor trigger
- handoff routing → agents/mesh.py

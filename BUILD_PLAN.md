# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-09-04, anchored to the deep-cut ledger and the diagnostics pass.

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs.

## Track N — Corrective-control segment — DONE

Shared quality contract, persistence, repair telemetry, and bounded repair parity across forge/plan/game-logic/NPC/dialogue are in place.

## Track O — Operator diagnostics command surface — DONE

### O1. Direct diagnostics cards — DONE
### O2. Command-deck diagnostics methods — DONE
### O3. HTTP diagnostics endpoints — DONE
### O4. CLI diagnostics commands — DONE
### O5. Filtering by surface / kind / limit — DONE

## Track P — Threshold and repair-policy steering — NEXT

### P1. Policy state persistence — pending
### P2. Threshold query/update cards — pending
### P3. CLI steering commands — pending
### P4. HTTP steering endpoints — pending

## Integration seams for the next pass

- diagnostics filtering parity is now closed
- threshold and repair-policy steering → next operator control segment
- rot_guard.assess → memory/compaction.ContextCompactor trigger
- handoff routing → agents/mesh.py

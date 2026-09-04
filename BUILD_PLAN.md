# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-09-04, anchored to the deep-cut ledger and the diagnostics pass.

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs.

## Track L — Social-media SOTA sweeps — DONE

Waves 1–4 plus routed gate and bound-field lineage shipped.

## Track M — Bi-directional frontier catch-up — DONE

Direction A and B landed previously and remain intact.

## Track N — Corrective-control segment — DONE

### N1. Shared quality contract — DONE
### N2. Surface verifiers — DONE
### N3. Quality persistence — DONE
### N4. Operator repair surface — DONE
### N5. Bounded repair paths — DONE
- forge repair: active
- plan repair: active
- game-logic repair: active
- NPC repair: active
- dialogue repair: active

### N6. Repair telemetry rollups — DONE
- recent activity
- recurring failure issue
- recurring repair target
- per-surface repair counts

## Track O — Operator diagnostics command surface — ACTIVE

### O1. Direct diagnostics cards — DONE
- `organism/failure_card.py`
- `organism/activity_card.py`
- `organism/recurring_card.py`

### O2. Command-deck diagnostics methods — DONE
- `failures()`
- `repairs()`
- `activity()`
- `recurring()`

### O3. HTTP diagnostics endpoints — DONE
- `/cortex/failures`
- `/cortex/repairs`
- `/cortex/activity`
- `/cortex/recurring`

### O4. CLI diagnostics commands — DONE
- `python -m skeleton failures`
- `python -m skeleton repairs`
- `python -m skeleton activity`
- `python -m skeleton recurring`

### O5. Filtering and policy controls — PENDING
- filter by surface
- filter by limit and type
- threshold/policy steering segment

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY file moves, godot binary, shim removal).

## Integration seams for the next pass

- diagnostics filtering → command deck / CLI / HTTP parity
- threshold and repair-policy steering → new operator control segment
- rot_guard.assess → memory/compaction.ContextCompactor trigger
- handoff routing → agents/mesh.py

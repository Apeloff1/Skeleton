# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-09-04, anchored to the deep-cut ledger and the corrective-control pass.

## Tracks — all DONE

A · B · C · D · F · G · H · H5 · I · J · K · Docs.

## Track L — Social-media SOTA sweeps — DONE

Waves 1–4 plus routed gate and bound-field lineage shipped.

## Track M — Bi-directional frontier catch-up — DONE

Direction A and B landed previously and remain intact.

## Track N — Corrective-control segment — ACTIVE

### N1. Shared quality contract — DONE
- `intelligence/quality.py`
- shared issue / signal / report vocabulary across plan, forge, and pipelines

### N2. Surface verifiers — DONE
- forge verifier
- plan verifier
- pipeline verifier
- NPC verifier
- dialogue verifier

### N3. Quality persistence — DONE
- `organism/quality_state.py`
- quality and repair history persisted separately under organism storage

### N4. Operator repair surface — DONE
- `organism/repair_card.py`
- reused by product / nervous / doctor / satellites

### N5. Bounded repair paths — PARTIAL
- forge repair: active
- plan repair: active
- NPC repair: active
- dialogue repair: active
- game-logic repair: pending

### N6. Repair telemetry rollups — DONE
- recent activity
- recurring failure issue
- recurring repair target
- per-surface repair counts

## Track E — Cleanup pass (deferred, requires local git ops)

E1–E4 unchanged (root sprawl, SEVEN_BY file moves, godot binary, shim removal).

## Integration seams for the next pass

- `rot_guard.assess` → `memory/compaction.ContextCompactor` trigger.
- `handoff.HandoffRegistry` → `agents/mesh.py` routing.
- game-logic repair path → full corrective-control parity.
- repair-card / quality-state queries → dedicated operator commands.

## Active architectural note

The corrective-control segment is now a first-class app segment. It surrounds
existing generation surfaces rather than replacing them: verify → persist →
target → repair once → re-verify → surface.

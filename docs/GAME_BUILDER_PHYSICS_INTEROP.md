# Cross-family physics interoperability — platformer, racing and persistent worlds

**Authored:** 2026-10-12 (Europe/Oslo). **Depends on:** Game Builder #3642 → Physics #3661/#3662/#3664/#3665 → Native #3666 → Signed fixtures #3670.

## Delivered original-game mechanics

This milestone introduces an **opt-in executable physical encounter rehearsal**. It is not an invisible rewrite of the existing platformer, racing or sandbox authorities. Their original source game session is independently replayed before the bridge may create any physical scene. The bridge derives authored static obstacles and witness identifiers directly from a signed original game scene, then constructs a second validated original Physics scene, applies a bounded transcript of actual physics commands and independently verifies every resulting event and final state.

### Platformer
Source hazards are projected proportionally from the original level width to bounded collision fixtures. Physical play rehearses actual swept hazard impact, with exact source spike IDs recorded in the witness map. Collectible progression, HP and game victory remain controlled by the original platformer runtime, not the rehearsal.

### Racing
The source-authored obstacle position is projected onto the physics test world. A replayed car in the original centerline receives a solid source fixture, whereas a verified side-lane maneuver produces an explicitly passable layer. The physics test independently confirms an actual impact or avoidance, without minting podium points or altering engine health.

### Persistent sandbox world
Actual authored ridges and constructed buildings become physical obstacles; roads and bridges retain pass-through semantics. Up to eight source records are projected from the authoritative 64-tile layout. The physical test never edits terrain, population, building budgets or persistent chunk history.

## Security and reproducibility

- All three source game families use canonical advanced-session verification and a signed source-scene digest before any physical rehearsal.
- Physical settings and action vocabulary are finite, typed, original and sealed by the bridge. The source can request at most 32 accepted commands; no arbitrary scripts, HTML, live file writes or unreviewed client states are executed.
- A signed result contains source session/head/scene digests, physical scene, original witness IDs, physical session, actual swept/static fixture-event count and a SHA-256 result digest.
- `verify_physics_encounter` reconstructs both simulations independently and compares the entire result, preventing forged physics hits, lane switches, evidence fields or source changes.
- The new authenticated, same-origin local Studio API can display physical witnesses, signed proof and independently detected impacts. It does not claim native hardware execution, model promotion, native production parity or publisher approval.

## Testing

`tests/test_game_builder_advanced_physics_interop.py` covers canonical original source replay, platformer spike collisions, real racing side-lane avoidance, source-bound sandbox terrain, immutable source custody, tamper rejection, invalid actions, mismatched settings and absence of automatic win/release effects. These tests run in the existing exact-head Windows/Ubuntu Advanced System Engines workflow.

## Timestamped change history

- **2026-10-12:** Proven native fixture collision (improved: independently executing Godot source respects reviewed solid obstacles and collision masks).
- **2026-10-12:** Source-driven platformer bridge (improved: hazards can be physically rehearsed without losing source provenance).
- **2026-10-12:** Racing physical obstacle lanes (improved: replayed control choices change physical collision outcomes).
- **2026-10-12:** World building and terrain bridge (improved: persistent original structures supply actual simulation obstacles).
- **2026-10-12:** Signed dual-engine receipts and same-origin Studio interaction (improved: physical tests produce audit-grade evidence without mutating original games).

**Next milestone:** after cross-platform integration is verified, optionally connect these collision outcomes to full authored game runtime progression through explicit authority and policy contracts. Extend the independently executed Godot reference to rotated fixtures and dynamic pairs without weakening proven source parity.
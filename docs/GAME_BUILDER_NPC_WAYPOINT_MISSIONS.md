# Advanced Original Game Studio — Authenticated NPC Waypoint Missions

Date: 2026-10-12 (Europe/Oslo). Status: draft until exact-head CI.
Dependency stack: PR #3705 dynamic NPC route execution, #3702 historical
spatial source replay, #3700 spatial residency, #3695 128-person original
physical NPC world.

## What actually executes

The original streamed-world reference simulator now has an explicit
multi-stage mission executor, not merely a single route demonstration.
The operator supplies 1–12 typed source-backed waypoints. The mission
reuses the actual dynamic route planner for every objective, each time
starting from the previous leg's fully reconstructed physical world.

Waypoint goals support: approach a real site/citizen/tile, material site
harvest, material repair, witness conversation, paid social support, and
source-eligible restoration claim. No arbitrary narrative labels, direct
coordinate edits or fake quest-completion switches are accepted.

A representative original nine-leg mission:

1. Physically approach the original authored site; harvest real finite stock.
   Record actual physical witnesses in the event journal.
2. Physically reach the firsthand witness; speak and bind a real source
   statement to that exact event.
3. Pay real finite influence and material to support the same citizen.
4–8. Carry out five material site repairs, each paid from existing
   original inventory and using the live source simulation.
9. Claim the restoration only after a true witnessed statement, paid
   support and every required material repair.

The player and NPCs continue moving throughout the expedition. Every step
honors embodied collision, actual obstacle geometry, per-tick detailed NPC
scheduling, finite stamina, memory/patience and real line-of-sight. A leg
cannot fabricate a resource, teleport a citizen, or skip a dialogue/action
precondition.

## Replay custody and conservation

Before executing any mission, the complete original source game is
independently replay-verified. Each waypoint invokes the existing dynamic
route planner, executes the physical actions, and builds a complete
independently replayed source-world result. The next leg starts **only**
from that exact canonical result.

Every leg binds source and result action-chain heads, exact start/end
player positions and ticks, generated player action list, physical
movement/frame digests, accumulated real source facts, genuine dialogue,
paid social choices, material and stamina deltas, and actually earned
original quest milestones.

The full mission report preserves starting source scene/settings/seed
identity and the global generated action trace, real final world digest,
final source chain head and last NPC physical update ledger. Imported
mission receipts are independently reconstructed and compared, rejecting
altered resources, fake timestamps, false action heads, free rewards,
forged actor interactions or invented quest completion.

No hardware/Godot execution benchmark or AI-weight improvement is
claimed. The code is original CPU-reference gameplay and cannot mutate
the user's project without an explicit separate authorization.

## Delivered user interfaces

Runtime:
skeleton/ai/game_builder/advanced_npc_waypoint_mission.py

Tests:
tests/test_game_builder_npc_waypoint_mission.py

Offline CLI:
- plan-original-npc-mission
- verify-original-npc-mission

Authenticated local Studio routes:
- POST /api/plan-original-npc-mission
- POST /api/verify-original-npc-mission

Dialogue Studio visual controls:
- NPC Waypoint Mission, an editable set of exact source waypoint goals,
  operator-run authenticated source simulation, independent re-verification,
  exact per-leg physical movement, source facts, paid social decisions,
  conservation deltas and earned original quest progress.

Exact-head CI:
.github/workflows/game-builder-npc-waypoint-missions.yml
- Ubuntu 24.04 and Windows Server 2022, pinned source checkout,
  Python 3.11 compilation, complete adversarial mission tests and eight
  original cross-seed/chunk gameplay sequences on each platform.

## Timestamped change ledger

2026-10-12 — Added source-authenticated chained original NPC route legs
(turns verified one-stop pathfinding into real playable multi-stop missions).

2026-10-12 — Added original eyewitness, dialogue and finite material
quest progression (requires actual player actions, not narrative flags).

2026-10-12 — Added source-head linkage and resource/event deltas per leg
(all genuine results can be scrutinized and independently reconstructed).

2026-10-12 — Added adversarial denial of skipped quests, forged receipts
and impossible physical routes (prevents false source completion).

2026-10-12 — Added offline CLI, authenticated Studio mission controls
and exact-head Ubuntu/Windows workflow (operator-accessible game feature).

## Remaining milestones

Native Godot 4 source-parity route execution, multi-actor shared mission
scheduling, richer conditional objective trees, failure/retry policy
editor, performance benchmarks on consumer hardware and production-grade
persisted game saves remain distinct work. This milestone does not imply
completion of any of those.

All stacked PRs remain draft, pending exact-head CI and dependency review.
No automatic merge to main, model-weight promotion or uncontrolled
external operation.

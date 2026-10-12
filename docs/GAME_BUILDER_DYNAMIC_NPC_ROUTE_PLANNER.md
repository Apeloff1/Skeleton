# Advanced Original Game Studio — Dynamic NPC-Aware Route Planner

Date: 2026-10-12 (Europe/Oslo). Status: draft awaiting exact-head CI.
Parent milestones: #3702 historical source-verified spatial lens, #3700
original chunk-residency index, #3695 128-physical-body simulation.

## Executable capability

This milestone implements a real action-executing navigation planner
for the source-authored original streamed NPC world. It supports 21x21
and 35x35 worlds with up to 128 physically embodied citizens and actual
NPC schedules. Every generated movement executes the existing game rules.

Operator objectives:

- Reviewed source site: physically reach an original material site and
  optionally perform real harvest, repair or claim actions. Preconditions,
  finite stock, quest progression and source witnesses are checked by
  the unchanged original game.
- Original NPC: approach a moving physical citizen, then optionally
  speak, observe or support if actual active-detail, distance and
  influence constraints allow. The target NPC is never teleported.
- Exact tile: navigate to a bounded source tile, rejecting obstacles,
  collisions and nonexistent map coordinates.

## Receding-horizon physical pathfinding

At each actual source turn, the planner reads the real player position,
authoring obstacles and embodied resident positions. Bounded BFS computes
the shortest currently reachable path on walkable tiles. Exactly one
adjacent physical movement is executed with the original gameplay
engine. If insufficient stamina is available, a real paid/recoverable
rest action executes instead of free motion.

The actual NPC schedule advances, one true legal tile per detailed actor,
and the planner recalculates paths from the updated physical positions.
Temporarily blocked routes can wait up to five bounded turns. Permanent
obstruction and exhausted budgets fail closed instead of minting progress.

At a reachable physical endpoint, the requested optional original
interaction executes once using unchanged material, NPC and quest rules.
An unearned restoration, impossible repair or unsupported source
NPC statement is rejected by the actual game.

The planner then independently reexecutes the **entire original source
game** from original reviewed scenes, seed, typed settings and complete
player action list. Every authoritative NPC position, resource, clock,
event, detailed/deferred work receipt and chained proof head must equal
the planner's internal source-mechanics execution exactly.

This is NOT globally time-optimal movement under future unknown NPC
decisions. BFS finds a shortest path only for the currently observed
world occupancy and replans after every real simulation turn.

## Provenance and interfaces

Plans include reviewed game source digest/head, exact typed objective,
bounded step capacity, each real action and player from/to cell/chunk,
true witness/gameplay effect labels, source frame digest, per-step
detailed NPC work count, finite resources and independently reconstructed
result world digest.

Runtime: skeleton/ai/game_builder/advanced_npc_dynamic_route_planner.py
Tests: tests/test_game_builder_npc_dynamic_route_planner.py

Offline CLI commands:
plan-original-npc-route
verify-original-npc-route

Authenticated read-only Studio routes:
/api/plan-original-npc-route
/api/verify-original-npc-route

Dialogue Studio panel: Dynamic NPC Route Planner, with goal selection,
exact source identity/tile, optional actual source action, physical
route-replanning and independent source evidence.

Exact-head Windows/Ubuntu CI:
.github/workflows/game-builder-npc-dynamic-route-planner.yml

## Timestamped improvements

2026-10-12 — Added physically embodied dynamic route search
(upgrades static source occupancy inspection to actual playable actions).

2026-10-12 — Added moving-NPC collision and one-step replanning
(prevents clipping, phasing or teleporting through actual NPC bodies).

2026-10-12 — Added finite stamina recovery and real source interactions
(prevents free quest achievements or fictional resource creation).

2026-10-12 — Added complete game replay equivalence and forged-proof
rejection (authoritative source trace remains the sole truth).

2026-10-12 — Added CLI, authenticated Studio and seeded cross-OS tests
(makes the actual routing capability reviewable and operator accessible).

## Open scope

No globally time-optimal paths, no guaranteed solution for physically
impossible objectives, no native streamed Godot execution, no claimed
consumer hardware benchmark, no source file writes and no model-weight
promotion. Further native physics, multi-waypoint missions and persisted
route policies remain distinct milestones.

All PRs in this dependency stack remain draft and unmerged.

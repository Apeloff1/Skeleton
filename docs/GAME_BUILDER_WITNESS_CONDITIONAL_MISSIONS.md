# Game Studio — Witness-Conditional NPC Missions

**Date:** 2026-10-12 (Europe/Oslo). **Status:** draft pending exact-head CI.
**Depends on:** draft #3709 adversarial NPC mission mirror, #3707 original
nine-leg physical missions, #3705 dynamic navigation and #3695 NPC world.

## Executable implementation

The Game Studio now supports bounded original NPC missions with source-backed
if / and / or / not guards that use facts **actually acquired by the player**,
rather than the private agendas of remote NPCs or imagined events.

Programs contain one to twelve nodes. Each node is a real physical waypoint
or a conditional decision with a guarded then-list and otherwise-list.
Selected goals run through the existing original NPC waypoint and dynamic
route engine. Unselected goals are recorded as unexecuted alternatives,
never mistaken for actual game actions or model training.

A guarded decision has at most 31 Boolean nodes, recursion depth five and
at most six children under an and/or operator. Guard predicates are
whitelisted and require exact typed arguments. Supported player facts:

- own_harvest_at_site: original player-performed harvest event and source site
- firsthand_testimony: direct actual witness statement heard from an
  exact original physically embodied NPC, with real source event ID
- paid_support: material and influence actually paid to a directly
  heard witness, not merely an intent to offer aid
- site_quest_resolved: earned authored quest resolution, never a guessed ending
- supplies_at_least, stamina_at_least, influence_at_least: finite
  player-controlled inventory against a bounded integer threshold
- turn_at_most and earned_quests_at_least: actual elapsed original
  world time and earned material quest milestones

AND, OR and NOT can combine these conditions. Unknown language operators,
private NPC knowledge, arbitrary code, booleans submitted as numeric
quantities, invalid source IDs, unbounded expressions, false event claims
and infeasible missions are rejected.

## Authentic replay and recorded decisions

Every selected waypoint executes with genuine game rules for moving NPCs,
player traversal, finite stamina, source witness constraints, scarce
material and paid aid. The record preserves the world source head before
a decision, the full evaluated player-evidence tree, the selected branch,
unexecuted alternatives, each actual game action and its source receipt,
and the complete final game-world digest.

The full game is independently reconstructed from original reviewed
scenes, settings, seed and player commands. The exported record verifier
reexecutes all conditional decisions, including choices not taken,
and rejects modified provenance, witness identities, paid supplies,
resource thresholds, quest outcomes, source receipts and unsupported
weight-promotion claims.

SHA-based content integrity does not confer author or operator identity.

## Product and testing surfaces

Runtime: skeleton/ai/game_builder/advanced_npc_conditional_mission.py
Tests: tests/test_game_builder_npc_conditional_mission.py
CLI: run-original-conditional-npc-mission,
verify-original-conditional-npc-mission.
Authenticated Studio:
  /api/run-original-conditional-npc-mission
  /api/verify-original-conditional-npc-mission

The Dialogue Studio includes a Witness-Conditional Missions editor with
editable original physical objectives, actual first-hand evidence and
independently verified outcomes. The dedicated exact-head CI workflow
game-builder-npc-conditional-missions.yml runs on Ubuntu and Windows,
testing earned restoration, false testimonies, illegal branches, source
forgery, typed guard bounds and up-to-128 original physical actors.

## Dated improvement ledger

2026-10-12 — Implemented actual evidence-gated original mission programs
(upgrades fixed linear waypoint routes to player-observed conditional quests).

2026-10-12 — Added typed bounded AND/OR/NOT expression trees
(extends authored quest logic without allowing arbitrary scripts).

2026-10-12 — Bound mission decisions to actual first-hand testimony,
player harvesting, paid support, own inventory and earned restoration
(prevents hidden offscreen assumptions from controlling gameplay).

2026-10-12 — Added individual source/branch receipts and full
independent mission reexecution (forgery and fictional completion defense).

2026-10-12 — Added Studio, CLI and exact-head cross-platform test
coverage (operator-accessible and auditable authored game logic).

## Remaining scope

This is a deterministic source-reference gameplay and scripting system,
not a trained LLM planner, all-faction narrative world, guaranteed route
solution, native Godot release or hardware benchmark. No game project
files or AI model weights are automatically modified. This and its
unmerged ancestor PRs remain drafts until safe integration and
source-head CI pass.

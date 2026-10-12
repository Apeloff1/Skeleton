# Advanced Original Game Studio — Adversarial NPC Mission Mirror

Date: 2026-10-12 (Europe/Oslo). Status: draft until exact-head CI.
Stacked after #3707 multi-stop material NPC missions, #3705 physical
dynamic route planner, #3702 historical actor states, #3700 real chunk
residency and #3695 detailed budgeted 128-person world.

## Real capability

The original waypoint mission engine can execute a fully sourced,
nine-step witnessed restoration: harvest original finite material,
interview a genuinely present eyewitness, pay to support them, carry
out five actual finite repairs at the site, and explicitly claim a
real quest milestone. Completing this is a gameplay consequence,
not a guessed game design annotation.

This milestone permits one to eight different **bounded authored
itineraries** to be run against exactly the same original reviewed
game state. A candidate can propose the full material restoration,
a short legitimate harvest, a resource-limited detour, or a shortcut
that should be rejected. The system does not automatically treat
any submitted plan as working.

Every candidate is run by the existing original waypoint mission
engine, which calls real player/NPC navigation, stamina and active LOD
schedules, proximity checks, source-witness constraints and material
quest actions. Accepted plans must also independently replay each
mission receipt in full. Rejected or infeasible plans record a
bounded failure reason with no fabricated actor state, rewards or
claims of successful completion.

## Factual, bounded mission comparisons

Actual reviewed consequences include:
- Number of truly completed itinerary legs and earned quest milestones.
- Number of real physical events and firsthand conversations.
- Actual paid support actions and remaining finite supplies.
- Total executed actions, route replan attempts and blocked waits.
- Current remaining stamina, world time and player tile.
- Physical population and genuinely executed/detail-deferred NPC turns.
- Complete final original game digest, action head and separate source
  custody digest for each leg.

These are factual results **only of the original replayed game**.
No result is written into the original project source or AI weights.

The mirror computes a bounded Pareto frontier over **real accepted
plans only**. Its criteria favor higher earned quest counts, real
physical events and remaining finite supplies, with fewer player
actions and blocked waits. It also exposes a documented lexicographic
review order prioritizing earned quests followed by events, action
cost and supplies, with stable candidate IDs as a deterministic
tie-breaker.

A Pareto frontier over up to eight submitted alternatives is **not**
proof of a globally optimal NPC route, a best videogame, superior
model skill or performance against other game engines. No route
outside the supplied candidate set is claimed to have been explored.

An impossible source action remains explicitly
"rejected_by_real_gameplay" with an empty outcome. Such a candidate
never appears in the accepted review order or Pareto frontier.

## Trust and integrity

Before analysis, the source game itself is independently
reconstructed from reviewed game scenes/settings, seed, original
player actions, exact NPC positions and resource/time/state receipts.
The candidate list has strict unique lowercase safe IDs, one to
twelve typed physical waypoints per candidate and bounded per-leg
turn limits. Results and source identities are hashed under the
existing original game canonical JSON primitive.

Importing or verifying any report **reexecutes the entire exact
candidate review**, including all accepted and rejected branches,
their physical transition sequences and actual quest rewards.
Altered witness evidence, claimed victories, resource balances,
historical heads, outcome ordering, candidate source, rankings,
hardware/model-promotion claims or report hashes fail closed.

The checksums are content integrity, not private-key signatures.

## Product integration

- Runtime:
  skeleton/ai/game_builder/advanced_npc_mission_mirror.py
- Actual route/quest engine:
  skeleton/ai/game_builder/advanced_npc_waypoint_mission.py
- Adversarial/CLI/Studio regression:
  tests/test_game_builder_npc_mission_mirror.py
- Offline commands:
  analyze-original-npc-missions
  verify-original-npc-mission-mirror
- Token-authenticated, read-only Studio endpoints:
  /api/analyze-original-npc-missions
  /api/verify-original-npc-mission-mirror
- Visual Dialogue Studio:
  NPC Mission Mirror, an editable up-to-eight itinerary set,
  actual success/rejection outcomes and source-evidence metrics,
  with independent replay on both preview and verify calls.
- Exact-head Linux/Windows validation:
  .github/workflows/game-builder-npc-mission-mirror.yml

## Dated October 12, 2026 improvement ledger

2026-10-12 — Added source-authenticated multi-itinerary execution
(upgrades one prepared mission to several objectively testable
alternate original quests).

2026-10-12 — Added actual failure custody and legal-gameplay
precondition checks (eliminates invented victories for free claims
or non-witnessed support actions).

2026-10-12 — Added material- and quest-aware comparative metrics,
bounded Pareto review and deterministic ordering (exposes actual
costs/consequences without claiming global optimality).

2026-10-12 — Added strict candidate schema, source-linked leg receipts
and independent full reexecution of every review (prevents state,
ranking, evidence or model-weight forgery).

2026-10-12 — Added exact-head cross-platform adversarial tests,
offline CLI and authenticated Studio controls (reviewable original
gameplay rather than an opaque optimizer).

## Open milestone backlog

- Additional deliberately authored quest alternatives and real
  choices involving competing NPC interests and scarce rewards.
- Better physical transit planning with proven finite occupancy
  and contingent path choices across game genres.
- Side-by-side narrative evidence review in a visual game map.
- Native Godot 4 original multi-engine quest execution and
  measured CPU/GPU benchmarks on supported devices.
- Operator-gated transfer of genuinely beneficial knowledge through
  the mother-dragon shadow-weight verification system; **not**
  directly into permanent LLM weights.

No automatic merge to main, source mutation or hardware
certification. The PR remains draft until its exact-head
independent game tests and stacked integration gates pass.

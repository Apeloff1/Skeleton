# expedition: Self-consistent natural habitat and observed ecological changes — vertical routes

**Volume 838 of 1,000** · Game production: Travel parties, interactive NPCs and native authored RPG quests · Owned compiler: `skeleton/forge/game_frontier_studio_final_production.py` · PR #4200.

## Real-world game-production result

This book describes **50 underlying concrete game-source archetypes × 9 production treatments × 10 gameplay systems** within domain `expedition`, director `ecology_cycles`, and final finishing pass `vertical_routes`. The output is a real immutable edit to the canonical `StudioProject` source: additional palette-indexed map tiles and a typed sensor-driven RPGEventPage, with new cast/quest modifications when those records were created in the same transaction. It is a composed authoring workflow, **not** a new standalone game engine, asset model, or a complete shipped game.

**Domain:** Travel parties, interactive NPCs and native authored RPG quests. **Director:** Self-consistent natural habitat and observed ecological changes. **Finishing behavior:** Build accessible skyward crossings and adjust newly placed actors. **Observed sensor inputs:** updraft_mps, sky_island_height_m. **Typed gameplay action proposal:** `apply_gameplay_effect`. The proposal does not mutate native game state until authorized by its runtime.

## Source archetype inventory (50 executable producers)

1. `encounter_village_crowd`
2. `encounter_market_vendors`
3. `encounter_tavern_guests`
4. `encounter_festival_parade`
5. `encounter_harbor_workers`
6. `encounter_farm_hands`
7. `encounter_caravan_merchants`
8. `encounter_city_patrol`
9. `encounter_castle_guards`
10. `encounter_royal_court`
11. `encounter_wolf_pack`
12. `encounter_deer_herd`
13. `encounter_bird_flock`
14. `encounter_fish_school`
15. `encounter_insect_swarm`
16. `encounter_horse_stampede`
17. `encounter_bear_den`
18. `encounter_predator_ring`
19. `encounter_migratory_line`
20. `encounter_turtle_nesting`
21. `encounter_squad_wedge`
22. `encounter_siege_lines`
23. `encounter_archer_wall`
24. `encounter_shield_circle`
25. `encounter_cavalry_charge`
26. `encounter_ambush_arcs`
27. `encounter_flanking_pincer`
28. `encounter_rear_guard`
29. `encounter_scout_net`
30. `encounter_boss_minions`
31. `encounter_sky_pirates`
32. `encounter_airship_crew`
33. `encounter_cloud_drakes`
34. `encounter_floating_island_settlers`
35. `encounter_wind_surfers`
36. `encounter_tower_watchers`
37. `encounter_balloon_riders`
38. `encounter_glider_convoy`
39. `encounter_sky_fishermen`
40. `encounter_aurora_procession`
41. `encounter_dungeon_slimes`
42. `encounter_cave_bats`
43. `encounter_crypt_guardians`
44. `encounter_labyrinth_wardens`
45. `encounter_treasure_mimics`
46. `encounter_portal_sentinels`
47. `encounter_ruin_explorers`
48. `encounter_mine_workers`
49. `encounter_fungal_foragers`
50. `encounter_underground_merchants`

## Combinatorial authoring space and versioning

Production treatment axes: `waterways`, `highlands`, `fortified`, `nightfall`, `festival`, `circuit`, `secrets`, `skyreach`, `wilderness`. Gameplay systems: `wayfinding`, `seasons`, `destructibles`, `weather`, `combat`, `commerce`, `stealth`, `verticality`, `migration`, `story_convergence`. This volume covers 4,500 exact source-changing commands for one domain/director/finish combination. There are 900 such volumes, meaning **4.5 million directed finishing combinations** in the new tier, in addition to the preceding 500,000 operations. Game-source IDs, revisions and code-level authorizations never depend on the numeric scale of the catalog.

**Representative exact command:** `complete_expedition_tower_watchers__skyreach___verticality____ecology_cycles_____vertical_routes`.

| Example | Actual enumerated game operation |
|---:|---|
| 1 | `complete_expedition_village_crowd__skyreach___verticality____ecology_cycles_____vertical_routes` |
| 2 | `complete_expedition_market_vendors__wilderness___migration____ecology_cycles_____vertical_routes` |
| 3 | `complete_expedition_tavern_guests__waterways___story_convergence____ecology_cycles_____vertical_routes` |
| 4 | `complete_expedition_festival_parade__highlands___wayfinding____ecology_cycles_____vertical_routes` |
| 5 | `complete_expedition_harbor_workers__fortified___seasons____ecology_cycles_____vertical_routes` |

## Execution and native compilation path

1. Resolve authenticated project identity, source SHA, editor version and actual palette.
2. Select one of the fifty owned source archetypes above, a real tile layer and a finite seeded authoring region.
3. Execute a canonical source recipe and its spatial/quest/encounter treatment through `execute_authoring`.
4. Apply the selected gameplay system to author source tiles and a real observed-sensor event page.
5. Apply the director's spatial/narrative layout and a further independently evaluated page.
6. Complete this book's finishing stage: build accessible skyward crossings and adjust newly placed actors.
7. Append the typed event action `apply_gameplay_effect` gated on real game observations (updraft_mps, sky_island_height_m). Never fabricate readings or execute an unauthorized mutation.
8. Modify only newly authored actors/quest stages; preserve all existing cast identities, story canon and version receipts.
9. Write a new deterministic map layer candidate and compute its before/after SHA-256. A failed stage discards the whole immutable transaction.
10. Preview the candidate against current authorized source, commit via the original host compare-and-set, and export the native Godot expedition files.
11. In Godot, verify changed geometry, walkability, actor placements, quest reachability and actual observed event evaluation.
12. Perform a real target-device playthrough before promoting the candidate to release status.

## Measurable functional acceptance

- The source recipe, director and finishing identity must resolve to an exact registered operation; unknown command strings fail closed.
- The canonical map cells must actually change, and the game-source digest must reflect those changes.
- The finishing page must have **two distinct supported sensor predicates**, correct comparator thresholds and the registered `apply_gameplay_effect` action.
- Same original source/seed/instance yields deterministic identical output; a second unique instance authors additional content without overwriting existing canon.
- Invalid palette, non-finite input, out-of-bounds rectangles, duplicate IDs and untrusted nested commands reject atomically.
- Newly created NPC dialogue targets, where applicable, retain stable actor indices. New quest alternatives, where applicable, are reachable from their authored entry stage.
- Project JSON roundtrip preserves all typed source records and original game metadata.
- Server discovery returns no more than 64 contracts per page; no eagerly materialized four-million-entry list is acceptable.
- Native Godot tile geometry, expedition routes and RPG page proposals must be inspected; **collision, sound, economy and combat results require separate runtime evidence**.
- All content must be original or rights-cleared; generated narrative branches may not silently overwrite user-authored lore.

## Integration, repair and release notes

This document belongs to the original Forge Studio/Jeeves application rather than an auxiliary sample game. The renderer, user interface, transaction record, world compiler and game-learning workspace remain single-authority systems. If native testing finds blocked paths, broken prefab references, incorrect sensors or timeline contradictions, repair the source-owning producer and rerun exact-head CI; never lower requirements simply to reach a numeric target. **Implementation status is separate from E2E release certification.**

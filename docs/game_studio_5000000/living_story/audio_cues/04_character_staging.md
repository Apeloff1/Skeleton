# Volume 984 of 1,000 — Living Story / audio_cues / character_staging

**Scope:** original-game longform production using exact sources, a real game script/quest compiler and the canonical Forge Studio project. **Published status:** source implementation committed; runtime qualification still pending.

## Purpose and actual game production

Use director **audio_cues** with finishing pass **character_staging** to produce a new game chapter that preserves player choices, adds reachable native quest consequences and links observed environmental actions to authored story scenes. A valid production executes the existing 500,000-tier directed workflow, paints additional deterministic tile geometry, and appends another bounded two-sensor `RPGEventPage`. Existing character and quest identities are never edited; transformations apply only to records created by this current transaction.

Example exact command: `complete_living_story_saltwind_market__nightfall___weather____audio_cues_____character_staging`.

## Fifty existing native quest source archetypes

| # | Canonical source | Actually authored output |
|---:|---|---|
| 1 | `quest_lighthouse_blackout` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 2 | `quest_sky_island_rescue` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 3 | `quest_stolen_compass` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 4 | `quest_moon_tide_survey` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 5 | `quest_forest_railway` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 6 | `quest_clockwork_herald` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 7 | `quest_flooded_archive` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 8 | `quest_starlit_observatory` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 9 | `quest_copper_mine_dispute` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 10 | `quest_mountain_pass` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 11 | `quest_marsh_lanterns` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 12 | `quest_garden_of_machines` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 13 | `quest_whispering_canyon` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 14 | `quest_archipelago_mail` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 15 | `quest_ironwood_heirloom` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 16 | `quest_saltwind_market` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 17 | `quest_beacon_constellation` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 18 | `quest_ruins_of_ash` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 19 | `quest_library_of_winds` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 20 | `quest_mirror_lake` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 21 | `quest_tower_chimes` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 22 | `quest_glass_dunes` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 23 | `quest_deepwater_engine` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 24 | `quest_hidden_canal` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 25 | `quest_ember_festival` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 26 | `quest_orchard_winter` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 27 | `quest_jade_quarry` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 28 | `quest_bridge_of_mist` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 29 | `quest_river_sentinel` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 30 | `quest_northern_outpost` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 31 | `quest_cavern_echos` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 32 | `quest_sky_orchards` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 33 | `quest_clocktower_apprentice` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 34 | `quest_wildlife_corridor` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 35 | `quest_aurora_station` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 36 | `quest_drowned_temple` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 37 | `quest_coral_foundry` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 38 | `quest_lost_weather_balloon` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 39 | `quest_underground_orchard` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 40 | `quest_firefly_navigation` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 41 | `quest_solar_tide_engine` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 42 | `quest_icebound_caravan` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 43 | `quest_treetop_council` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 44 | `quest_sextant_apprentice` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 45 | `quest_broken_portal` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 46 | `quest_floating_foundry` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 47 | `quest_night_ferry` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 48 | `quest_echoes_of_the_city` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 49 | `quest_moonlit_greenhouse` | Native six-scene authored quest graph, optional branch and original quest-giver event |
| 50 | `quest_last_skybridge` | Native six-scene authored quest graph, optional branch and original quest-giver event |

The source can be composed through nine producer treatments (waterways, highlands, fortified, nightfall, festival, circuit, secrets, skyreach, wilderness), ten world-gameplay layers (wayfinding, seasons, destructibles, weather, combat, commerce, stealth, verticality, migration, story_convergence) and ten final finishing passes. This book owns one specific director × finish combination; full final tier counts 4.5 million **composed authoring operations**, not 4.5 million independent engines or complete games.

## Canon and gameplay route

1. Read the source-backed quest graph, original-project metadata, current revision, cast IDs and authorized world-layer palette.
2. Query `/api/game-frontier-authoring/recipes?generation=final&domain=living_story&director=audio_cues&finish=character_staging&limit=32` and select an exact registered operation.
3. Generate the original six-scene homebrew quest with an actual in-world quest starter bound to a placed NPC.
4. Add alternative routes and a separately meaningful scene objective without detaching all terminals or omitting canonical choices.
5. Perform the gameplay overlay and director pass, making real map-cell edits and observed-environmental event pages.
6. Apply the requested **character_staging** pass to transform terrain, newly created party poses and the newly created chapter's outcome graph.
7. Check the output against author-supplied story intent, dialogue references, place history and choices before saving.
8. Return the before/after source SHA and deterministic evidence receipts; commit the immutable candidate via host source compare-and-set.
9. Export original native quest records and Godot scene files, then check actual in-game interactions, transitions and resolution.

## Game-authoring and technical signoff

1. Verify original quest first-stage and last-stage reachability.
2. Reject quest IDs colliding with canonical character canon.
3. Retain all existing authored actors and recorded NPC memories.
4. Require a real tile change after each proposed production finish.
5. Require a separate two-sensor typed page, not a fabricated sensor report.
6. Keep environmental proposals outside unauthorized game mutations.
7. Verify all spatial edits respect palette and world-layer bounds.
8. Preserve explicit seed and deterministic game-source digest.
9. Keep source-end quest forks reachable and independently terminable.
10. Allow two differently named chapters to coexist without source overwrite.
11. Never write an unapproved code executor through model-supplied parameters.
12. Recheck player choice implications against previous chapter context.
13. Ensure source event targets exist as placed actors and scenes.
14. Retain canonical save revision and source SHA receipt.
15. Reject stale version compare-and-set, with no partial commit.
16. Inspect Godot terrain source and game expedition path graph.
17. Run native game scene playthrough and record gameplay outcomes.
18. Inspect game loop RAM, frame times and sustained session behavior.
19. Require original IP and asset provenance before publishing.
20. Pass exact-head focused CI, E2E and native platform checks.

## Engine and rights boundaries

The executable source compiler can author tile geometry, story graph branches and typed sensor-driven action proposals; it does not automatically supply motion capture, game AI weights, polished voice acting, or proof that an engine applied each action. Separate code, human/IP, gameplay, copyright and target-device acceptance remains necessary. Longform project partitioning must use authorized versioned source chapters and cannot bypass tenant/project rights.

**Related owner files:** `skeleton/forge/game_frontier_studio_final_production.py`, `skeleton/forge/game_frontier_studio_directed_production.py`, `skeleton/forge/game_frontier_studio_quest_blueprint_factory.py`, `skeleton/testing/test_game_frontier_studio_production_5000000.py`.

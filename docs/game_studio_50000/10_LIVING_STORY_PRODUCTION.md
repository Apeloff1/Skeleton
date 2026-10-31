# Volume 10 — Narrative plus environment-reactive scene direction

> Owner: Forge Studio game-production compiler · Status: committed implementation, qualification pending · Source: `Apeloff1/Skeleton`, PR #4200.

## 01. Delivery contract and authored output

This volume is one of the **ten technical production books** for the 50,000-operation Forge Studio. It covers **living_story**, a family of **4,500 executable compositions**: 50 native archetypes × 9 existing production treatments × 10 new game-system layers.

- **Mission:** Longform authored story with world-state reactions.
- **Primary mutator:** Quest authoring followed by independently evaluated environmental page.
- **Original domain:** `living_story`.
- **Source family:** `quest` (`skeleton/forge/game_frontier_studio_quest_blueprint_factory.py`).
- **Composition registry:** `skeleton/forge/game_frontier_studio_production_recipes.py`.
- **Ten-layer expansion compiler:** `skeleton/forge/game_frontier_studio_system_expansions.py`.
- **Editor/version owner:** canonical `skeleton/forge/game_frontier_studio_authoring.py`, `backend/core/game_frontier_authoring.py` and `game/editor/frontier_studio.json`.
- **Native target:** same expedition world/scene graph and Godot 4 source emitter, not a new engine.

The 4,500 domain operations are distinct combinations of real source-changing behavior. They are **not 4,500 handwritten low-level algorithms or 4,500 finished games**.

## 02. Exact 50 source archetypes

Each row provides a real built source producer, not a planned checklist. Operation `expand_living_story_<archetype>__<treatment>___<system>` is the identity contract.

| # | Source archetype | Composition prefix | Native output |
|---:|---|---|---|
| 1 | `quest_lighthouse_blackout` | `expand_living_story_lighthouse_blackout` | StudioQuest graph + quest-start event |
| 2 | `quest_sky_island_rescue` | `expand_living_story_sky_island_rescue` | StudioQuest graph + quest-start event |
| 3 | `quest_stolen_compass` | `expand_living_story_stolen_compass` | StudioQuest graph + quest-start event |
| 4 | `quest_moon_tide_survey` | `expand_living_story_moon_tide_survey` | StudioQuest graph + quest-start event |
| 5 | `quest_forest_railway` | `expand_living_story_forest_railway` | StudioQuest graph + quest-start event |
| 6 | `quest_clockwork_herald` | `expand_living_story_clockwork_herald` | StudioQuest graph + quest-start event |
| 7 | `quest_flooded_archive` | `expand_living_story_flooded_archive` | StudioQuest graph + quest-start event |
| 8 | `quest_starlit_observatory` | `expand_living_story_starlit_observatory` | StudioQuest graph + quest-start event |
| 9 | `quest_copper_mine_dispute` | `expand_living_story_copper_mine_dispute` | StudioQuest graph + quest-start event |
| 10 | `quest_mountain_pass` | `expand_living_story_mountain_pass` | StudioQuest graph + quest-start event |
| 11 | `quest_marsh_lanterns` | `expand_living_story_marsh_lanterns` | StudioQuest graph + quest-start event |
| 12 | `quest_garden_of_machines` | `expand_living_story_garden_of_machines` | StudioQuest graph + quest-start event |
| 13 | `quest_whispering_canyon` | `expand_living_story_whispering_canyon` | StudioQuest graph + quest-start event |
| 14 | `quest_archipelago_mail` | `expand_living_story_archipelago_mail` | StudioQuest graph + quest-start event |
| 15 | `quest_ironwood_heirloom` | `expand_living_story_ironwood_heirloom` | StudioQuest graph + quest-start event |
| 16 | `quest_saltwind_market` | `expand_living_story_saltwind_market` | StudioQuest graph + quest-start event |
| 17 | `quest_beacon_constellation` | `expand_living_story_beacon_constellation` | StudioQuest graph + quest-start event |
| 18 | `quest_ruins_of_ash` | `expand_living_story_ruins_of_ash` | StudioQuest graph + quest-start event |
| 19 | `quest_library_of_winds` | `expand_living_story_library_of_winds` | StudioQuest graph + quest-start event |
| 20 | `quest_mirror_lake` | `expand_living_story_mirror_lake` | StudioQuest graph + quest-start event |
| 21 | `quest_tower_chimes` | `expand_living_story_tower_chimes` | StudioQuest graph + quest-start event |
| 22 | `quest_glass_dunes` | `expand_living_story_glass_dunes` | StudioQuest graph + quest-start event |
| 23 | `quest_deepwater_engine` | `expand_living_story_deepwater_engine` | StudioQuest graph + quest-start event |
| 24 | `quest_hidden_canal` | `expand_living_story_hidden_canal` | StudioQuest graph + quest-start event |
| 25 | `quest_ember_festival` | `expand_living_story_ember_festival` | StudioQuest graph + quest-start event |
| 26 | `quest_orchard_winter` | `expand_living_story_orchard_winter` | StudioQuest graph + quest-start event |
| 27 | `quest_jade_quarry` | `expand_living_story_jade_quarry` | StudioQuest graph + quest-start event |
| 28 | `quest_bridge_of_mist` | `expand_living_story_bridge_of_mist` | StudioQuest graph + quest-start event |
| 29 | `quest_river_sentinel` | `expand_living_story_river_sentinel` | StudioQuest graph + quest-start event |
| 30 | `quest_northern_outpost` | `expand_living_story_northern_outpost` | StudioQuest graph + quest-start event |
| 31 | `quest_cavern_echos` | `expand_living_story_cavern_echos` | StudioQuest graph + quest-start event |
| 32 | `quest_sky_orchards` | `expand_living_story_sky_orchards` | StudioQuest graph + quest-start event |
| 33 | `quest_clocktower_apprentice` | `expand_living_story_clocktower_apprentice` | StudioQuest graph + quest-start event |
| 34 | `quest_wildlife_corridor` | `expand_living_story_wildlife_corridor` | StudioQuest graph + quest-start event |
| 35 | `quest_aurora_station` | `expand_living_story_aurora_station` | StudioQuest graph + quest-start event |
| 36 | `quest_drowned_temple` | `expand_living_story_drowned_temple` | StudioQuest graph + quest-start event |
| 37 | `quest_coral_foundry` | `expand_living_story_coral_foundry` | StudioQuest graph + quest-start event |
| 38 | `quest_lost_weather_balloon` | `expand_living_story_lost_weather_balloon` | StudioQuest graph + quest-start event |
| 39 | `quest_underground_orchard` | `expand_living_story_underground_orchard` | StudioQuest graph + quest-start event |
| 40 | `quest_firefly_navigation` | `expand_living_story_firefly_navigation` | StudioQuest graph + quest-start event |
| 41 | `quest_solar_tide_engine` | `expand_living_story_solar_tide_engine` | StudioQuest graph + quest-start event |
| 42 | `quest_icebound_caravan` | `expand_living_story_icebound_caravan` | StudioQuest graph + quest-start event |
| 43 | `quest_treetop_council` | `expand_living_story_treetop_council` | StudioQuest graph + quest-start event |
| 44 | `quest_sextant_apprentice` | `expand_living_story_sextant_apprentice` | StudioQuest graph + quest-start event |
| 45 | `quest_broken_portal` | `expand_living_story_broken_portal` | StudioQuest graph + quest-start event |
| 46 | `quest_floating_foundry` | `expand_living_story_floating_foundry` | StudioQuest graph + quest-start event |
| 47 | `quest_night_ferry` | `expand_living_story_night_ferry` | StudioQuest graph + quest-start event |
| 48 | `quest_echoes_of_the_city` | `expand_living_story_echoes_of_the_city` | StudioQuest graph + quest-start event |
| 49 | `quest_moonlit_greenhouse` | `expand_living_story_moonlit_greenhouse` | StudioQuest graph + quest-start event |
| 50 | `quest_last_skybridge` | `expand_living_story_last_skybridge` | StudioQuest graph + quest-start event |

Each archetype participates in nine treatments and ten additional gameplay layers. A source blueprint is executed before the gameplay layer, so a saved edit changes at least one canonical game source structure.

## 03. Nine existing production treatments

| Treatment | Source geometry / actor / story consequence |
|---|---|
| `waterways` | Carve passable riverbank / transport strips in the selected map. Show water-linked orientation and environmental observation conditions. |
| `highlands` | Sculpt altitude-oriented elevated ridge masks. Raise newly spawned actors incrementally; route toward high passes. |
| `fortified` | Write defensible outer perimeter geometry. Rotate new cast toward defensive positions and stage access points. |
| `nightfall` | Place occlusion/cover terrain bands. Offset patrol actors, enable daylight-dependent response. |
| `festival` | Open connected civic paths across the authored ground. Arrange crowds around a public social encounter. |
| `circuit` | Author grid-like service streets and utilities. Place workers along repeatable mechanical-service routes. |
| `secrets` | Carve diagonal hidden alternatives. Add side objective and covert-approach actors. |
| `skyreach` | Create an elevated ring / platform route. Move newly created airborne actors to higher Z. |
| `wilderness` | Scatter natural cover and irregular open routes. Disperse newly generated NPCs and creatures. |

The treatment is applied by the pre-existing 4,500-recipe production compiler. The new gameplay layer applies independently after its source edits.

## 04. Ten new cross-system gameplay layers

| Game system | Spatial construction | Actual sensor pair | Typed runtime proposal |
|---|---|---|---|
| `wayfinding` | Draw connected guide corridors | Heading and fog visibility | inspect_instrument / UI waypoint |
| `seasons` | Paint seasonal ground bands | Temperature and ground ice | change_light / seasonal ambience |
| `destructibles` | Scatter breakable cover geometry | Collision energy and structure integrity | trigger_impact_fx / structure |
| `weather` | Carve storm shelter and movement corridors | Wind speed and rainfall | weather_transition / environment |
| `combat` | Build cover ring and tactical engagement space | Contact count and party morale | start_combat / character |
| `commerce` | Author market/service road crossings | Reputation and quest progress | open_shop / character |
| `stealth` | Create hidden doubleback routes | Sound occlusion and daylight | set_flag / world |
| `verticality` | Build aerial/traversal ring geometry | Updraft and sky island altitude | apply_gameplay_effect / character |
| `migration` | Draw natural habitat migration paths | Humidity and morale | trigger_foliage_fx / environment |
| `story_convergence` | Author meeting-place ground landmarks | Quest progress and NPC reputation | advance_quest / quest |

The environmental event page is stored in the original project and evaluated with observed rather than invented signals. Proposed `start_combat`, `advance_quest`, `open_shop` and other noncommutative actions still need native runtime authorization. Do not confuse an authored event with a completed gameplay mutation.

## 05. Domain-specific original-game construction

The living_story workflow shall generate the following actual, editable content:

1. Read project-scoped `prefab_catalog`, `actor_catalog`, `quest_catalog` and layer palette metadata from the authenticated editor.
2. Choose an archetype from the source inventory above. No arbitrary model-invented backend action names are accepted.
3. Select one of nine production treatments according to the proposed level/story composition.
4. Select one of ten gameplay layers, including an appropriate observability or traversal purpose.
5. Use the current original-game `StudioProject` and source SHA-256. Do not create a separate game state database.
6. Execute `produce_living_story_...__<treatment>` inside the canonical immutable authoring transaction.
7. Paint/rewire actual source tile cells in the selected `MapLayer`, where applicable.
8. Apply any domain-specific generated actors, authored quests, branch alternatives or reactive pages, leaving unrelated existing source untouched.
9. Author one additional gameplay-layer `RPGEventPage` with two legitimate sensor predicates and an approved action category.
10. Persist the complete candidate with the existing host CAS and record before/after content receipts.
11. Export the resulting authored project through the existing expedition/Godot code producer.
12. Validate at least one actual in-game path, triggered page or quest scene in a native runtime before accepting release.

## 06. Executable API example

First search `GET /api/game-frontier-authoring/recipes?generation=expanded&domain=living_story&system_layer=verticality&offset=0&limit=32`.

Then preview a native authoring edit with the exact project revision and saved SHA. The following example requires actual source IDs from the live project and may need different map/palette values:

```json
{
  "expected_version": 7,
  "expected_sha256": "<64-character SHA-256 from inspect>",
  "idempotency_key": "unique-editor-request",
  "steps": [
    {
      "action": "expand_living_story_lighthouse_blackout__skyreach___verticality",
      "parameters": {
        "layer": "ground",
        "x": 0, "y": 0, "width": 12, "height": 12,
        "floor": 0, "wall": 1, "seed": 42,
        "scale": 5, "threshold": 0.53,
        "prefab_id": "merchant", "count": 4, "z": 0,
        "radius": 8, "spacing": 2,
        "instance_id": "chapterA"
      }
    }
  ]
}
```

A second example is `expand_living_story_sky_island_rescue__waterways___wayfinding`, which combines the second archetype and waterways treatment with a true passable wayfinding overlay. Confirm the actual layer palette before exporting.

## 07. Native compiler, runtime and continuity

Quest scene graph composition precedes weather/physics/environment reaction editing. Time, signal state and cooldown persistence belong to the native runtime; page evaluation must not mutate world or canon without approval.

Project source revisions and world exports remain content-addressed. Replaying the same explicit seed and same input source must be deterministic. Multiple authored instances require unique `instance_id` values within a project revision.

## 08. Fail-closed cases and repairs

| Condition | Required correction |
|---|---|
| F01 | Existing project or CAS version does not match the authorized source digest | Reload source; preview against current version |
| F02 | Map region extends beyond the selected 256×256 tile layer bounds | Select a smaller source region |
| F03 | Floor and wall palette choices collapse to the same source tile index | Select distinct valid tile palette indices |
| F04 | Unknown original prefab when domain requires a placed actor | Author/select a real prefab first |
| F05 | Missing quest giver or invalid already-authored start-quest target | Place an eligible quest-giver actor |
| F06 | Reused event/page/quest identity without a distinct instance_id | Choose a new stable instance ID |
| F07 | Non-finite seed, oversized JSON, forged subcommands or invalid geometry | Fix typed request and reject embedded code |
| F08 | Insufficient source file bytes before a 950 KB typed source serialization | Reduce content or split project into authored subprojects |
| F09 | Inactive/dropped native engine capability for an authored action proposal | Retain proposal; test native platform before enabling action |
| F10 | Native navigation and dynamic collision not verified by source-only tests | Run target-engine physics/playthrough acceptance |

Do not suppress a failed producer and claim delivery. The immutable batch returns no persisted partial game when any step is invalid, and the host is responsible for compare-and-set confirmation.

## 09. Acceptance and integration proof

For living_story, measure the following outcomes against **actual** game source, not a gate count:

1. Resolve 50 source archetype identities to their original concrete mutators.
2. Resolve all nine production treatments to separate typed source changes.
3. Resolve all ten gameplay layers to different geometry and RPG event actions.
4. Confirm all 4,500 exact compositions for this domain have unique identifiers.
5. Perform a real project source edit and observe changed hash and changed typed fields.
6. Reject invalid original project identity and stale revision.
7. Reject unknown nested commands, unsafe IDs and out-of-bound tile regions.
8. Confirm repeatable seeds and stable instance ID names.
9. Confirm a second unique instance can coexist with the first.
10. Confirm same instance ID collisions fail rather than replacing canon.
11. Round-trip saved `game/editor/frontier_studio.json` and compare full source digest.
12. Inspect actual emitted Godot tile data, source scripts and expedition waypoints.
13. Check live environmental sensor values satisfy (or suppress) the authored page.
14. Check spawned NPCs, when present, retain valid placement-event bindings.
15. Check newly composed quests, when present, have reachable first/terminal stages.
16. Check unknown gameplay effects remain proposal-only rather than silently mutating state.
17. Check UI search returns at most 64 items and preserves stable next_offset.
18. Verify category browsing remains responsive for 45,000 indexed expansions.
19. Run full focused workflow on exact commit SHA and record failures.
20. Run actual native playthrough and device-resource smoke before release.

## 10. Architecture sign-off and remaining scope

1. Host owns tenant/project authentication; model context cannot grant itself file or game execution authority.
2. Source has one owner: original StudioProject and versioned game-learning editor file.
3. No secondary scene database is introduced by the expansion plan.
4. Every command is built from exactly one previous 4,500-recipe base plus one game-system layer.
5. Existing recipe may itself include two real editor producers; the added layer produces further source changes.
6. Plan index and array offsets are immutable and stable; never reorder without a migration.
7. Gameplay layer changes tiles and adds one typed environmental RPG event page.
8. Only freshly generated cast and quests may be further transformed, preserving old project referents.
9. Sensor readings are not fabricated; pages produce proposals to the runtime approval authority.
10. Godot 4 terrain export is source-derived MultiMesh geometry, not a full collision rebuild.
11. Native connected tile paths use the original palette walkability contract.
12. Game performance and visual fidelity on device require real runtime qualification.
13. Creative material must remain original; IP/source watch and review are release prerequisites.
14. Gameplay traits, AI behavior, assets and music are not pretrained or synthesized by these tile recipes.
15. Documented feature counts describe executable compositions, not unique authored engine implementations.

**Current completion claim:** these 4,500 domain operations are executable **combinations of existing source mutators plus one additional gameplay system**. Their registration and repository commits do not prove 4,500 commercial titles or complete platform-native game playthroughs. Do not merge this construction volume as release certification without the exact-head runtime, rights, code quality and native-engine checks.

**Related docs:** `docs/GAME_FRONTIER_STUDIO_5000_EXECUTABLE_RECIPES.md` and the nine peer volumes in `docs/game_studio_50000/`.

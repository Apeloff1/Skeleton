# Volume 03 — Interactive populations, wildlife, armies and sky settlements

> Owner: Forge Studio game-production compiler · Status: committed implementation, qualification pending · Source: `Apeloff1/Skeleton`, PR #4200.

## 01. Delivery contract and authored output

This volume is one of the **ten technical production books** for the 50,000-operation Forge Studio. It covers **population**, a family of **4,500 executable compositions**: 50 native archetypes × 9 existing production treatments × 10 new game-system layers.

- **Mission:** Source-bound NPC population and gameplay interactions.
- **Primary mutator:** Placement poses, interaction events and cast continuity.
- **Original domain:** `population`.
- **Source family:** `encounter` (`skeleton/forge/game_frontier_studio_encounter_factory.py`).
- **Composition registry:** `skeleton/forge/game_frontier_studio_production_recipes.py`.
- **Ten-layer expansion compiler:** `skeleton/forge/game_frontier_studio_system_expansions.py`.
- **Editor/version owner:** canonical `skeleton/forge/game_frontier_studio_authoring.py`, `backend/core/game_frontier_authoring.py` and `game/editor/frontier_studio.json`.
- **Native target:** same expedition world/scene graph and Godot 4 source emitter, not a new engine.

The 4,500 domain operations are distinct combinations of real source-changing behavior. They are **not 4,500 handwritten low-level algorithms or 4,500 finished games**.

## 02. Exact 50 source archetypes

Each row provides a real built source producer, not a planned checklist. Operation `expand_population_<archetype>__<treatment>___<system>` is the identity contract.

| # | Source archetype | Composition prefix | Native output |
|---:|---|---|---|
| 1 | `encounter_village_crowd` | `expand_population_village_crowd` | StudioPlacement + interact event |
| 2 | `encounter_market_vendors` | `expand_population_market_vendors` | StudioPlacement + interact event |
| 3 | `encounter_tavern_guests` | `expand_population_tavern_guests` | StudioPlacement + interact event |
| 4 | `encounter_festival_parade` | `expand_population_festival_parade` | StudioPlacement + interact event |
| 5 | `encounter_harbor_workers` | `expand_population_harbor_workers` | StudioPlacement + interact event |
| 6 | `encounter_farm_hands` | `expand_population_farm_hands` | StudioPlacement + interact event |
| 7 | `encounter_caravan_merchants` | `expand_population_caravan_merchants` | StudioPlacement + interact event |
| 8 | `encounter_city_patrol` | `expand_population_city_patrol` | StudioPlacement + interact event |
| 9 | `encounter_castle_guards` | `expand_population_castle_guards` | StudioPlacement + interact event |
| 10 | `encounter_royal_court` | `expand_population_royal_court` | StudioPlacement + interact event |
| 11 | `encounter_wolf_pack` | `expand_population_wolf_pack` | StudioPlacement + interact event |
| 12 | `encounter_deer_herd` | `expand_population_deer_herd` | StudioPlacement + interact event |
| 13 | `encounter_bird_flock` | `expand_population_bird_flock` | StudioPlacement + interact event |
| 14 | `encounter_fish_school` | `expand_population_fish_school` | StudioPlacement + interact event |
| 15 | `encounter_insect_swarm` | `expand_population_insect_swarm` | StudioPlacement + interact event |
| 16 | `encounter_horse_stampede` | `expand_population_horse_stampede` | StudioPlacement + interact event |
| 17 | `encounter_bear_den` | `expand_population_bear_den` | StudioPlacement + interact event |
| 18 | `encounter_predator_ring` | `expand_population_predator_ring` | StudioPlacement + interact event |
| 19 | `encounter_migratory_line` | `expand_population_migratory_line` | StudioPlacement + interact event |
| 20 | `encounter_turtle_nesting` | `expand_population_turtle_nesting` | StudioPlacement + interact event |
| 21 | `encounter_squad_wedge` | `expand_population_squad_wedge` | StudioPlacement + interact event |
| 22 | `encounter_siege_lines` | `expand_population_siege_lines` | StudioPlacement + interact event |
| 23 | `encounter_archer_wall` | `expand_population_archer_wall` | StudioPlacement + interact event |
| 24 | `encounter_shield_circle` | `expand_population_shield_circle` | StudioPlacement + interact event |
| 25 | `encounter_cavalry_charge` | `expand_population_cavalry_charge` | StudioPlacement + interact event |
| 26 | `encounter_ambush_arcs` | `expand_population_ambush_arcs` | StudioPlacement + interact event |
| 27 | `encounter_flanking_pincer` | `expand_population_flanking_pincer` | StudioPlacement + interact event |
| 28 | `encounter_rear_guard` | `expand_population_rear_guard` | StudioPlacement + interact event |
| 29 | `encounter_scout_net` | `expand_population_scout_net` | StudioPlacement + interact event |
| 30 | `encounter_boss_minions` | `expand_population_boss_minions` | StudioPlacement + interact event |
| 31 | `encounter_sky_pirates` | `expand_population_sky_pirates` | StudioPlacement + interact event |
| 32 | `encounter_airship_crew` | `expand_population_airship_crew` | StudioPlacement + interact event |
| 33 | `encounter_cloud_drakes` | `expand_population_cloud_drakes` | StudioPlacement + interact event |
| 34 | `encounter_floating_island_settlers` | `expand_population_floating_island_settlers` | StudioPlacement + interact event |
| 35 | `encounter_wind_surfers` | `expand_population_wind_surfers` | StudioPlacement + interact event |
| 36 | `encounter_tower_watchers` | `expand_population_tower_watchers` | StudioPlacement + interact event |
| 37 | `encounter_balloon_riders` | `expand_population_balloon_riders` | StudioPlacement + interact event |
| 38 | `encounter_glider_convoy` | `expand_population_glider_convoy` | StudioPlacement + interact event |
| 39 | `encounter_sky_fishermen` | `expand_population_sky_fishermen` | StudioPlacement + interact event |
| 40 | `encounter_aurora_procession` | `expand_population_aurora_procession` | StudioPlacement + interact event |
| 41 | `encounter_dungeon_slimes` | `expand_population_dungeon_slimes` | StudioPlacement + interact event |
| 42 | `encounter_cave_bats` | `expand_population_cave_bats` | StudioPlacement + interact event |
| 43 | `encounter_crypt_guardians` | `expand_population_crypt_guardians` | StudioPlacement + interact event |
| 44 | `encounter_labyrinth_wardens` | `expand_population_labyrinth_wardens` | StudioPlacement + interact event |
| 45 | `encounter_treasure_mimics` | `expand_population_treasure_mimics` | StudioPlacement + interact event |
| 46 | `encounter_portal_sentinels` | `expand_population_portal_sentinels` | StudioPlacement + interact event |
| 47 | `encounter_ruin_explorers` | `expand_population_ruin_explorers` | StudioPlacement + interact event |
| 48 | `encounter_mine_workers` | `expand_population_mine_workers` | StudioPlacement + interact event |
| 49 | `encounter_fungal_foragers` | `expand_population_fungal_foragers` | StudioPlacement + interact event |
| 50 | `encounter_underground_merchants` | `expand_population_underground_merchants` | StudioPlacement + interact event |

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

The population workflow shall generate the following actual, editable content:

1. Read project-scoped `prefab_catalog`, `actor_catalog`, `quest_catalog` and layer palette metadata from the authenticated editor.
2. Choose an archetype from the source inventory above. No arbitrary model-invented backend action names are accepted.
3. Select one of nine production treatments according to the proposed level/story composition.
4. Select one of ten gameplay layers, including an appropriate observability or traversal purpose.
5. Use the current original-game `StudioProject` and source SHA-256. Do not create a separate game state database.
6. Execute `produce_population_...__<treatment>` inside the canonical immutable authoring transaction.
7. Paint/rewire actual source tile cells in the selected `MapLayer`, where applicable.
8. Apply any domain-specific generated actors, authored quests, branch alternatives or reactive pages, leaving unrelated existing source untouched.
9. Author one additional gameplay-layer `RPGEventPage` with two legitimate sensor predicates and an approved action category.
10. Persist the complete candidate with the existing host CAS and record before/after content receipts.
11. Export the resulting authored project through the existing expedition/Godot code producer.
12. Validate at least one actual in-game path, triggered page or quest scene in a native runtime before accepting release.

## 06. Executable API example

First search `GET /api/game-frontier-authoring/recipes?generation=expanded&domain=population&system_layer=verticality&offset=0&limit=32`.

Then preview a native authoring edit with the exact project revision and saved SHA. The following example requires actual source IDs from the live project and may need different map/palette values:

```json
{
  "expected_version": 7,
  "expected_sha256": "<64-character SHA-256 from inspect>",
  "idempotency_key": "unique-editor-request",
  "steps": [
    {
      "action": "expand_population_village_crowd__skyreach___verticality",
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

A second example is `expand_population_market_vendors__waterways___wayfinding`, which combines the second archetype and waterways treatment with a true passable wayfinding overlay. Confirm the actual layer palette before exporting.

## 07. Native compiler, runtime and continuity

Each newly spawned actor has a real prefab identity, XYZ location, facing and a stable interact event target. Only the new cast can be repositioned by the gameplay layer. This is not a trained NPC behavior model.

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

For population, measure the following outcomes against **actual** game source, not a gate count:

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

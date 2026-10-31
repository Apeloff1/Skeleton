# Volume 05 — Weather, navigation, physics, music and RPG sensing

> Owner: Forge Studio game-production compiler · Status: committed implementation, qualification pending · Source: `Apeloff1/Skeleton`, PR #4200.

## 01. Delivery contract and authored output

This volume is one of the **ten technical production books** for the 50,000-operation Forge Studio. It covers **atmosphere**, a family of **4,500 executable compositions**: 50 native archetypes × 9 existing production treatments × 10 new game-system layers.

- **Mission:** Conditional environmental gameplay with measured signals.
- **Primary mutator:** Two-signal deterministic reaction pages and game action proposals.
- **Original domain:** `atmosphere`.
- **Source family:** `reaction` (`skeleton/forge/game_frontier_studio_reactive_scene_factory.py`).
- **Composition registry:** `skeleton/forge/game_frontier_studio_production_recipes.py`.
- **Ten-layer expansion compiler:** `skeleton/forge/game_frontier_studio_system_expansions.py`.
- **Editor/version owner:** canonical `skeleton/forge/game_frontier_studio_authoring.py`, `backend/core/game_frontier_authoring.py` and `game/editor/frontier_studio.json`.
- **Native target:** same expedition world/scene graph and Godot 4 source emitter, not a new engine.

The 4,500 domain operations are distinct combinations of real source-changing behavior. They are **not 4,500 handwritten low-level algorithms or 4,500 finished games**.

## 02. Exact 50 source archetypes

Each row provides a real built source producer, not a planned checklist. Operation `expand_atmosphere_<archetype>__<treatment>___<system>` is the identity contract.

| # | Source archetype | Composition prefix | Native output |
|---:|---|---|---|
| 1 | `reaction_storm_warning` | `expand_atmosphere_storm_warning` | RPGEventPage sensor proposal |
| 2 | `reaction_rain_audio` | `expand_atmosphere_rain_audio` | RPGEventPage sensor proposal |
| 3 | `reaction_fog_camera` | `expand_atmosphere_fog_camera` | RPGEventPage sensor proposal |
| 4 | `reaction_gale_sails` | `expand_atmosphere_gale_sails` | RPGEventPage sensor proposal |
| 5 | `reaction_wet_roads` | `expand_atmosphere_wet_roads` | RPGEventPage sensor proposal |
| 6 | `reaction_river_flood` | `expand_atmosphere_river_flood` | RPGEventPage sensor proposal |
| 7 | `reaction_ground_freeze` | `expand_atmosphere_ground_freeze` | RPGEventPage sensor proposal |
| 8 | `reaction_turbulence_fx` | `expand_atmosphere_turbulence_fx` | RPGEventPage sensor proposal |
| 9 | `reaction_hail_shelter` | `expand_atmosphere_hail_shelter` | RPGEventPage sensor proposal |
| 10 | `reaction_humidity_fog` | `expand_atmosphere_humidity_fog` | RPGEventPage sensor proposal |
| 11 | `reaction_terminal_fall` | `expand_atmosphere_terminal_fall` | RPGEventPage sensor proposal |
| 12 | `reaction_rough_landing` | `expand_atmosphere_rough_landing` | RPGEventPage sensor proposal |
| 13 | `reaction_kinetic_impact` | `expand_atmosphere_kinetic_impact` | RPGEventPage sensor proposal |
| 14 | `reaction_skin_tension` | `expand_atmosphere_skin_tension` | RPGEventPage sensor proposal |
| 15 | `reaction_low_stability` | `expand_atmosphere_low_stability` | RPGEventPage sensor proposal |
| 16 | `reaction_cliff_climb` | `expand_atmosphere_cliff_climb` | RPGEventPage sensor proposal |
| 17 | `reaction_weight_shift` | `expand_atmosphere_weight_shift` | RPGEventPage sensor proposal |
| 18 | `reaction_slick_fabric` | `expand_atmosphere_slick_fabric` | RPGEventPage sensor proposal |
| 19 | `reaction_updraft_lift` | `expand_atmosphere_updraft_lift` | RPGEventPage sensor proposal |
| 20 | `reaction_native_field` | `expand_atmosphere_native_field` | RPGEventPage sensor proposal |
| 21 | `reaction_altitude_chart` | `expand_atmosphere_altitude_chart` | RPGEventPage sensor proposal |
| 22 | `reaction_sextant_sighting` | `expand_atmosphere_sextant_sighting` | RPGEventPage sensor proposal |
| 23 | `reaction_bubble_sextant` | `expand_atmosphere_bubble_sextant` | RPGEventPage sensor proposal |
| 24 | `reaction_compass_turn` | `expand_atmosphere_compass_turn` | RPGEventPage sensor proposal |
| 25 | `reaction_triangulation` | `expand_atmosphere_triangulation` | RPGEventPage sensor proposal |
| 26 | `reaction_skyisland_arrival` | `expand_atmosphere_skyisland_arrival` | RPGEventPage sensor proposal |
| 27 | `reaction_gyro_drift` | `expand_atmosphere_gyro_drift` | RPGEventPage sensor proposal |
| 28 | `reaction_pressure_front` | `expand_atmosphere_pressure_front` | RPGEventPage sensor proposal |
| 29 | `reaction_navigation_current` | `expand_atmosphere_navigation_current` | RPGEventPage sensor proposal |
| 30 | `reaction_night_navigation` | `expand_atmosphere_night_navigation` | RPGEventPage sensor proposal |
| 31 | `reaction_party_low_morale` | `expand_atmosphere_party_low_morale` | RPGEventPage sensor proposal |
| 32 | `reaction_heroic_reputation` | `expand_atmosphere_heroic_reputation` | RPGEventPage sensor proposal |
| 33 | `reaction_quest_music` | `expand_atmosphere_quest_music` | RPGEventPage sensor proposal |
| 34 | `reaction_village_emotion` | `expand_atmosphere_village_emotion` | RPGEventPage sensor proposal |
| 35 | `reaction_party_morale_boost` | `expand_atmosphere_party_morale_boost` | RPGEventPage sensor proposal |
| 36 | `reaction_combat_music` | `expand_atmosphere_combat_music` | RPGEventPage sensor proposal |
| 37 | `reaction_stealth_audio` | `expand_atmosphere_stealth_audio` | RPGEventPage sensor proposal |
| 38 | `reaction_world_axis` | `expand_atmosphere_world_axis` | RPGEventPage sensor proposal |
| 39 | `reaction_quest_unlock` | `expand_atmosphere_quest_unlock` | RPGEventPage sensor proposal |
| 40 | `reaction_morale_camp` | `expand_atmosphere_morale_camp` | RPGEventPage sensor proposal |
| 41 | `reaction_moon_tide` | `expand_atmosphere_moon_tide` | RPGEventPage sensor proposal |
| 42 | `reaction_sunrise_cinematic` | `expand_atmosphere_sunrise_cinematic` | RPGEventPage sensor proposal |
| 43 | `reaction_eclipse_shadows` | `expand_atmosphere_eclipse_shadows` | RPGEventPage sensor proposal |
| 44 | `reaction_foliage_shadow` | `expand_atmosphere_foliage_shadow` | RPGEventPage sensor proposal |
| 45 | `reaction_terrain_erosion` | `expand_atmosphere_terrain_erosion` | RPGEventPage sensor proposal |
| 46 | `reaction_falling_building` | `expand_atmosphere_falling_building` | RPGEventPage sensor proposal |
| 47 | `reaction_cloud_portal` | `expand_atmosphere_cloud_portal` | RPGEventPage sensor proposal |
| 48 | `reaction_tidal_reef` | `expand_atmosphere_tidal_reef` | RPGEventPage sensor proposal |
| 49 | `reaction_deep_night` | `expand_atmosphere_deep_night` | RPGEventPage sensor proposal |
| 50 | `reaction_seasonal_bloom` | `expand_atmosphere_seasonal_bloom` | RPGEventPage sensor proposal |

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

The atmosphere workflow shall generate the following actual, editable content:

1. Read project-scoped `prefab_catalog`, `actor_catalog`, `quest_catalog` and layer palette metadata from the authenticated editor.
2. Choose an archetype from the source inventory above. No arbitrary model-invented backend action names are accepted.
3. Select one of nine production treatments according to the proposed level/story composition.
4. Select one of ten gameplay layers, including an appropriate observability or traversal purpose.
5. Use the current original-game `StudioProject` and source SHA-256. Do not create a separate game state database.
6. Execute `produce_atmosphere_...__<treatment>` inside the canonical immutable authoring transaction.
7. Paint/rewire actual source tile cells in the selected `MapLayer`, where applicable.
8. Apply any domain-specific generated actors, authored quests, branch alternatives or reactive pages, leaving unrelated existing source untouched.
9. Author one additional gameplay-layer `RPGEventPage` with two legitimate sensor predicates and an approved action category.
10. Persist the complete candidate with the existing host CAS and record before/after content receipts.
11. Export the resulting authored project through the existing expedition/Godot code producer.
12. Validate at least one actual in-game path, triggered page or quest scene in a native runtime before accepting release.

## 06. Executable API example

First search `GET /api/game-frontier-authoring/recipes?generation=expanded&domain=atmosphere&system_layer=verticality&offset=0&limit=32`.

Then preview a native authoring edit with the exact project revision and saved SHA. The following example requires actual source IDs from the live project and may need different map/palette values:

```json
{
  "expected_version": 7,
  "expected_sha256": "<64-character SHA-256 from inspect>",
  "idempotency_key": "unique-editor-request",
  "steps": [
    {
      "action": "expand_atmosphere_storm_warning__skyreach___verticality",
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

A second example is `expand_atmosphere_rain_audio__waterways___wayfinding`, which combines the second archetype and waterways treatment with a true passable wayfinding overlay. Confirm the actual layer palette before exporting.

## 07. Native compiler, runtime and continuity

A source-native RPG page includes two prerequisite sensor comparisons, an allowed action proposal and cooldown. The expansion adds a third page for the gameplay system. Native observed measurements must be supplied; the editor cannot fabricate weather or force fields.

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

For atmosphere, measure the following outcomes against **actual** game source, not a gate count:

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

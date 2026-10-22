# Volume 02 — Buildable settlements and structural traversal

> Owner: Forge Studio game-production compiler · Status: committed implementation, qualification pending · Source: `Apeloff1/Skeleton`, PR #4200.

## 01. Delivery contract and authored output

This volume is one of the **ten technical production books** for the 50,000-operation Forge Studio. It covers **architecture**, a family of **4,500 executable compositions**: 50 native archetypes × 9 existing production treatments × 10 new game-system layers.

- **Mission:** Connected inhabited world structure.
- **Primary mutator:** Architectural floor/wall layout and traversable construction.
- **Original domain:** `architecture`.
- **Source family:** `structure` (`skeleton/forge/game_frontier_studio_structure_factory.py`).
- **Composition registry:** `skeleton/forge/game_frontier_studio_production_recipes.py`.
- **Ten-layer expansion compiler:** `skeleton/forge/game_frontier_studio_system_expansions.py`.
- **Editor/version owner:** canonical `skeleton/forge/game_frontier_studio_authoring.py`, `backend/core/game_frontier_authoring.py` and `game/editor/frontier_studio.json`.
- **Native target:** same expedition world/scene graph and Godot 4 source emitter, not a new engine.

The 4,500 domain operations are distinct combinations of real source-changing behavior. They are **not 4,500 handwritten low-level algorithms or 4,500 finished games**.

## 02. Exact 50 source archetypes

Each row provides a real built source producer, not a planned checklist. Operation `expand_architecture_<archetype>__<treatment>___<system>` is the identity contract.

| # | Source archetype | Composition prefix | Native output |
|---:|---|---|---|
| 1 | `structure_village_square` | `expand_architecture_village_square` | Walkable/blocked architectural tile cells |
| 2 | `structure_market_stalls` | `expand_architecture_market_stalls` | Walkable/blocked architectural tile cells |
| 3 | `structure_courtyard` | `expand_architecture_courtyard` | Walkable/blocked architectural tile cells |
| 4 | `structure_town_grid` | `expand_architecture_town_grid` | Walkable/blocked architectural tile cells |
| 5 | `structure_radial_city` | `expand_architecture_radial_city` | Walkable/blocked architectural tile cells |
| 6 | `structure_harbor_piers` | `expand_architecture_harbor_piers` | Walkable/blocked architectural tile cells |
| 7 | `structure_farm_fields` | `expand_architecture_farm_fields` | Walkable/blocked architectural tile cells |
| 8 | `structure_orchard_rows` | `expand_architecture_orchard_rows` | Walkable/blocked architectural tile cells |
| 9 | `structure_house_cluster` | `expand_architecture_house_cluster` | Walkable/blocked architectural tile cells |
| 10 | `structure_canal_district` | `expand_architecture_canal_district` | Walkable/blocked architectural tile cells |
| 11 | `structure_castle_keep` | `expand_architecture_castle_keep` | Walkable/blocked architectural tile cells |
| 12 | `structure_outer_wall` | `expand_architecture_outer_wall` | Walkable/blocked architectural tile cells |
| 13 | `structure_gatehouse` | `expand_architecture_gatehouse` | Walkable/blocked architectural tile cells |
| 14 | `structure_corner_bastions` | `expand_architecture_corner_bastions` | Walkable/blocked architectural tile cells |
| 15 | `structure_moat_bridge` | `expand_architecture_moat_bridge` | Walkable/blocked architectural tile cells |
| 16 | `structure_watchtowers` | `expand_architecture_watchtowers` | Walkable/blocked architectural tile cells |
| 17 | `structure_wall_walk` | `expand_architecture_wall_walk` | Walkable/blocked architectural tile cells |
| 18 | `structure_arrow_slits` | `expand_architecture_arrow_slits` | Walkable/blocked architectural tile cells |
| 19 | `structure_turret_ring` | `expand_architecture_turret_ring` | Walkable/blocked architectural tile cells |
| 20 | `structure_fortified_crossroads` | `expand_architecture_fortified_crossroads` | Walkable/blocked architectural tile cells |
| 21 | `structure_dungeon_rooms` | `expand_architecture_dungeon_rooms` | Walkable/blocked architectural tile cells |
| 22 | `structure_dungeon_corridors` | `expand_architecture_dungeon_corridors` | Walkable/blocked architectural tile cells |
| 23 | `structure_spiral_vault` | `expand_architecture_spiral_vault` | Walkable/blocked architectural tile cells |
| 24 | `structure_treasure_chambers` | `expand_architecture_treasure_chambers` | Walkable/blocked architectural tile cells |
| 25 | `structure_pillar_hall` | `expand_architecture_pillar_hall` | Walkable/blocked architectural tile cells |
| 26 | `structure_prison_cells` | `expand_architecture_prison_cells` | Walkable/blocked architectural tile cells |
| 27 | `structure_cathedral_nave` | `expand_architecture_cathedral_nave` | Walkable/blocked architectural tile cells |
| 28 | `structure_catacomb_grid` | `expand_architecture_catacomb_grid` | Walkable/blocked architectural tile cells |
| 29 | `structure_trap_gauntlet` | `expand_architecture_trap_gauntlet` | Walkable/blocked architectural tile cells |
| 30 | `structure_boss_arena` | `expand_architecture_boss_arena` | Walkable/blocked architectural tile cells |
| 31 | `structure_factory_floor` | `expand_architecture_factory_floor` | Walkable/blocked architectural tile cells |
| 32 | `structure_conveyor_lanes` | `expand_architecture_conveyor_lanes` | Walkable/blocked architectural tile cells |
| 33 | `structure_power_grid` | `expand_architecture_power_grid` | Walkable/blocked architectural tile cells |
| 34 | `structure_storage_racks` | `expand_architecture_storage_racks` | Walkable/blocked architectural tile cells |
| 35 | `structure_warehouse_aisles` | `expand_architecture_warehouse_aisles` | Walkable/blocked architectural tile cells |
| 36 | `structure_rail_depot` | `expand_architecture_rail_depot` | Walkable/blocked architectural tile cells |
| 37 | `structure_shipyard_slips` | `expand_architecture_shipyard_slips` | Walkable/blocked architectural tile cells |
| 38 | `structure_mining_shafts` | `expand_architecture_mining_shafts` | Walkable/blocked architectural tile cells |
| 39 | `structure_pipeline_array` | `expand_architecture_pipeline_array` | Walkable/blocked architectural tile cells |
| 40 | `structure_reactor_chamber` | `expand_architecture_reactor_chamber` | Walkable/blocked architectural tile cells |
| 41 | `structure_suspension_bridge` | `expand_architecture_suspension_bridge` | Walkable/blocked architectural tile cells |
| 42 | `structure_stepping_stones` | `expand_architecture_stepping_stones` | Walkable/blocked architectural tile cells |
| 43 | `structure_ramp_switchbacks` | `expand_architecture_ramp_switchbacks` | Walkable/blocked architectural tile cells |
| 44 | `structure_cliff_stairs` | `expand_architecture_cliff_stairs` | Walkable/blocked architectural tile cells |
| 45 | `structure_tunnel_bore` | `expand_architecture_tunnel_bore` | Walkable/blocked architectural tile cells |
| 46 | `structure_treetop_walks` | `expand_architecture_treetop_walks` | Walkable/blocked architectural tile cells |
| 47 | `structure_sky_platforms` | `expand_architecture_sky_platforms` | Walkable/blocked architectural tile cells |
| 48 | `structure_rope_bridge` | `expand_architecture_rope_bridge` | Walkable/blocked architectural tile cells |
| 49 | `structure_portal_plaza` | `expand_architecture_portal_plaza` | Walkable/blocked architectural tile cells |
| 50 | `structure_island_airfield` | `expand_architecture_island_airfield` | Walkable/blocked architectural tile cells |

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

The architecture workflow shall generate the following actual, editable content:

1. Read project-scoped `prefab_catalog`, `actor_catalog`, `quest_catalog` and layer palette metadata from the authenticated editor.
2. Choose an archetype from the source inventory above. No arbitrary model-invented backend action names are accepted.
3. Select one of nine production treatments according to the proposed level/story composition.
4. Select one of ten gameplay layers, including an appropriate observability or traversal purpose.
5. Use the current original-game `StudioProject` and source SHA-256. Do not create a separate game state database.
6. Execute `produce_architecture_...__<treatment>` inside the canonical immutable authoring transaction.
7. Paint/rewire actual source tile cells in the selected `MapLayer`, where applicable.
8. Apply any domain-specific generated actors, authored quests, branch alternatives or reactive pages, leaving unrelated existing source untouched.
9. Author one additional gameplay-layer `RPGEventPage` with two legitimate sensor predicates and an approved action category.
10. Persist the complete candidate with the existing host CAS and record before/after content receipts.
11. Export the resulting authored project through the existing expedition/Godot code producer.
12. Validate at least one actual in-game path, triggered page or quest scene in a native runtime before accepting release.

## 06. Executable API example

First search `GET /api/game-frontier-authoring/recipes?generation=expanded&domain=architecture&system_layer=verticality&offset=0&limit=32`.

Then preview a native authoring edit with the exact project revision and saved SHA. The following example requires actual source IDs from the live project and may need different map/palette values:

```json
{
  "expected_version": 7,
  "expected_sha256": "<64-character SHA-256 from inspect>",
  "idempotency_key": "unique-editor-request",
  "steps": [
    {
      "action": "expand_architecture_village_square__skyreach___verticality",
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

A second example is `expand_architecture_market_stalls__waterways___wayfinding`, which combines the second archetype and waterways treatment with a true passable wayfinding overlay. Confirm the actual layer palette before exporting.

## 07. Native compiler, runtime and continuity

Architectural plans are tile geometry and generated traversable walkways. They are not fully rigged or textured 3D castles; real physics/mesh collision work remains a separate native engine responsibility.

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

For architecture, measure the following outcomes against **actual** game source, not a gate count:

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

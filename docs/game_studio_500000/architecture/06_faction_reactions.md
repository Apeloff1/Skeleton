# ARCHITECTURE · Faction-driven play director
## Forge Studio 500,000-production collection · Book 025 / 100

**Code owner:** `skeleton/forge/game_frontier_studio_directed_production.py` · **Game domain:** `architecture` · **Director:** `faction_reactions`

### What this operator builds
Cities, infrastructure, dungeon and architecture layouts. The director additionally does: **Author allegiance-facing interaction routes and grouping**. The output is real authored `StudioProject` source, not a self-contained game engine or quality-gate counter.

An operation runs the previously implemented source recipe, the previously implemented gameplay overlay, then creates a further deterministic tile edit and an independently measured typed RPG event page. When the underlying recipe generated new actors or a new quest, only these freshly authored records are redirected into the director's arrangement or branch.

**Key gameplay invariant:** Choices should respect canonical faction reputation instead of fabricating character memory.

### All fifty concrete source archetypes available

Each row expands through nine treatments and ten existing gameplay systems. Every resulting production name has a unique stable exact identity.

| # | Implemented source archetype | Exact directed command pattern |
|---:|---|---|
| 01 | `structure_village_square` | `direct_architecture_village_square__<treatment>___<system>____faction_reactions` |
| 02 | `structure_market_stalls` | `direct_architecture_market_stalls__<treatment>___<system>____faction_reactions` |
| 03 | `structure_courtyard` | `direct_architecture_courtyard__<treatment>___<system>____faction_reactions` |
| 04 | `structure_town_grid` | `direct_architecture_town_grid__<treatment>___<system>____faction_reactions` |
| 05 | `structure_radial_city` | `direct_architecture_radial_city__<treatment>___<system>____faction_reactions` |
| 06 | `structure_harbor_piers` | `direct_architecture_harbor_piers__<treatment>___<system>____faction_reactions` |
| 07 | `structure_farm_fields` | `direct_architecture_farm_fields__<treatment>___<system>____faction_reactions` |
| 08 | `structure_orchard_rows` | `direct_architecture_orchard_rows__<treatment>___<system>____faction_reactions` |
| 09 | `structure_house_cluster` | `direct_architecture_house_cluster__<treatment>___<system>____faction_reactions` |
| 10 | `structure_canal_district` | `direct_architecture_canal_district__<treatment>___<system>____faction_reactions` |
| 11 | `structure_castle_keep` | `direct_architecture_castle_keep__<treatment>___<system>____faction_reactions` |
| 12 | `structure_outer_wall` | `direct_architecture_outer_wall__<treatment>___<system>____faction_reactions` |
| 13 | `structure_gatehouse` | `direct_architecture_gatehouse__<treatment>___<system>____faction_reactions` |
| 14 | `structure_corner_bastions` | `direct_architecture_corner_bastions__<treatment>___<system>____faction_reactions` |
| 15 | `structure_moat_bridge` | `direct_architecture_moat_bridge__<treatment>___<system>____faction_reactions` |
| 16 | `structure_watchtowers` | `direct_architecture_watchtowers__<treatment>___<system>____faction_reactions` |
| 17 | `structure_wall_walk` | `direct_architecture_wall_walk__<treatment>___<system>____faction_reactions` |
| 18 | `structure_arrow_slits` | `direct_architecture_arrow_slits__<treatment>___<system>____faction_reactions` |
| 19 | `structure_turret_ring` | `direct_architecture_turret_ring__<treatment>___<system>____faction_reactions` |
| 20 | `structure_fortified_crossroads` | `direct_architecture_fortified_crossroads__<treatment>___<system>____faction_reactions` |
| 21 | `structure_dungeon_rooms` | `direct_architecture_dungeon_rooms__<treatment>___<system>____faction_reactions` |
| 22 | `structure_dungeon_corridors` | `direct_architecture_dungeon_corridors__<treatment>___<system>____faction_reactions` |
| 23 | `structure_spiral_vault` | `direct_architecture_spiral_vault__<treatment>___<system>____faction_reactions` |
| 24 | `structure_treasure_chambers` | `direct_architecture_treasure_chambers__<treatment>___<system>____faction_reactions` |
| 25 | `structure_pillar_hall` | `direct_architecture_pillar_hall__<treatment>___<system>____faction_reactions` |
| 26 | `structure_prison_cells` | `direct_architecture_prison_cells__<treatment>___<system>____faction_reactions` |
| 27 | `structure_cathedral_nave` | `direct_architecture_cathedral_nave__<treatment>___<system>____faction_reactions` |
| 28 | `structure_catacomb_grid` | `direct_architecture_catacomb_grid__<treatment>___<system>____faction_reactions` |
| 29 | `structure_trap_gauntlet` | `direct_architecture_trap_gauntlet__<treatment>___<system>____faction_reactions` |
| 30 | `structure_boss_arena` | `direct_architecture_boss_arena__<treatment>___<system>____faction_reactions` |
| 31 | `structure_factory_floor` | `direct_architecture_factory_floor__<treatment>___<system>____faction_reactions` |
| 32 | `structure_conveyor_lanes` | `direct_architecture_conveyor_lanes__<treatment>___<system>____faction_reactions` |
| 33 | `structure_power_grid` | `direct_architecture_power_grid__<treatment>___<system>____faction_reactions` |
| 34 | `structure_storage_racks` | `direct_architecture_storage_racks__<treatment>___<system>____faction_reactions` |
| 35 | `structure_warehouse_aisles` | `direct_architecture_warehouse_aisles__<treatment>___<system>____faction_reactions` |
| 36 | `structure_rail_depot` | `direct_architecture_rail_depot__<treatment>___<system>____faction_reactions` |
| 37 | `structure_shipyard_slips` | `direct_architecture_shipyard_slips__<treatment>___<system>____faction_reactions` |
| 38 | `structure_mining_shafts` | `direct_architecture_mining_shafts__<treatment>___<system>____faction_reactions` |
| 39 | `structure_pipeline_array` | `direct_architecture_pipeline_array__<treatment>___<system>____faction_reactions` |
| 40 | `structure_reactor_chamber` | `direct_architecture_reactor_chamber__<treatment>___<system>____faction_reactions` |
| 41 | `structure_suspension_bridge` | `direct_architecture_suspension_bridge__<treatment>___<system>____faction_reactions` |
| 42 | `structure_stepping_stones` | `direct_architecture_stepping_stones__<treatment>___<system>____faction_reactions` |
| 43 | `structure_ramp_switchbacks` | `direct_architecture_ramp_switchbacks__<treatment>___<system>____faction_reactions` |
| 44 | `structure_cliff_stairs` | `direct_architecture_cliff_stairs__<treatment>___<system>____faction_reactions` |
| 45 | `structure_tunnel_bore` | `direct_architecture_tunnel_bore__<treatment>___<system>____faction_reactions` |
| 46 | `structure_treetop_walks` | `direct_architecture_treetop_walks__<treatment>___<system>____faction_reactions` |
| 47 | `structure_sky_platforms` | `direct_architecture_sky_platforms__<treatment>___<system>____faction_reactions` |
| 48 | `structure_rope_bridge` | `direct_architecture_rope_bridge__<treatment>___<system>____faction_reactions` |
| 49 | `structure_portal_plaza` | `direct_architecture_portal_plaza__<treatment>___<system>____faction_reactions` |
| 50 | `structure_island_airfield` | `direct_architecture_island_airfield__<treatment>___<system>____faction_reactions` |

### Production combinations and complexity budget

- 50 concrete structure authoring archetypes × 9 production treatments × 10 gameplay systems × **this director** = **4,500 executable composed production commands**.
- Nine spatial/narrative treatments: `waterways`, `highlands`, `fortified`, `nightfall`, `festival`, `circuit`, `secrets`, `skyreach`, `wilderness`.
- Ten prior gameplay systems: `wayfinding`, `seasons`, `destructibles`, `weather`, `combat`, `commerce`, `stealth`, `verticality`, `migration`, `story_convergence`.
- The complete 10-domain × 10-director directed registry contains **450,000** operations, and the full Studio catalog **500,000**.
- Names are virtual indexed contracts, not half a million eagerly constructed Python objects. Searching returns at most 64 metadata records per request.
- Source storage uses the canonical typed project source document with the existing project revision CAS and fail-closed schema validator.

### Typed direct execution example

```json
{
  "action": "direct_architecture_market_stalls__skyreach___verticality____faction_reactions",
  "parameters": {
    "layer": "ground", "x": 0, "y": 0, "width": 12, "height": 12,
    "floor": 0, "wall": 1, "seed": 42,
    "scale": 5, "threshold": 0.53,
    "prefab_id": "merchant", "count": 4,
    "radius": 8, "spacing": 2, "z": 0,
    "instance_id": "chapter_A"
  }
}
```

These example layer, palette, actor and project identifiers MUST be replaced by actual accessible project-source IDs. A missing prefab fails closed rather than being synthesized silently. `instance_id` permits a separate content-addressed chapter; reusing an identity must not overwrite canon.

### Native game integration path

1. The authenticated game-learning workspace resolves tenant, owner, project, source revision and source digest.
2. `game_frontier_studio_authoring.py` resolves this exact command in its virtual `AuthoringCatalogue`, then routes to the directed compiler.
3. The directed compiler resolves one real earlier `EXPANDED_RECIPE_ACTIONS` entry without running dynamically provided Python or JavaScript.
4. The original production recipe writes authoritative map/actor/quest/environment content.
5. The ten-layer game system produces a second source tile edit and a separately observed event response.
6. This book's director edits the same source map deterministically: author allegiance-facing interaction routes and grouping.
7. The editor appends a new `RPGEventPage` with two actually registered environmental signals, a cooldown and a typed runtime-action proposal.
8. If and only if the base recipe created new actors or quests, the director updates those owned new records, preserving the user's existing cast and chapter canon.
9. Host persistence writes the entire immutable candidate or rejects the whole transaction. No partial map/quest mutation is committed.
10. Original Godot 4 expedition export consumes tile geometry, passable route links, authored NPC placements and native quest-stage data.
11. In runtime, environmental event evaluation uses measured observations; noncommutative effects still require the authorized game engine.

### Gameplay direction and audiovisual design

**Scene design purpose:** Cities, infrastructure, dungeon and architecture layouts. **Spatial production purpose:** Author allegiance-facing interaction routes and grouping. **Observation contract:** Reputation and quest world observations.

Traversable floor geometry, collision proof and interior routing. No published Godot runtime confirmation is claimed merely because the authoring output exists. This director's authored event and path geometry are a foundation for subsequent animation, dialog staging, original audio, navigation and gameplay runtime decisions.

### Data, safety and determinism

- Accept only declared bounded JSON parameters, valid source-layer coordinates, valid palette indices and an explicit deterministic seed.
- Use the existing immutable `StudioProject` as the sole game-source owner and original `game/editor/frontier_studio.json` as the project document.
- Resolve names arithmetically through immutable source and director indices; unknown action names fail closed.
- All new event identities derive from exact command SHA-256 plus a bounded `instance_id`, preventing overlong names and collisions.
- Reject duplicate authored event, chapter or cast IDs; never discard or silently replace user-created canon.
- Existing source actors and quests are not repositioned: directed stage edits apply only to content created during the current recipe.
- Persist via tenant-scoped authorized version compare-and-set; record before/after source hashes for traceability.
- Sensor observations are provided by the game runtime; the editor never fabricates environmental facts or runs an unauthorized action.
- Native physics parity, IP clearance and device performance remain separate acceptance requirements.

### Domain-specific functional acceptance checklist

1. Resolve and execute one of all 50 original structure source producers.
2. Resolve exactly nine treatment variants for that producer.
3. Resolve exactly ten gameplay-layer variants for this director.
4. Verify the director `faction_reactions` adds actual tile changes and a typed event page.
5. Confirm reputation and quest world observations use values observed by native gameplay rather than invented readings.
6. Verify the output source digest differs from the input digest.
7. Verify the same seed, operation and original source replay to an identical digest.
8. Verify a second unique instance_id can coexist with the first.
9. Verify repeating an existing instance_id fails without losing previous content.
10. Verify all existing actor poses and native quest stages remain unchanged.
11. Verify newly created actor placements, when present, reflect director staging.
12. Verify newly authored quests, when present, have reachable first and terminal stages.
13. Verify event-page action categories match the canonical RPG evaluator registry.
14. Verify client discovery pages never return more than 64 operations.
15. Verify long operation identifiers satisfy REST input constraints.
16. Verify preview cannot commit to the canonical project.
17. Verify committed source survives the typed JSON project roundtrip.
18. Verify native Godot terrain and expedition path compilation uses the changed source.
19. Verify actual on-device gameplay mechanics and collision before release.
20. Verify original creative ownership and no copyrighted source asset reuse.

**Sign-off:** Source implementation and documentation committed to PR #4200; exact-head CI, playable native Godot E2E and release-rights checks remain authoritative. No claim of independent completed games is made.

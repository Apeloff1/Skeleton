# Book 031 of 100 — POPULATION: Tactical zone staging

**Implementation:** tactical_zones over population · **PR:** #4200 · **Audience:** game director, Jeeves editor, original-world production, native Godot integrator.

## Mission and real production capability

Character populations, civilian crowds, creatures and tactical groups. The director authors cover perimeters and new cast formation layouts via genuine `StudioProject` mutations. Stable actor pose/event binding and non-destructive encounter staging. This is one of **90 director/domain technical books** alongside the previous ten original-domain volumes. Together they form 100 technical volumes across ten world-production domains.

The count represents **4,500 distinct composition workflows for this director/domain** (50 validated source archetypes × nine treatments × ten gameplay systems). Each executes the underlying source producer, one gameplay-layer tile/event transform, and a tactical_zones tile/event director. It is not a claim of 4,500 independent game engines or finished commercial games.

## Exact authoritative source archetypes

These fifty identifiers originate from the real `skeleton/forge/game_frontier_studio_encounter_factory.py` implementation:

| # | Existing executable blueprint | Representative exact composed command |
|---:|---|---|
| 1 | `encounter_village_crowd` | `direct_population_village_crowd__waterways___wayfinding____tactical_zones` |
| 2 | `encounter_market_vendors` | `direct_population_market_vendors__waterways___wayfinding____tactical_zones` |
| 3 | `encounter_tavern_guests` | `direct_population_tavern_guests__waterways___wayfinding____tactical_zones` |
| 4 | `encounter_festival_parade` | `direct_population_festival_parade__waterways___wayfinding____tactical_zones` |
| 5 | `encounter_harbor_workers` | `direct_population_harbor_workers__waterways___wayfinding____tactical_zones` |
| 6 | `encounter_farm_hands` | `direct_population_farm_hands__waterways___wayfinding____tactical_zones` |
| 7 | `encounter_caravan_merchants` | `direct_population_caravan_merchants__waterways___wayfinding____tactical_zones` |
| 8 | `encounter_city_patrol` | `direct_population_city_patrol__waterways___wayfinding____tactical_zones` |
| 9 | `encounter_castle_guards` | `direct_population_castle_guards__waterways___wayfinding____tactical_zones` |
| 10 | `encounter_royal_court` | `direct_population_royal_court__waterways___wayfinding____tactical_zones` |
| 11 | `encounter_wolf_pack` | `direct_population_wolf_pack__waterways___wayfinding____tactical_zones` |
| 12 | `encounter_deer_herd` | `direct_population_deer_herd__waterways___wayfinding____tactical_zones` |
| 13 | `encounter_bird_flock` | `direct_population_bird_flock__waterways___wayfinding____tactical_zones` |
| 14 | `encounter_fish_school` | `direct_population_fish_school__waterways___wayfinding____tactical_zones` |
| 15 | `encounter_insect_swarm` | `direct_population_insect_swarm__waterways___wayfinding____tactical_zones` |
| 16 | `encounter_horse_stampede` | `direct_population_horse_stampede__waterways___wayfinding____tactical_zones` |
| 17 | `encounter_bear_den` | `direct_population_bear_den__waterways___wayfinding____tactical_zones` |
| 18 | `encounter_predator_ring` | `direct_population_predator_ring__waterways___wayfinding____tactical_zones` |
| 19 | `encounter_migratory_line` | `direct_population_migratory_line__waterways___wayfinding____tactical_zones` |
| 20 | `encounter_turtle_nesting` | `direct_population_turtle_nesting__waterways___wayfinding____tactical_zones` |
| 21 | `encounter_squad_wedge` | `direct_population_squad_wedge__waterways___wayfinding____tactical_zones` |
| 22 | `encounter_siege_lines` | `direct_population_siege_lines__waterways___wayfinding____tactical_zones` |
| 23 | `encounter_archer_wall` | `direct_population_archer_wall__waterways___wayfinding____tactical_zones` |
| 24 | `encounter_shield_circle` | `direct_population_shield_circle__waterways___wayfinding____tactical_zones` |
| 25 | `encounter_cavalry_charge` | `direct_population_cavalry_charge__waterways___wayfinding____tactical_zones` |
| 26 | `encounter_ambush_arcs` | `direct_population_ambush_arcs__waterways___wayfinding____tactical_zones` |
| 27 | `encounter_flanking_pincer` | `direct_population_flanking_pincer__waterways___wayfinding____tactical_zones` |
| 28 | `encounter_rear_guard` | `direct_population_rear_guard__waterways___wayfinding____tactical_zones` |
| 29 | `encounter_scout_net` | `direct_population_scout_net__waterways___wayfinding____tactical_zones` |
| 30 | `encounter_boss_minions` | `direct_population_boss_minions__waterways___wayfinding____tactical_zones` |
| 31 | `encounter_sky_pirates` | `direct_population_sky_pirates__waterways___wayfinding____tactical_zones` |
| 32 | `encounter_airship_crew` | `direct_population_airship_crew__waterways___wayfinding____tactical_zones` |
| 33 | `encounter_cloud_drakes` | `direct_population_cloud_drakes__waterways___wayfinding____tactical_zones` |
| 34 | `encounter_floating_island_settlers` | `direct_population_floating_island_settlers__waterways___wayfinding____tactical_zones` |
| 35 | `encounter_wind_surfers` | `direct_population_wind_surfers__waterways___wayfinding____tactical_zones` |
| 36 | `encounter_tower_watchers` | `direct_population_tower_watchers__waterways___wayfinding____tactical_zones` |
| 37 | `encounter_balloon_riders` | `direct_population_balloon_riders__waterways___wayfinding____tactical_zones` |
| 38 | `encounter_glider_convoy` | `direct_population_glider_convoy__waterways___wayfinding____tactical_zones` |
| 39 | `encounter_sky_fishermen` | `direct_population_sky_fishermen__waterways___wayfinding____tactical_zones` |
| 40 | `encounter_aurora_procession` | `direct_population_aurora_procession__waterways___wayfinding____tactical_zones` |
| 41 | `encounter_dungeon_slimes` | `direct_population_dungeon_slimes__waterways___wayfinding____tactical_zones` |
| 42 | `encounter_cave_bats` | `direct_population_cave_bats__waterways___wayfinding____tactical_zones` |
| 43 | `encounter_crypt_guardians` | `direct_population_crypt_guardians__waterways___wayfinding____tactical_zones` |
| 44 | `encounter_labyrinth_wardens` | `direct_population_labyrinth_wardens__waterways___wayfinding____tactical_zones` |
| 45 | `encounter_treasure_mimics` | `direct_population_treasure_mimics__waterways___wayfinding____tactical_zones` |
| 46 | `encounter_portal_sentinels` | `direct_population_portal_sentinels__waterways___wayfinding____tactical_zones` |
| 47 | `encounter_ruin_explorers` | `direct_population_ruin_explorers__waterways___wayfinding____tactical_zones` |
| 48 | `encounter_mine_workers` | `direct_population_mine_workers__waterways___wayfinding____tactical_zones` |
| 49 | `encounter_fungal_foragers` | `direct_population_fungal_foragers__waterways___wayfinding____tactical_zones` |
| 50 | `encounter_underground_merchants` | `direct_population_underground_merchants__waterways___wayfinding____tactical_zones` |

## Nine spatial production treatments

1. **waterways:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
2. **highlands:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
3. **fortified:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
4. **nightfall:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
5. **festival:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
6. **circuit:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
7. **secrets:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
8. **skyreach:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.
9. **wilderness:** source-bound encounter authoring changes, seeded according to the selected archetype; its geometry, actor poses, quest DAG branches or environmental page inputs remain editable. In this population book, the `tactical_zones` pass follows that transformation and adds further authored world/gameplay data.

## Game-layer contracts and native acceptance

### Game layer 1: `wayfinding`

Purpose: Connect traversable central and secondary corridors. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Compass/fog proposals. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 2: `seasons`

Purpose: Retile winter/spring bands and authored climate transition. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Ground ice / temperature lighting. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 3: `destructibles`

Purpose: Lay breakable cover props as authored collision-adjacent tile masks. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Impact / structure-integrity action proposal. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 4: `weather`

Purpose: Provide shelter and weather-appropriate routes. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Wind/rain weather transition. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 5: `combat`

Purpose: Shape tactical engagement perimeter and cover. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Observed contact / party combat proposal. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 6: `commerce`

Purpose: Write traffic and service lanes. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Reputation/progress merchant access. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 7: `stealth`

Purpose: Build concealed alternate routes and cover. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Occlusion/daylight stealth flag. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 8: `verticality`

Purpose: Write sky-platform ring and shift newly created cast altitude. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Updraft/altitude lift proposal. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.

### Game layer 9: `migration`

Purpose: Create wildlife corridors with new cast redistribution. Here in **population**, the action first authors **character populations, civilian crowds, creatures and tactical groups** using an existing validated native world producer and the selected spatial treatment, then performs its own deterministic tile edit.

Runtime reading: Humidity/habitat foliage response. The gameplay proposal uses two canonical sensors; no proposed action may be applied as an unauthorized state mutation. Native collision, UI feedback, NPC navigation and audio/video presentation require platform-specific execution evidence. The tactical_zones overlay further creates **cover perimeters and new cast formation layouts**. This establishes distinct source state even when the input game already has matching tiles.

A test should compare the complete before/after source digest; inspect the actual tile region; then verify generated quests and actor poses where applicable. The native export should contain relevant changed layer/source files, while unrelated existing canon remains intact.


## Representative distinct composed commands

| # | Game production command | Visible, authored result |
|---:|---|---|
| 1 | `direct_population_village_crowd__waterways___wayfinding____tactical_zones` | Connect traversable central and secondary corridors; Compass/fog proposals |
| 2 | `direct_population_market_vendors__highlands___seasons____tactical_zones` | Retile winter/spring bands and authored climate transition; Ground ice / temperature lighting |
| 3 | `direct_population_tavern_guests__fortified___destructibles____tactical_zones` | Lay breakable cover props as authored collision-adjacent tile masks; Impact / structure-integrity action proposal |
| 4 | `direct_population_festival_parade__nightfall___weather____tactical_zones` | Provide shelter and weather-appropriate routes; Wind/rain weather transition |
| 5 | `direct_population_harbor_workers__festival___combat____tactical_zones` | Shape tactical engagement perimeter and cover; Observed contact / party combat proposal |
| 6 | `direct_population_farm_hands__circuit___commerce____tactical_zones` | Write traffic and service lanes; Reputation/progress merchant access |
| 7 | `direct_population_caravan_merchants__secrets___stealth____tactical_zones` | Build concealed alternate routes and cover; Occlusion/daylight stealth flag |
| 8 | `direct_population_city_patrol__skyreach___verticality____tactical_zones` | Write sky-platform ring and shift newly created cast altitude; Updraft/altitude lift proposal |
| 9 | `direct_population_castle_guards__wilderness___migration____tactical_zones` | Create wildlife corridors with new cast redistribution; Humidity/habitat foliage response |

## Source-to-native execution sequence

1. Read the game-learning project's authorized revision and SHA-256; use the existing app's editor, not a parallel workspace.
2. Inspect real map layers, palettes, prefab catalog, placed actor references and quest graph identifiers.
3. Search `/api/game-frontier-authoring/recipes?generation=directed&domain=population&director=tactical_zones&offset=0&limit=32` for an exact enumerated command.
4. Choose the native source producer, one of nine production treatments and one of ten game-system overlays.
5. Supply finite, bounded parameters, a deterministic integer seed and a unique stable instance ID. Do not submit arbitrary code or nested tools.
6. Execute the authoritative `edit_recipe` and `edit_expansion` source mutations under the existing typed Forge dispatcher.
7. Construct this book's director tiles and event page using the ten fixed, server-defined direction algorithms.
8. If new actors were produced, redirect **only those new instances**; do not overwrite the existing cast or its physics/index binding.
9. If a new quest was produced, append a distinct reachable side stage with an owned story objective and valid termination.
10. Recompute the complete source digest; on failure, abort the entire immutable batch and preserve the previous revision.
11. Commit through the existing authenticated compare-and-set source owner; retain receipt hashes and stable chapter metadata.
12. Export actual palette geometry, expedition traversal graph, source actors, native quests and observed environmental pages through the existing Godot source producer.
13. Qualify at least one real native playthrough before calling the design release-ready.

## Safety, long-run stability and IP ownership

- Recheck tactical path reachability and lines of sight.
- The authored RPG event is a typed proposal; no observed sensor reading, damage outcome, currency purchase, ability, music asset or approval is fabricated by the editor.
- No existing actor or quest may silently change to make a new recipe fit; new story branches must be reachable and respect all source-stable IDs.
- The catalog is **virtual** and indexed arithmetically; startup must not materialize 450,000 names. Discovery is paginated to at most 64 server-described results.
- Projects keep an immutable source hash and authorized version. Repeated chapters use separate instance identifiers. Duplicate pages/quests are errors.
- Native collision, real-time combat, animated environmental FX, spatial sound and device-specific memory performance require separate engine validation.
- Original creative authorship is mandatory. Direct copyrighted art, sound, scenes or game assets may not be repurposed without the necessary rights.
- Production progress must be recorded via source evidence and an actual transformed project. A registered command name alone does not prove playable gameplay.

## Twenty measurable sign-off probes

1. All 50 source archetypes resolve to real editable content.
2. All nine spatial production treatments retain separate exact action names.
3. All ten gameplay systems produce an accepted nonempty plan.
4. This director appends an actual authored MapLayer edit.
5. This director appends an actual typed RPGEventPage.
6. Each event has two valid independent sensors and an allowed response.
7. No sensor facts are synthesized by the authoring compiler.
8. Original source digest differs from edited source digest.
9. Identical inputs yield identical changed source digests.
10. Unknown command names fail closed before mutation.
11. Malformed instance identifiers fail closed before persistence.
12. Two unique instances coexist without overriding event identifiers.
13. Repeated used instance IDs return a collision error.
14. Original actor IDs, poses and quest canon are preserved.
15. Newly placed actors preserve their authored interaction event target.
16. Newly authored quest side stages are reachable and terminal-safe.
17. Typed source JSON survives save/load without changing its digest.
18. Bounded search returns at most 64 records and stable offsets.
19. Native Godot output reflects actual changed tiles and links.
20. Real target-engine playthrough, security and IP rights are independently signed.

## Completion boundary

**Implemented:** source producer execution, ten-domain composition, nine treatment choices, ten gameplay layers and directed gameplay overlays, all within the original app. **Unverified until CI/native acceptance:** all target-device gameplay, 450,000 individual gameplay trials, combat/commerce runtime effects, animation/assets and multi-month endurance. See `docs/game_studio_50000/README.md` for the previous ten volumes and `skeleton/testing/test_game_frontier_studio_production_500000.py` for current source regression.

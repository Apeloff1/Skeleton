# Forge Studio: Second Batch of 50 Functional Tools (101–150)

## Delivery scope

This update adds **50 executable authoring functions** to the existing 100,
for **150 distinct canonical source-edit commands**. None of the 50 is an
assurance gate or conceptual proposal. Each command produces an immutable
`StudioProject` with changed tile, placement, quest or RPG event records.


### Procedural world / geometry

| Action | Concrete source mutation |
|---|---|
| `terrain_height_noise` | Seeded interpolated elevation threshold paints real tiles |
| `terrain_fractal` | Multi-octave coherent height-map bands |
| `terrain_ridge` | Directional Gaussian mountain spine |
| `terrain_islands` | Radial archipelago landmass mask with noise |
| `terrain_crater` | Raised circular rim with excavated center |
| `terrain_meander_river` | Sine-warped connected river channel |
| `terrain_lake` | Seeded elliptical lake shoreline |
| `terrain_coastline` | Tide-facing irregular coast band |
| `terrain_talus` | Iterative 4-neighbor tile slope relaxation |
| `terrain_dunes` | Rotatable sinusoidal dune ridges |
| `terrain_voronoi` | Seeded nearest-site terrain partition |
| `terrain_contours` | Alternating bands from coherent elevation noise |
| `terrain_floodplain` | Wide floodplain surrounding a narrower river |
| `terrain_cave_automata` | Deterministic cellular-automata cave carving |
| `terrain_room_dungeon` | Connected seeded room-and-corridor layout |
| `terrain_depth_maze` | Depth-first perfect-grid maze carving |
| `terrain_road_links` | Wide roads joining authored waypoints |
| `terrain_avoidance_path` | A* low-cost route around expensive tiles |
| `terrain_cliff_band` | Orientation-aware steep cliff strip |
| `terrain_biome_mosaic` | Moisture/temperature/elevation mosaic |

### Population and formations

| Action | Concrete source mutation |
|---|---|
| `formation_line` | Evenly spaced facing-aligned actors |
| `formation_arc` | Partial radial actor arc |
| `formation_ring` | Full actor ring |
| `formation_spiral` | Progressive-radius spiral assembly |
| `formation_wedge` | Triangular tactical actor wedge |
| `formation_stagger` | Offset-row staggered troops |
| `formation_jitter_grid` | Seeded irregular lattice population |
| `formation_scatter` | Uniform-in-disk random placements |
| `formation_poisson` | Rejection-sampled minimum-separation placement |
| `formation_waypoint_path` | Arc-length placement along authored XYZ path |
| `formation_perimeter` | Even distribution around rectangular enclosure |
| `actors_translate` | Translate selected live actors without changing index |
| `actors_rotate` | Rotate selected live actors and facing around pivot |
| `actors_mirror` | Mirror selected actor locations/facing |
| `actors_reassign_prefab` | Rebind selected instances to an authored prefab |

### Narrative and events

| Action | Concrete source mutation |
|---|---|
| `narrative_branch_pair` | Author two player-choice quest outcomes |
| `narrative_branch_multi` | Create two to eight quest-choice branches |
| `narrative_extend_chain` | Append a longform sequential quest path |
| `narrative_insert_stage` | Insert new objective into authored edge |
| `narrative_bypass_stage` | Splice out linear intermediate objective |
| `narrative_relabel_quest` | Rename quest and all referenced start events |
| `narrative_fork_quest` | Duplicate native quest into distinct narrative path |
| `narrative_merge_endings` | Merge multiple terminals into shared epilogue |
| `event_clone` | Duplicate source RPG event with independent identifier |
| `event_batch_retarget` | Retarget selected actual authored event actions |
| `event_batch_retrigger` | Change event activation conditions in bulk |
| `event_bind_quest` | Create interaction that starts an existing authored quest |
| `event_actor_dialogue_batch` | Author unique dialogue interactions for actors |
| `event_actor_audio_batch` | Author unique spatial audio interactions for actors |
| `event_actor_loot_batch` | Author unique item reward interactions for actors |

## Actual game and workflow integration

- The same `execute_authoring` and `apply_authoring_batch` transaction path
  used by the original 100 now executes these 50. Each batch includes
  per-step before/after content hashes and fails atomically on invalid edits.
- `backend/core/game_frontier_authoring.py` reuses the authenticated scoped
  project, current editor revision and atomic existing `save_editor` storage.
  No extra database, model runtime or source authority is introduced.
- `frontend/src/features/Jeeves/GameFrontierAuthoringPanel.tsx` shows all
  150 operations, organized by area. New operations have JSON parameter
  presets and can be previewed, committed, and built as a Godot candidate.
- `skeleton/forge/game_frontier_studio.py` now composes original expedition
  route gameplay, physics/quest/environment runtime and **native geometry**
  from the same source.
- `skeleton/forge/game_frontier_studio_terrain_runtime.py` emits
  `studio_terrain.gd` and `studio_terrain.json`, and connects a new Node3D
  renderer into the original `expedition.tscn`. Its MultiMesh places
  palette-derived colored blocks at authored X/Z and elevation.
- Native geometry draw count is capped at 8192 instances; when a source
  exceeds that budget, deterministic sparse visual LOD is used. Source
  layer data remains unchanged. **Visual geometry does not currently
  replace collision geometry or native terrain navigation.**
- Quest stage operations use the existing native quest graph parser, plus
  an iterative cycle check, to preserve playable stage identity, terminal
  reachability, exact event references and proper branching.

## End-to-end example via existing REST interface

1. Inspect `GET /api/game-frontier-authoring/projects/{project_id}` to
   obtain the current source digest and revision.
2. Preview a single step with `terrain_room_dungeon` and parameters
   `{"layer":"ground","x":0,"y":0,"width":16,"height":16,"floor":0,"wall":1,"seed":42,"rooms":8}`.
3. Commit by PATCH with the exact revision and source digest; the existing
   workspace stores the revised `game/editor/frontier_studio.json`.
4. Optionally author `formation_ring` for a real previously authored prefab.
   The placement array and compiled native expedition waypoints update.
5. Optionally author `narrative_branch_pair`; the branch survives the
   typed JSON roundtrip and native gameplay quest compilation.
6. Export through `/api/game-frontier-authoring/projects/{project_id}/build/export`.
   The canonical project revision records runnable Godot 4 source,
   including 3D tile rendering and existing gameplay scripts.

## L00–L13 owner and production notes

- **L00:** canonical Forge Studio owns original authored content.
- **L01:** edit source -> typed Project validation -> existing CAS persistence
  -> world compiler -> native engine.
- **L02:** exactly 50 additional named operations with explicit input types,
  bounds and deterministic effects.
- **L03:** existing host authorization and project/tenant ownership enforced.
- **L04:** actor layouts and terrain generation never bypass the Studio compiler.
- **L05:** immutable project editing, versioned workspace save and history.
- **L06:** bounded tiles, counts, seeds, coordinates and source JSON; no file IO
  in model commands.
- **L07:** invalid operation, source conflict, graph cycle or 3D budget aborts
  edit without source mutation.
- **L08:** source SHA-256 and changed content are visible and auditable.
- **L09:** standard tile 256x256 source bounds and 8192 native visual instances.
- **L10:** additive operations under existing UI, API and ownership.
- **L11:** 50 individual functional state-mutation tests, seeded replay,
  spatial separation, quest composition and native terrain export.
- **L12:** host versioned project history controls restoring prior snapshots.
- **L13:** candidate code and synthetic functional tests do not establish
  measured target-platform game performance, collision/navigation parity,
  actual live Godot execution or legal release approval.

## Focused acceptance

```sh
python -m compileall -q skeleton/forge/game_frontier_studio*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q --noconftest \
  skeleton/testing/test_game_frontier_studio_authoring_next50.py
```

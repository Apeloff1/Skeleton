# Forge Studio: 50 Executable Game-Authoring Operations

## Delivered product capability

This implementation extends the **existing canonical** Forge Studio
`StudioProject` source model. All 50 commands perform actual immutable
mutations of authored project content. They are **not quality gates, labels,
feature flags, planned milestones or simulated API success responses**.

A game creator can paint and transform actual tile maps, expand layers and
palettes, place source-linked objects, author action pages, create and evolve
playable native quest branches, edit soundscape cue ordering, and compile the
result through the already-existing original expedition and Godot 4 emitters.

### Map, tile, layer, palette and clipboard operations (25)

| Action | Executed behavior |
|---|---|
| tile_set | Paint one tile at a bounded map coordinate |
| rect_fill | Fill a bounded rectangular region |
| line_draw | Rasterize an integer Bresenham line |
| ellipse_fill | Fill pixels within an authored ellipse |
| flood_fill | Connected four-neighbor fill, each cell once |
| replace_tile | Replace all occurrences of one palette index |
| checker_fill | Draw a two-tile alternating checkerboard |
| stamp | Apply tile brush; -1 means transparent/unchanged |
| region_paste | Paste exact tile buffer including erased cells |
| shift_layer | Translate map with optional explicit wraparound |
| flip_horizontal | Mirror tile pixels across the vertical axis |
| flip_vertical | Mirror tile pixels across the horizontal axis |
| rotate_90 | Rotate map 90° in chosen direction and swap dimensions |
| layer_add | Create new typed map layer with independent palette |
| layer_remove | Delete layer without allowing empty projects |
| layer_duplicate | Copy a layer under a new source identity |
| layer_reorder | Change layer compositing sequence |
| layer_elevation | Adjust source-authored vertical position |
| palette_add | Extend palette with an original tile identifier |
| palette_replace | Rename one palette identifier |
| palette_swap | Exchange palette entries and remap references |
| palette_remove | Remove unused palette entry and compact indices |
| layer_resize | Resize map with chosen fill and preserve overlap |
| layer_crop | Crop valid source rectangle into independent map |
| layer_clear | Erase all authored tile pixels in one layer |

### Prefab, actor, event, quest and soundtrack operations (25)

| Action | Executed behavior |
|---|---|
| prefab_add | Add typed content-hashed, era-bound game prefab |
| prefab_remove | Remove unplaced source prefab only |
| prefab_clone | Duplicate prefab with new identity |
| prefab_retarget | Update authored source asset digest |
| prefab_interaction | Switch playable interaction type |
| placement_add | Place real prefab with 3D pose |
| placement_remove | Delete actor; refuse unsafe native-index shifts |
| placement_move | Move existing actor in 3D |
| placement_rotate | Rotate actor facing modulo 360° |
| placement_duplicate | Duplicate actor with XYZ translation |
| placement_mirror | Mirror actor pose about x/y world axis |
| placement_grid | Place bounded array of game prefabs in world |
| event_add | Create executable RPG event declaration |
| event_remove | Delete unbound authored event |
| event_condition | Set typed boolean condition and flag |
| event_action | Change existing event action, target and value |
| event_trigger | Change event to supported engine trigger |
| quest_add | Create a valid native quest with playable objective |
| quest_remove | Delete quest not referenced by authored start event |
| quest_stage_append | Link existing stage to a newly authored stage |
| quest_objective | Rewrite an existing stage objective |
| quest_title | Retitle existing source quest |
| soundtrack_add | Add an original named soundscape cue |
| soundtrack_remove | Remove an existing cue |
| soundtrack_reorder | Move cue in authored playback order |

## Actual edit semantics

`execute_authoring(project, action, parameters)` calls the implementation
that changes the typed project. `apply_authoring_batch(project, steps)`
executes up to 64 changes as a copy-on-write transaction: failure leaves the
original object unmodified. Each step includes a source and result hash, with
a complete batch receipt. `authored_tile_region` returns real tile pixels
for the viewport clipboard and pasting.

The existing `StudioProject.__post_init__` immediately rechecks invariants
on every new typed result, including matching prefabs, native zone/field
references and reachable native quest graphs. Unsupported, out-of-bounds,
non-finite or unsafe edits raise `StudioError`; nothing is persisted.

## Jeeves host integration

The trusted owner attaches
`studio_authoring_handlers(project_loaders, commit_project=..., game_profiles=...,
export_root=...)`. It produces these existing ToolRegistry operations:

- `game.studio.author.inspect`: real project counts, layer occupancy and digest.
- `game.studio.author.copy`: exact authored clipboard pixels.
- `game.studio.author.preview`: dry-run real changes with receipt and new summary.
- `game.studio.author.edit`: **persist** edits through host-owned atomic
  compare-and-set callback and verify committed source by rereading it.
- `game.studio.author.compile`: compile deterministic source manifest.
- `game.studio.author.game`: produce a real deterministic, route-playtested
  expedition from canonical authored source and host-chosen generation profile.
- `game.studio.author.export`: **write** actual Godot project files into a
  new, safe, host-owned folder using existing native exporter with no overwrite.

No tool is automatically granted permission; the existing
`register_studio_tools` exact-command authorizer remains mandatory.
No model may invent a source repository or turn candidate data into release
authority. Native Godot output is an executable candidate, not evidence of
an independently executed GPU playthrough.

## L00–L13 engineering handoff

- **L00:** Forge Studio remains canonical owner; no extra runtime root.
- **L01:** source project -> immutable changes -> host CAS -> Forge compiler.
- **L02:** 50 stable operations with typed parameter and result contracts.
- **L03:** host authorizer controls each operation and persistent write.
- **L04:** preview/edit/compile/game/export run as explicit operations.
- **L05:** host versioned project store is the only mutable authority.
- **L06:** bounded payloads, identifiers, coordinates and safe export paths.
- **L07:** reject invalid mutations and concurrent CAS; no partial batch writes.
- **L08:** digests, source counts, resulting project receipt and generational logs.
- **L09:** 64-step bound, 256×256 layers, bounded grid instances and responses.
- **L10:** optional host attachment leaves all existing Studio tools compatible.
- **L11:** functional state-change regressions per action, rollback, CAS and export.
- **L12:** detach handler or revert edit using the host's canonical versions.
- **L13:** native acceptance needs real Godot and device evidence independently.

## Validation

The focused game workflow compiles the new editor modules and runs
`skeleton/testing/test_game_frontier_studio_authoring.py` after the source
implementation is complete. Real editor results are compared to their typed
post-edit state, not merely counted by their operation name.

# Epic Native Terrain: Fair 8,192-Instance Godot Visual LOD

## Engineering problem corrected

The original Godot `studio_terrain.gd` uses a bounded `MultiMeshInstance3D` renderer to display source-authored terrain tiles. Its Python source exporter previously scanned layers sequentially: whichever early dense layer reached 8,192 rendered cells first consumed the entire budget. Later original-game regions—including floating islands, subterranean story worlds, astronomical stages, second chapters and parallel planes—could silently disappear from the actual visual export.

This milestone **changes the native exporter**, rather than merely adding a checklist.

## Actual source implementation

`skeleton/forge/game_frontier_studio_epic_lod.py` performs three reproducible procedures:

1. Read the original `StudioProject.layers` and count exactly which map cells are real nonempty source tiles. All 128 allowed layer IDs and palettes retain original ownership and order.
2. When the total is at most 8,192, preserve the original tile data losslessly. For denser material, guarantee at least one visible instance in every nonempty source layer. Allocate remaining slots using a deterministic capped square-root weighting across source-layer sizes. Small but narratively essential subworlds must not be starved.
3. Within each layer, choose deterministic representatives spread across the entire source rectangle. Use centered spatial block samples and global quantile selection; fill any residual quota only from existing nonempty original coordinates. Original empty tiles stay empty. Tile IDs and source coordinates never change.

`skeleton/forge/game_frontier_studio_terrain_runtime.py` now consumes those allocations before exporting the unchanged fixed Godot 4 render script and the original `game/frontier/studio_terrain.json` source file. The runtime still draws actual source positions with their actual palette-derived material and elevation in a `MultiMesh` instance under the existing expedition scene root.

## Bounded physical example

Eight densely authored 64×64 source layers contain 32,768 nonempty cells. The exporter now provides **1,024 instances per layer**, preserving all eight instead of showing only the first two. It retains every layer's original 4,096 source coordinates with nonselected visual locations represented by blank entries in the sparse render grid.

The renderer remains capped at **8,192 visual instances total**, independent of the number of catalogued source-operation combinations. There is no 50-trillion array allocation.

## Native evidence

The output metadata contains `source_layer_count`, `rendered_layer_count`, `source_cells`, `rendered_cells`, `visual_instance_budget`, `lod_ratio`, `lod_strategy` for each layer, `all_nonempty_layers_represented` and the canonical `studio_sha256`.

`skeleton/testing/test_game_frontier_studio_epic_lod.py` verifies exact quota allocation, nonstarvation with 128 regions, deterministic spatial coverage, strict source tile material preservation, sparse/blank layers, lossless small maps, valid Godot scene attachment and no overwrite of existing terrain files.

## Important physics, ownership and fidelity constraints

This changes **visible generated terrain** in the native Godot candidate, not the source gameplay collision map or engine-owned path movement. It does not introduce per-frame streaming, terrain collisions, high-end animated foliage, physically correct water, or completed 3D world AI by itself. Source navigation remains controlled by the original game expedition and route assurance; physics/gameplay evidence requires real Godot execution. Any later runtime LOD streaming must preserve this versioned source digest and retain a separately verified collision map.

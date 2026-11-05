# Scene tiles: collision-aware playable scene movement

`python -m skeleton scene-tiles demo` plays the original Lantern Hollow
grid: walk to an authored brass key, collect it on the correct tile, traverse
the locked gate, then reach the sanctuary. An alternate sinkhole route is a
real failure ending. The canonical scene runtime owns pickups, locked exits,
save ancestry and endings; this adapter adds bounded 16x16 geometry.

Use `simulate --source-json JSON --actions-json JSON` to play a custom
authored tile world. `resume --session-json JSON --actions-json JSON`
continues a verified checkpoint. `verify`, `export`, `import` replay and
round-trip portable source-bound saves.

Every tile map must cover one canonical scene. Walls and interactions must
not overlap; every pickup and exit must be physically reachable from the
scene spawn. Movement cannot cross walls or bounds, and pickup/exit actions
require exact player coordinates. A rejected action preserves the old save.

Focused validation:

```sh
python -m pytest skeleton/testing/test_scene_tile_walk.py -q
python -m skeleton scene-tiles demo
```

Replay digests detect corruption, not author identity. Exact-head CI, device
qualification and release review remain mandatory.

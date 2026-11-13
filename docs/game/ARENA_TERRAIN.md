# Deterministic original tactical terrain

`python -m skeleton arena-terrain demo` generates a playable original
Lantern Harbor tactical grid with deterministic seeded obstacles. The
source is validated by the existing canonical tactical arena normalizer.
An explicitly carved corridor guarantees a legal walkable actor-to-actor
route; a BFS path receipt proves connectivity without claiming an AI victory.

```sh
python -m skeleton arena-terrain demo
python -m skeleton arena-terrain generate --generator-json '<JSON>'
python -m skeleton arena-terrain verify --terrain-json '<JSON>'
python -m skeleton arena-terrain preview --terrain-json '<JSON>'
python -m pytest skeleton/testing/test_arena_terrain.py -q
```

Parameters are seed, world/arena IDs, dimensions, wall density and turn
budget. The generator uses bounded integer xorshift and a canonical wall
list, never network randomness. Dimensions are 4..32 by 3..32, density
0..40%, seed 0..2147483647 and walls at most 512. Receipt verification
re-generates every wall, actor placement, source digest and route. Preview
runs the real canonical tactical autoplay and exposes its actual outcome
without promising victory. Digests detect corruption, not trusted author
identity; this is authored geometry, not rendered sprites or native 3D.

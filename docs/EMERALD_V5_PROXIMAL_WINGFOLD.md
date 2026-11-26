# V5 Pathfinder + Archivist: measured proximal wing clearance candidates

Approved art direction: retained `Emerald Dragon Evolution Sanctuary.png`. This branch is source-bound repair of the two larger **weighted V4** models, not a redesign of the original Hoarder. Candidate rotations are fixed per source clip: -0.30 radians about local Y on the two shoulder joints (skin indices 68/80), +0.18 radians about local Z on the terminal flight fingers (79/91). It appends 1,520 exact independent rotation streams across the 380 original motion clips per form. It does **not** change the 381st growth clip or the original embedded geometry, skin weights, UVs, textures and materials.

| Measured evidence | Pathfinder | Archivist |
| --- | ---: | ---: |
| Original V4 wing-pair idle intersections | 563 | 657 |
| Actual V5 model bytes | 114,687,832 | 114,810,480 |
| V5 SHA-256 | `80a98c198f5d8a6e101b571a9def6869904df4dfb0e5d90cba33f8890de9112f` | `569fdf85be64705b857a43e2491b62ae6970fe90739c1050ffb49494da642b27` |
| Original noncorrected tracks retained | 42,776 | 42,776 |
| Independent exported-pose samples checked | 7 | 7 |
| Sampled collisions across 7 region pairs | 0 | 0 |
| Sampled near-margin triangle pairs | 0 | 0 |
| Idle sampled strain p95 change | +0.001396 | +0.001248 |

The geometry classifier covers 269,919 selected high-risk triangles of 719,312; **449,393 remain outside its classification**. Seven discrete poses across idle, cuddle, takeoff, orbit and landing are **not continuous collision detection**. Animations and growth interpolation intervals, optional equipment and cloth, other body and wing surface contacts, Unreal and hardware remain independently held. The sampled strain metric measures 12,000 deterministic triangle edges at one idle pose, not all motions.

## Exact reproduction and verification

Extract the unchanged pinned V4 GLB into an operator-controlled folder. With Python, NumPy, the included source scripts and enough free scratch space:

```sh
python scripts/emerald_v5_proximal_wingfold.py pathfinder --source /v4/pathfinder.glb --out /new/pathfinder.glb --receipt /new/pathfinder-build.json
python scripts/verify_emerald_v5_proximal.py pathfinder --source /v4/pathfinder.glb --candidate /new/pathfinder.glb

python scripts/emerald_v5_proximal_wingfold.py archivist --source /v4/archivist.glb --out /new/archivist.glb --receipt /new/archivist-build.json
python scripts/verify_emerald_v5_proximal.py archivist --source /v4/archivist.glb --candidate /new/archivist.glb
```

The independent verifier checks exact source and output SHA-256, original binary prefix, all 1,520 corrected channels, identical non-target channel declarations, growth-clip identity and all original mesh/skin/material records. A mismatched candidate is refused. Stage packages include the actual corrected model, proof receipts, measured sampled-contact scripts and software-verification sources.

The eight binary transport pieces are in `assets/emerald/evolution-v5/proximal-wingfold-publication.json`. To reassemble exact local parts into a new file or publish into the two explicit review-only payload branches using a trusted, authenticated Git checkout:

```sh
python scripts/verify_emerald_v5_proximal_publication.py assemble --stage pathfinder --parts /verified/slices --output /new/pathfinder.glb
python scripts/verify_emerald_v5_proximal_publication.py publish --stage pathfinder --parts /verified/slices --repo /trusted/Skeleton
```

Replace the stage with `archivist` for the second model. Remote publication succeeds only after real raw Git blobs and exact head SHAs are confirmed. The source files themselves are not the binary data; their CI passing does not count as remote upload.

**Hold:** No automatic model selection, optional equipment activation, merge or release. Artistic approval and truly hand-painted artwork, elimination of baked adult equipment, full continuous skinned-mesh CCD, physically qualified Unreal, D3D12/RTX/device capture, performance and release provenance remain outstanding. Do not repin or alter the original Hoarder.

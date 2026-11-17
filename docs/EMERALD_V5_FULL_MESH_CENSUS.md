# Emerald V5 full-mesh anatomical census — measured coverage, not collision clearance

Seven exact-SHA original-donor models were evaluated on 17 November 2026: all five V4 forms plus exported Pathfinder and Archivist V5. Each preserves 365,997 vertices, 719,312 triangles, 108 joints, and 381 clips. The original Hoarder is unchanged.

The original seven high-risk contact regions classified **269,919** triangles. The new exact-GLB census assigns **719,228** triangles by two-of-three dominant bone majority, leaving **84** with three different anatomical categories. This classifies 449,309 more triangles; it **does not clear any more collision tests**.

| Region | Triangles |
|---|---:|
| Torso | 224,140 |
| Head | 44,618 |
| Forelegs | 20,728 |
| Hindlegs | 17,918 |
| Tail | 43,160 |
| Near primary wing | 0 |
| Far primary wing | 260 |
| Wing-mounted detail | 78 |
| Near flight wing | 144,912 |
| Far flight wing | 143,876 |
| Corrective joints | 79,538 |
| Three-way mixed | 84 |
| **Total** | **719,312** |

**Blended-skin risk:** 83,627 vertices receive at least 20% contribution from two or more anatomical cohorts; 171,165 triangles touch such vertices and 17,222 triangles span at least three significant cohorts. A clear majority assignment must not be interpreted as seam clearance. These figures were independently computed from the actual SHA-verified GLBs and are preserved in `assets/emerald/evolution-v5/anatomical-census-measured.json`.

## Reproduce the census

Provide the exact original GLB bytes in a trusted local folder. Python and NumPy are required; output must be an unused file in an existing directory.

```sh
python scripts/emerald_v5_anatomical_census.py --stage pathfinder --generation v5 --model /original/pathfinder.glb --output /new-evidence/pathfinder-census.json
python scripts/emerald_v5_anatomical_census.py --stage archivist --generation v5 --model /original/archivist.glb --output /new-evidence/archivist-census.json
python scripts/check_emerald_v5_anatomical_evidence.py
```

The resulting worklist explicitly leaves wing-to-torso, head, limbs, tail, corrective-rig seams, mounted details, and cross-category triangles **unqualified**. A pass in source-only CI only checks record consistency and hostile input rejection, not model bytes or continuous motion.

## Acceptance holds

Full bounded broad/narrow-phase contacts must be run across new cohorts; 171,165 blended-risk triangles need independent seam analysis, and *continuous* animation intervals need defensible deformation bounds rather than sampled timestamps. Optional equipment remains disabled. The original poster's visual fidelity, human-authored paint, removal of inherited adult detail, actual Unreal compilation, Windows/GPU physical RTX, final-head CI and release provenance are all unqualified. Neither this source branch nor its worklist authorizes adoption, merge or release.

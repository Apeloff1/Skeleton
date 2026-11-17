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


## Actual V5 posed broad-phase expansion

The archived reviewed `Tools/contact_audit.py` (exact SHA-256 `0333ec4e01f701554e6f62b443fc5b2283bb68e8a62aaf324760068cc7107d4f`, 23,471 bytes) was used on the independently SHA-verified Pathfinder and Archivist V5 GLBs. The new operator implementation requires **that exact tool source** instead of importing an unreviewed file. The model, tool and working head have separate custody.

At 7 sampled poses per stage and 19 anatomical pair types per pose, the conservative AABB lower-bound screen measured:

| Source-bound pair status | Instances |
| --- | ---: |
| Posed boxes separated by more than 8 mm | **76** |
| Overlapping posed boxes, exact triangle test required | **176** |
| Empty majority cohort, evidence missing | **14** |
| **Total** | **266** |

The 76 separations are valid only at the **specific sampled instants**. All 176 overlapping boxes remain unqualified; an overlap is **not** itself a triangle intersection. The 14 empty-group cases are unqualified rather than silently passed. The complete source-bound status matrix is in `assets/emerald/evolution-v5/expanded-sampled-bounds.json`; detailed per-pair AABB lower bounds can be regenerated using the exact operator source and models.

```sh
python scripts/emerald_v5_expanded_broadphase.py \
  --stage pathfinder \
  --model /verified/pathfinder.glb \
  --contact-tool /retained/source-and-contact-evidence/Tools/contact_audit.py \
  --out /new-evidence/pathfinder-aabb.json
python scripts/emerald_v5_expanded_broadphase.py \
  --stage archivist \
  --model /verified/archivist.glb \
  --contact-tool /retained/source-and-contact-evidence/Tools/contact_audit.py \
  --out /new-evidence/archivist-aabb.json
```

This broad-phase tool checks source pin, model topology and numerical limits, then writes a bounded sampled-pose report. Its success **does not assert** full-mesh triangle narrow-phase, arbitrary temporal intervals, stitched/weighted skin seam clearance, optional equipment, artist approval, Unreal compilation, physical RTX or launch readiness. Source-only CI checks synthetic geometry, evidence consistency and hostile input rejection; actual GLB execution remains external.

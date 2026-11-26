# Emerald V6: exact-tail repair and attachment seam provenance

This is a review-only correction for **Pathfinder** and **Archivist**. The full original Hoarder, five V4 evolution models, and both V5 models remain unchanged. The approved sanctuary poster is the artistic target, not artistic acceptance evidence.

## Confirmed source of the 551 reported contacts

A full indexed-face and source-bind comparison of three newly added anatomical pairings at ground-idle shows the same **551 contacts on both stages**:

| Pair | Contacts per original-source bind and idle pose | Exact source vertex-ID shared |
|---|---:|---:|
| Far primary wing ↔ torso | 338 | 338 |
| Wing-mounted detail ↔ torso | 206 | 206 |
| Tail ↔ hindlegs | 7 | 7 |
| **Total** | **551** | **551** |

All 551 share an original mesh vertex index and were already touching at bind pose. They are attachment-weld *candidates*, **not automatically safe contacts**: co-planar overlap, inverted area, self-crossing, other seams and constraints still require inspection. The earlier stage-specific wing-angle candidates did not create these 551 source-topology contacts.

## Motion-induced problem and tested solution

On the same exported V5 models, additional tail–hindleg contacts occur in orbit and landing. A +0.18-radian **local Y** quaternion postrotation at *tail_01*, skin joint index **34**, removes all non-welded contacts detected in the examined tail–hindleg region at nine samples per clip in both stages. Returning the correction to zero at clip boundaries leaves unresolved contact, so this candidate applies the same offset at all existing source keyframes of **orbit-01** and **landing-1**, with cross-clip transitions held for independent qualification.

This correction is **clip-specific**, not a global rest-pose or 380-animation change. V6 was exported from the exact V5 bytes and independently checked.

| Original-donor V6 asset | Bytes | SHA-256 |
|---|---:|---|
| Pathfinder V6 GLB | 114,693,124 | `20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063` |
| Archivist V6 GLB | 114,815,776 | `8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973` |

Each modifies exactly **2** original animation sampler outputs (169 orbit and 109 landing quaternion keys). Independent verification proves that the source embedded mesh/material/skin/texture and old animation binary prefix is unchanged, **44,511 other animation channels** are unchanged, the exact growth document and its bytes are unmodified, and all original 108 joints and 381 motion clips remain. The full model exports are provided separately; source-only CI does not replay those bytes.

## Actual exported model contact measurements

Nine evenly spaced times from 0 through 1 across both named clips and both models give **36 true skinned export poses** and **108 anatomical pair instances** for the three pairs above:

- **0 independent non-welded intersections**, down from **335 across the corresponding V5 sample instants**
- **19,836 occurrences of the original 551 shared-vertex attachment pairings**, not independent collisions
- **134,247 near-margin pair occurrences** across all poses (8 mm threshold), unresolved as clearance
- **No evidence** for unsampled motion intervals, other anatomical pairs or blended clip transitions

The condensed actual-source receipts are in `assets/emerald/evolution-v6/exported-contact-evidence.json`. The operator's complete per-pair reports and actual two GLB candidate binaries are in the delivered ZIP archives.

## Operator reproduction

```sh
python scripts/emerald_v6_tail_clearance.py pathfinder --input /verified/v5/pathfinder.glb --output /new/pathfinder.glb
python scripts/verify_emerald_v6_tail.py pathfinder --source /verified/v5/pathfinder.glb --candidate /new/pathfinder.glb
python scripts/emerald_v6_tail_clearance.py archivist --input /verified/v5/archivist.glb --output /new/archivist.glb
python scripts/verify_emerald_v6_tail.py archivist --source /verified/v5/archivist.glb --candidate /new/archivist.glb
```

The exporter rejects incorrect source bytes, unknown stages, non-unit or nonfinite quaternions, non-LINEAR target animation, repinning, unsafe destination reuse and output hash mismatches. The independent verifier rechecks the two correction streams and all untouched declarations.

## Remaining acceptance

Cross-clip slerp/crossfade with original Director runtime, true continuous motion bounds, the remaining anatomical pairs and 171,165 blended-risk faces, optional equipment, the fully artist-directed poster comparison, true human-painted textures, actual Unreal and D3D12 RTX hardware, verified remote binary delivery, exact-head CI and release provenance. Equipment stays disabled; model auto-adoption, merging and release are blocked.

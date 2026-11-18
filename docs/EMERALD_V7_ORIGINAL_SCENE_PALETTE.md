# Emerald V7 — independently verified original scene and skin palette

**Status: exact original-file audit, review-only.** This custody audit inspects the full original 114–115 MB Pathfinder and Archivist V7 GLBs within the previously supplied immutable ZIPs. It establishes the real skin/scene layout and corrects an earlier inaccurate claim that the *root bone* has a name containing spaces. The root is named `root`; the independent *mesh node* has that multiword name.

## Measured source bytes

| V7 form | ZIP SHA-256 | Complete GLB SHA-256 | GLB bytes |
|---|---|---|---:|
| Pathfinder | `1149a6991004954735a1aeab633aa604d7453cee5856349fc24d1ad8b614ec30` | `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade` | 114,696,520 |
| Archivist | `ae76924a439bc78368640680563e42ff3903fb2ae16c394347cc1cd697ffd1d6` | `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf` | 114,819,168 |

Both full GLBs were streamed, hashed and their internal JSON inspected independently on 18 November 2026. Neither file is auto-adopted or modified by this audit. Full ZIP sizes are 114,705,092 and 114,827,704 bytes respectively.

## Exact scene and rig census

- The glTF contains **109 nodes**, one skinned mesh, one skin, 108 skin joints and **381 animation clips** for each stage.
- The single active scene lists node IDs **0** and **92**. Node **0** is the skeleton root named `root`, with child joint 1.
- Node **92** is the single skin-bound mesh named `Emerald continuous reconstructed character`, with `mesh: 0` and `skin: 0`. It is **not** a bone and has no local transform or children.
- The exact skin palette is nodes **0–91 and 93–108**. The gap at 92 means the skeleton palette indices after node 91 **must not** be treated as raw glTF node IDs. The last node 108 is a corrective tail joint.
- Neither model contains explicit scale transforms on the 108 bones, which is required by the current independently verified quaternion/translation skin reconstruction.
- In both models, palette joint 34 maps to glTF node 34, the corrected `orbit-02` tail-root rotation accessor has **160 VEC4 float32 keys**, and the intended source yaw is +0.18 radians.

| Motion clip | Rotation tracks | Translation tracks | Total |
|---|---:|---:|---:|
| `ground-idle-1` | 97 | 17 | 114 |
| `takeoff-1` | 106 | 18 | 124 |
| `orbit-01` | 71 | 17 | 88 |
| `orbit-02` | 71 | 17 | 88 |
| `landing-1` | 105 | 18 | 123 |

The end-of-catalogue transition remains `growth-pathfinder-to-archivist` or `growth-archivist-to-hoarder` respectively.

## New source enforcement

`frontend/scripts/emerald-v7-three-mixer-trace.mjs` now enforces the source-bound scene and mesh/skin palette *before* constructing mixer bones, plus unit joint scales. Track bindings continue to use stable skin **palette** identifiers rather than ambiguous source node names. This protects both actual donor models and prevents accidental binding of mesh node 92 as a bone.

`scripts/verify_emerald_v7_scene_palette.py` is a **separate standard-library source auditor**. With `--archives`, it verifies exact ZIP bytes, safe ZIP members, complete GLB SHA, GLB header/BIN extent, full scene/skin mapping, original flight track census and tail accessor on both V7 models. Without `--archives`, it checks only the pinned receipt at `assets/emerald/evolution-v7/original-skin-palette-rechecked-20261118.json`; the output reports `actual_zip_bytes_replayed_in_this_source_only_step: false`, making synthetic/source-only CI distinguishable from actual full model custody.

The hostile fixture suite `scripts/test_emerald_v7_scene_palette.py` rejects a changed scene root, invented mesh identity, mesh node entering the skin palette, scale changes, missing growth, duplicated/misrouted animation tracks, fabricated source digests and false release/device assertions. A separate 381-clip/109-node synthetic fixture exercises the real Three parser without passing the whole-GLB SHA check.

## Operator reproduction

```sh
# Source-only evidence consistency:
python scripts/verify_emerald_v7_scene_palette.py

# Independent physical original ZIP and GLB source replay:
python scripts/verify_emerald_v7_scene_palette.py \
  --archives /trusted/emerald-v7-orbit02-delivery
```

A successful source-byte audit does **not** prove that the actual Three mixer has completed a 108-pose original-model replay. Original remote GitHub binary publication, all anatomical region collision checks, continuous-time CCD, arbitrary live browser playheads, optional equipment, human-approved poster anatomy and paint, native Unreal and physical RTX remain held. No install, merge or release is authorized.

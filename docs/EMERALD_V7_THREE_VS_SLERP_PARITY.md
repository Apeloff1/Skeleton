# Emerald V7 — real Three mixer versus exact source-SLERP parity

## Why this gate exists

The historical V7 108-pose screen applied joint-wise local quaternion SLERP and translation LERP to original glTF source channels. The newer operator drives the actual **Three.js 0.186.1 AnimationMixer**, and these two interpretations can diverge because of action crossfade scheduling, original bind-state contribution, channel omissions, loop phase, and interpolation differences. **Previous zero-contact counts cannot be transferred to a real mixer without checking the poses.**

This draft adds `scripts/compare_emerald_v7_three_source_parity.py` and integrates it directly into the two-model real-mixer operator.

## Byte-locked operation

Given one exact original V7 model and its actual Three joint trace, the comparator:

1. Recomputes the complete original model SHA-256 (Pathfinder `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade`, Archivist `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf`).
2. Validates the full 54-pose, six-route, nine-phase Three 0.186 source trace, its 108 joints, action weights, original donor, and active 0.22-second action playheads.
3. Revalidates **all five** original SHA-pinned contact and glTF-interpolation tool files before importing the reviewed source.
4. Independently samples the exact original animation accessors at the **actual Three reported outgoing and incoming playhead times**. It does not invent fresh clip phases or compare different parts of the motion.
5. Computes the historical approximate translation and quaternion SLERP at the recorded fade alpha, for all 108 joints in every pose.
6. Reports for each of the **54 poses** and **108 joints** the position and sign-invariant quaternion differences, largest offending joint index and tail-root joint 34 measurements. Quaternion `q` and `-q` are treated as the same physical rotation.

Fixed strict parity tolerances: **0.5 degrees maximum angle** and **0.005 meters maximum local translation** per joint. A source mismatch is retained in the report and returns failure instead of being silently labeled equivalent. The original model, clips, sculpture, materials and render pipeline are not modified.

### Individual operator measurement

```sh
python scripts/compare_emerald_v7_three_source_parity.py \
  --stage pathfinder \
  --model /trusted/models/pathfinder.glb \
  --trace /new/evidence/pathfinder-three-mixer.json \
  --source-tools /verified/five-reviewed-contact-tools \
  --output /new/evidence/pathfinder-three-vs-slerp.json
```

The corresponding Archivist command uses its own verified GLB, trace, and unused output path.

### Integrated real-model admission

`scripts/run_emerald_v7_real_three_qualification.py` now runs the parity comparator **after** its actual Three execution and **before** the expensive original triangle-contact analyzer. It independently checks parity's model and trace SHA, sample inventory and false approval flags. Any above-tolerance deviation prevents a positive sampled-only operator receipt; the detailed parity result is held for review. Both stage receipts carry the parity report SHA, measured worst joint angle/translation errors and proof that the comparator subprocess actually ran.

## Claims explicitly not established

Source-only CI tests these equations against artificial identity, antipodal and tail-root poses. It **does not possess** the two complete original GLBs and therefore cannot assert actual original-model parity, collision, genuine browser loop phase or native GPU. This comparator does **not** perform collision detection: positive parity alone cannot demonstrate skinned-surface clearance. The previous 108/108 offline 0-contact result is historical approximate evidence, not a substitute for future measured real Three execution.

The complete two-stage operator still requires independently produced triangle-distance reports and emits `continuous_collision_qualified: false`, `all_anatomical_pairs_qualified: false`, `physical_rtx_verified: false` and `release_qualified: false`. Original Hoarder/installed assets, raw GitHub V7 payloads, artist approval, physical Unreal, optional equipment, merge and release remain held.

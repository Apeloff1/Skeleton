# Scholar wingfold r1 — original-donor experimental corrective model

This is a distinct **manual-only, opt-in** candidate of the Scholar level. It does not replace the V4 Scholar pin or the unchanged original Hoarder. It is based on the exact V4 source, SHA-256
`db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9`, retaining the original donor SHA
`c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a`.

## Actual finished asset and measurement

The original 112,509,064-byte V4 Scholar GLB had 100 wing-root membrane triangle intersections in the sampled idle pose. All were within the 25 mm centerline classification; none was distal. The controlled experiment rotated terminal wing-finger joints 79 and 91 by +0.18 radians in their local Z frames, producing zero sampled intersections in the corrected idle pose, with approximately 1,103 pairs within the 8 mm proximity margin.

The final **113,305,100-byte** corrected GLB has SHA-256
`3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877`.

It appends 760 new quaternion output accessors across the original 380 animation clips. Existing rotation accessors, original animation time arrays, mesh geometry, normals, UVs, skin weights, all materials and imagery, and the entire original binary prefix remain unchanged. The 381st growth clip is retained exactly.

The independent actual exported-byte audit checked 365,997 original-donor vertices, 719,312 triangles, 108 joints, 381 clips and the full prefix and 760 corrected quaternion arrays. The Scholar-to-Pathfinder growth endpoint difference remains 1.99701e-7 m. 12,000 sampled triangle edges showed p95 strain 0.0229562 before and 0.0246215 after; this is a small measured increase, not proof of acceptable artist quality or hardware animation.

Seven independently sampled poses (idle at 0%, 50%, 100%; cuddle, takeoff, orbit and landing at 50%) showed **zero intersecting pairs within the selected screened body/wing regions**. Residual proximity counts remained around 1,100 for folded idle and cuddle. The scanner excludes 449,393 unclassified triangles and leaves between-pose intervals, all growth morphs and optional equipment unqualified.

The corrected asset is available in the operator's separately verified `scholar-wingfold-r1.zip` and four exact binary parts. It is **not yet on GitHub**. The GitHub connector accepts repository text and Git blob data but cannot directly transfer these local large binary files. A separate draft carries exact metadata and intentionally fails actual-byte custody until a trusted operator publishes the four parts.

## Rebuild

With original `scholar.glb` V4 source from the verified package, a trusted Python environment with NumPy and ample free disk:

```sh
python scripts/patch_emerald_scholar_wingfold.py \
  --source /retained/scholar-v4.glb \
  --output /reviewed/scholar-corrected.glb \
  --report /reviewed/scholar-corrected-receipt.json \
  --radians 0.18
```

Validate the output SHA against the candidate pin, then independently run the true skinned triangle contact scanner against the corrected file. For binary publication through an authorized local Git checkout:

```sh
python scripts/publish_emerald_scholar_wingfold.py verify-bundle --bundle /reviewed/scholar-wingfold-r1.zip
python scripts/publish_emerald_scholar_wingfold.py publish --bundle /reviewed/scholar-wingfold-r1.zip
python scripts/publish_emerald_scholar_wingfold.py verify-tree --repo /clone/Skeleton
```

All Git push commands are forward-only to `assets/emerald-scholar-wingfold-r1-20261117` and do not merge or release.

## Explicit holds

- No source or receipt is sufficient to certify continuous all-triangle CCD, folded-wing root topology, 449,393 unclassified triangles, or actual equipment clearance.
- Full artist acceptance, handwritten texture and sculpt fidelity, approved-poster parity and folded-wing aesthetics remain pending.
- The original-donor full five-form update, native Unreal C++ and physical RTX/device qualification, correct release provenance and exact final-head CI remain independent.
- The local Atelier viewer may manually inspect/scrub this exact candidate; auto-animation is disabled at the UI *and* renderer. It is never selected by the level/XP logic.
- Do not change the original V4 Scholar pin or Hoarder SHA, enable equipment, merge or release.

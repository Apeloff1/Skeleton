# Scholar wing-fold V5 — audited correction, not automatically accepted

Stage: **Scholar**, levels 21–30. V4 input: 112,509,064 bytes, SHA-256 `db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9`. V5 corrected candidate: 113,305,100 bytes, SHA-256 `3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877`. Original full-density Hoarder donor remains `c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a`.

## Implemented correction

The two terminal flight-finger joints (skin indices 79 and 91) are locally postrotated +0.18 radians about Z across 380 original clips, appending **760** VEC4 quaternion streams. Source mesh, texture, skin and material bytes remain unchanged; no other keyframe channel changes and the 381st growth animation is identical. The independent verifier requires exact source and output SHA, original GLB binary prefix, preserved growth, exactly 760 corrections and identical non-target animation declarations. An invalid or partially written output is rejected and discarded.

The original source-bound contact audit examined 7 sampled poses across ground-idle, cuddle, takeoff, orbit and landing: 0 classified triangle intersections after correction, 1103–1106 near-margin pairs on idle, 1058 near-margin pairs on cuddle. Original idle p95 sampled strain 0.0229562 versus corrected 0.0246215, change +0.0016652. Of 719,312 triangles, 269,919 were classified in this high-risk screen and **449,393 were outside its coverage**. Six nonlinear intervals were not certified. This is not full continuous skinned-mesh CCD or artistic acceptance.

## Local exact rebuild

Use the original V4 GLB outside the repository, with Python and NumPy:

```sh
python scripts/emerald_v5_scholar_wingfold.py --source /verified/v4/scholar.glb --output /new-private/scholar.glb
python scripts/verify_emerald_v5_scholar.py --source /verified/v4/scholar.glb --candidate /new-private/scholar.glb --receipt /new-private/verified.json
```

The original corrected output is supplied separately in `scholar-wingfold-r1.zip`. Four exact 32 MiB-or-smaller binary parts and their digests are recorded in `assets/emerald/evolution-v5/scholar-wingfold-r1/publication-manifest.json`. Reassemble separately with:

```sh
python scripts/verify_emerald_v5_publication.py assemble --parts /verified/slices --output /new-private/scholar.glb
```

The draft requires all actual Git blobs before it can claim remote publication. **Source-only CI passing never proves binary upload or render safety.** Do not replace existing pinned V4 model or enable equipment automatically. An explicit later adoption PR with updated admission receipts, visual comparisons, wider motion sampling, independent physical renderer checks and artist approval is required.

### Residual holds

- Unclassified triangles, unsampled animation intervals, genuine skinned contact CCD and body/wing equipment clearance
- Full visual parity and genuinely hand-painted native textures
- Unreal compilation and hardware/D3D12 physical RTX tracing
- Exact-head complete repository checks, binary publication, device acceptance, security and release provenance

# Emerald V7 — original-binary Three mixer joint and clip binding census

The complete original Pathfinder and Archivist V7 full-density GLBs have an important structural distinction that the initial source tracer needed to handle correctly: **109 glTF nodes, but exactly 108 skin joints**. Node **92** is the excluded skinned mesh node; the corrective joint at glTF node **108** belongs to the 108-element skin palette. Animation channels target glTF **node indices**, not palette indices. The source-binary palette array is identical across the two V7 stages, and its canonical JSON SHA-256 is `75cb827128980e9253aea694efcb74636429ebc98310ab1c416f6ed378d8d647`.

The newly pinned manifest `assets/emerald/evolution-v7/original-three-binding-census.json` records the actual complete original GLB identities, JSON chunk lengths, skin palette SHA, five essential animation-track target ordering SHAs and exact float32 source durations. The original arrays were independently inspected from both SHA-pinned V7 delivery ZIPs; no geometry/art asset or active model pointer is changed.

## Actual source-backed clip census

| Original motion | Channels | Rotation | Translation | Source duration |
|---|---:|---:|---:|---:|
| ground-idle-1 | 114 | 97 | 17 | 5.915 s |
| takeoff-1 | 124 | 106 | 18 | 6.5 s |
| orbit-01 | 88 | 71 | 17 | 22.4 s |
| orbit-02 | 88 | 71 | 17 | 21.18 s |
| landing-1 | 123 | 105 | 18 | 7.2 s |

Durations are indicative rounded display values only; the manifest preserves the **exact accessor float32 maximum**. Target binding digests are calculated over UTF-8 `JSON.stringify([[gltfNodeIndex, target.path], ...])` in the unchanged original **channel order**. The `orbit-01` and corrected `orbit-02` target SHA arrays are intentionally identical because V7 corrected a quaternion stream, not the channel declarations.

## Independent preflight before full Three execution

`scripts/qualify_emerald_v7_original_three_bindings.py` is a *standard-library-only* original model auditor. It opens both complete GLBs with a nofollow file descriptor, verifies exact length/whole-file SHA-256, validates glTF 2 and JSON/BIN extents, rejects wrong donor/stage, and verifies the 109/108/mesh omission, 381-clip catalogue, exact palette SHA, all five clip target fingerprints, source rotation/translation counts, positive source times and interpolation. It refuses unintended retargeting or source timebase changes. The original V7 SHA is rechecked again before and after the full operator work.

```sh
python scripts/qualify_emerald_v7_original_three_bindings.py \
  --models /trusted/emerald-v7-original-models
```

The full operator `scripts/run_emerald_v7_real_three_qualification.py` now invokes this preflight for both stages **before** Node starts. It retains its own prior and post-run complete model SHA validation, source script hashes, exact reviewed geometry tool hashes, Three runtime file hashes, and the previously added checkpoint remeasurement requirement. A positive result remains conditional on executing both actual Three model traces and both full reviewed triangle analysis passes with no new contacts.

## Explicit evidence status

The manifest fingerprints are **source structure**, not actual Three mixer execution. The standalone and registered CI test suites construct tiny synthetic GLBs with mocked SHA pins and hostile node/clip mutations; they do **not** mount the two original 114–115 MB GLBs. A passing source test cannot certify renderer fidelity, real browser playheads, continuous-time CCD, all anatomical pair types, near-margin/weld clearances, artist poster likeness, hand-painted textures, Unreal compilation, RTX GPU, publication of eight original Git transport parts, merge or release.

Both V7 stages remain quarantined; the existing Hoarder and installed Emerald model pins are untouched. The source-enabled `source_operator_sampled_only_qualified` receipt is reserved for a real completed two-model operator run and must remain false/unavailable when source execution is incomplete.

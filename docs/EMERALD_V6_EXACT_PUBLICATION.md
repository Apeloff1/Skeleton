# Emerald V6 original-donor GLB publication — split, review-only

The actual Pathfinder and Archivist V6 correction binaries are **229,508,900 bytes total**, split into **eight original raw Git chunks**, each at most 32 MiB. Exact size, whole-file and every chunk SHA-256 is independently measured and pinned in `assets/emerald/evolution-v6/publication-manifest.json`. The original V5 source hashes and Hoarder donor identity are unchanged.

| Payload draft | Model size | Exact SHA-256 |
|---|---:|---|
| Pathfinder V6 | 114,693,124 bytes | `20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063` |
| Archivist V6 | 114,815,776 bytes | `8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973` |

Both models are real generated GLBs, separately downloadable in `pathfinder-v6-tail-clearance.zip` and `archivist-v6-tail-clearance.zip`. Each ZIP includes a full original V6 model, exporter, independent verifier and measured contact evidence.

## Authenticated draft-only Git delivery

From a **trusted existing authenticated checkout** of Apeloff1/Skeleton, place the two unchanged ZIP files in an operator-controlled directory and run:

```sh
python scripts/publish_emerald_v6_tail.py verify-bundles --bundles /trusted/emerald-v6-archives
python scripts/publish_emerald_v6_tail.py publish --bundles /trusted/emerald-v6-archives --repo /trusted/Skeleton
python scripts/publish_emerald_v6_tail.py reconstruct --destination /new/verified-emerald-v6 --repo /trusted/Skeleton
```

`publish` performs only bounded existing review-branch raw Git object inserts and **non-force fast-forward** commits, uses no checkout filters or LFS pointer substitution, checks both origin URLs, each original ZIP member and 32-MiB chunk, and confirms each remote branch's exact head. `reconstruct` fetches the exact branch heads, cryptographically reassembles both complete models and publishes only into an unused destination directory. Passing `verify-bundles` does **not** imply GitHub upload.

Use `--stage pathfinder` or `--stage archivist` for controlled independent pushes. The two payload drafts carry only missing-byte markers initially. Their binary job must fail until every expected original GLB chunk exists at the exact Git head. A source job may pass while the binary job fails; this is intentional.

## No premature adoption

The correction was measured on 36 skinned exported poses across three anatomical pairs per pose; all 551 recurring contact pairs are pre-existing shared-index attachment seams and the 335 newly introduced source-pose intersections in the two selected flight clips are absent in V6's sampled poses. **This is not proof of continuous contact safety**, cross-clip blending, full mesh clearance, 171,165 mixed-skin seam risk, artist-directed geometry and textures, physical Unreal/RTX hardware, release provenance or production integration. No automatically selected model, equipment enablement, merge, or release is permitted by this transport draft.

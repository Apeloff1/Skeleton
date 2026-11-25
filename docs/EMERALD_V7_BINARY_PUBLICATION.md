# Emerald V7 original-binary publication — review-only split custody

Two real V7 GLBs have been exported from pinned original V6 weighted models. The complete model bytes total **229,515,688 bytes** and are divided into **eight exact Git binary parts** of at most **32 MiB**. Each part, complete model and the separately supplied original ZIP is SHA-256 pinned in `assets/emerald/evolution-v7/publication-manifest.json`.

| Form | Real V7 GLB | SHA-256 |
| --- | ---: | --- |
| Pathfinder | 114,696,520 bytes | `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade` |
| Archivist | 114,819,168 bytes | `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf` |

Original model ZIP names: `pathfinder-v7-orbit02-clearance.zip` and `archivist-v7-orbit02-clearance.zip`. Each contains the complete original model, independently generated source and byte-verification receipts, full 18-pose contact report, deterministic exporter and independent verifier. **These files exist in the conversation artifact delivery, not yet as GitHub binary objects.** The manifest/source branch must never be misrepresented as successful remote publication.

## Trusted authentication and original-byte publication

From an existing authorized local checkout of `Apeloff1/Skeleton` with the review-only V7 branches and actual delivered ZIPs, run:

```sh
python scripts/publish_emerald_v7_orbit02.py verify-zip \
  --bundles /trusted/emerald-v7-zips
python scripts/publish_emerald_v7_orbit02.py publish \
  --bundles /trusted/emerald-v7-zips \
  --repo /trusted/Skeleton
```

The publisher authenticates both origin URLs, verifies the exact ZIP SHA, validates every member against traversal/duplicate/linked/encrypted hazards, reads the actual model member without extracting other content, checks four contiguous raw 32-MiB-or-smaller chunk hashes and the whole model digest. It then uses Git raw blob objects without clean/smudge filters, temporary indexes, parent-anchored commit trees and **non-force** branch pushes. It fails if the remote head's manifest differs or a prior raw Git object is altered.

Expected branch destinations are `assets/emerald-v7-pathfinder-orbit02-20261117` and `assets/emerald-v7-archivist-orbit02-20261117`. No binary is marked published until its branch contains all four raw chunks and exact-head CI runs:

```sh
python scripts/publish_emerald_v7_orbit02.py verify-tree --stage pathfinder
python scripts/publish_emerald_v7_orbit02.py verify-tree --stage archivist
```

The two payload PRs intentionally begin as empty byte slots; their actual-binary job must fail until upload and full SHA validation. A synthetic source CI pass is not a binary pass. The 100 MiB per-file GitHub cap is respected by 32-MiB transport objects, but remote storage quota and repository policies still need independent confirmation.

## Strict model status

The exported V7 contact scan covered 36 selected source-mixer approximations on three anatomical pair types and found zero new non-welded contacts. It preserved **139,465** near-margin pair occurrences and **19,836** previously existing shared-vertex attachment seam occurrences. This is no clearance of all contacts, continuous-time skinned collision, arbitrary Three.js mixer loop phases or original equipment. V7 remains unadopted; the original Hoarder and V4–V6 assets stay intact. Hand-painted art, poster likeness, original Unreal project compilation, D3D12/RTX physical execution, exact-head mandatory CI, security and release-provenance gates are still held.

No draft authorizes merging, releasing, enabling equipment or changing the installed application.

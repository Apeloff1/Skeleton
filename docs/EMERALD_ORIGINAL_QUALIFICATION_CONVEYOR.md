# Emerald original asset integration conveyor

Stack order: reconstruction (#5524) → offline transaction (#5527) → native staged byte verification (#5528) → Forge provenance (#5529) → SSR custody (#5530) → original asset qualification.

## Operator flow

Run from the checked-out repository with a trusted local destination and sufficient scratch space.

```sh
python scripts/prepare_emerald_delivery.py build --archives /retained/zips --parts /retained/parts --target /assets/emerald-original
python scripts/prepare_emerald_delivery.py verify --target /assets/emerald-original
python scripts/verify_emerald_native_stage.py stage --delivery /assets/emerald-original --target /assets/native
python scripts/qualify_emerald_original.py --delivery /assets/emerald-original --staged /assets/native
```

Alternatively provide the complete original model via --model rather than --parts. Exact original pins remain unchanged; do not commit giant binary files as normal Git blobs.

## Independent rehearsal, 2026-11-17

The original source and web archive sizes and SHA-256 pins and original reconstructed model SHA-256 were rechecked. An independent Python staging rehearsal extracted the same eligible file families used by the native stager into a temporary trusted directory, copied the exact model, and rehashed each staged file. Measured 86 files and 661,542,916 bytes, 380 animations, 108 maximum skin joints. Verified original source SHA-256 093feccb25846b39eefe94a4385873e25df125371544545042c3d34b3fe879f5 and model c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a. This was an independent rehearsal, not an execution of the new repository scripts or a persistent native deployment.

## Evidence limits

Do not treat mock orchestration tests, successful archive integrity, staging or source identity as actual continuous collision/deformation, texture decoding, browser rendering, Unreal compilation, device or RTX execution, artist acceptance, release or merge evidence. Original binary publication requires an authorized asset-storage transport; it is not performed by these source PRs. Downstream checks now run independently after successful checkout, dependency installation and patching; failure still fails the entire workflow. Source-only evidence remains separate from hardware acceptance.

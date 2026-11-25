# Emerald V7 exact remote Git publication — full two-model reassembly

The V7 publication drafts are split by **stage** (Pathfinder and Archivist), with each 114–115 MB full-density original GLB divided into **four** raw Git objects no larger than 32 MiB. The source and transport manifests exist, but neither model counts as remotely published until the *actual eight binary blobs* are present on the two reviewed GitHub branches and independently reassembled from remote Git objects.

This draft implements `scripts/verify_emerald_v7_remote_original.py` for that exact acceptance boundary.

## Verified model custody requirements

| Stage | Original GLB size | Required whole-model SHA-256 |
|---|---:|---|
| Pathfinder V7 | 114,696,520 bytes | `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade` |
| Archivist V7 | 114,819,168 bytes | `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf` |
| **Total** | **229,515,688 bytes** | Each independently pinned |

The verifier loads the same immutable eight-part source manifest used by the publisher. It will authenticate the allowed Skeleton Git origin, fetch each dedicated review branch, verify **exact manifest bytes and current branch SHA**, confirm that every expected tree entry is an ordinary Git `100644 blob` (not a symlink, submodule, missing object or Git LFS pointer), inspect the remote object's byte count and read its *actual raw Git object payload*. Each of the eight parts must match its exact offset, size and SHA-256. Complete files are streamed into a temporary directory and checked again by whole-file SHA-256 and source-bound glTF/GLB metadata (108 joints, 381 clips, orbit-02 joint 34 correction, donor identity).

The remote refs are checked again *after* all parts are read. A different remote head, missing blob, same-length altered object, unapproved mode, absent original model or incorrect metadata causes failure and cleanup of temporary files. The two models and their detailed receipt are made visible **together** only after complete verification. Nothing is merged or installed.

## Operator commands

First publish the unchanged V7 ZIPs to the two stage drafts using the approved non-force raw Git publisher:

```sh
python scripts/publish_emerald_v7_orbit02.py verify-zip \
  --bundles /trusted/emerald-v7-archives
python scripts/publish_emerald_v7_orbit02.py publish \
  --repo /trusted/Skeleton --bundles /trusted/emerald-v7-archives
```

Then, **in the same authenticated, trusted Skeleton checkout**:

```sh
python scripts/verify_emerald_v7_remote_original.py \
  --repo /trusted/Skeleton \
  --output /unused/emerald-v7-remotely-verified
```

The output directory must not exist, with sufficient space for both original models plus scratch. After success, it contains:

- `pathfinder.glb` — 114,696,520 exact remote Git bytes.
- `archivist.glb` — 114,819,168 exact remote Git bytes.
- `remote-git-original-custody.json` — both immutable remote heads, per-part Git OIDs, byte and SHA receipts, GLB structural checks and a **remote-only** `remote_binary_publication_verified: true` status.

The receipt is not issued if either stage is missing or changed during verification. A successful local ZIP verification, successful synthetic CI suite or appearance of a README marker in a payload draft **never** sets this flag. Source-only automated tests use tiny simulated Git blobs and reject incomplete sources; they **cannot** prove actual remote publication.

## No acceptance escalation

The same source branch preserves `continuous_collision_qualified: false`, `real_three_mixer_qualified: false`, `artist_approved: false`, `unreal_compiled: false`, `physical_rtx_verified: false` and `release_qualified: false`. The source-confirmed 108 sampled crossfade poses only inspect three anatomical pair types. 415,154 near-margin occurrences and 59,508 inherited attachment seam occurrences are still open. No equipment enablement, active model adoption, change to original Hoarder, merge, installer release or deployment follows from binary publication.

**Repository status at authoring:** Pathfinder and Archivist V7 stage PRs contain missing-byte markers rather than verified remote Git blobs. Therefore actual publication is **not yet qualified** and no successful remote reassembly is claimed. The upload requires the authenticated operator with the original verified archives.

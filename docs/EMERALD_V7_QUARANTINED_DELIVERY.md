# Emerald V7 original model quarantine — inspect without adopting

The original Emerald Hoarder remains protected by the installed source pin at `frontend/src/features/Jeeves/companion/emeraldAssetPin.json`. The 114–115 MB Pathfinder V7 and Archivist V7 corrective models are **not approved for runtime use**, replacement of `frontend/public/emerald/v1`, native Unreal adoption, release or deployment. The separate remote original-binary publication acceptance step must be completed first.

This draft adds `scripts/stage_emerald_v7_quarantine.py`, an **external-only, readonly** local review staging process.

## Admission

Required input is the exact output of `scripts/verify_emerald_v7_remote_original.py`, not merely a model ZIP or a source test result. The incoming source directory must consist of exactly `pathfinder.glb`, `archivist.glb` and `remote-git-original-custody.json`. The bounded receipt must declare both reviewed remote stage branches, Git commit OIDs, eight raw-Git object hashes/sizes, complete model hashes, 108-joint/381-clip donor identity, and explicit nonqualification of continuous collision, real Three mixer, art, Unreal, RTX and release. This stage independently verifies both exact model SHA-256s and source-bound GLB metadata again.

The current output path **must be outside the Skeleton source tree and its public/native asset directories**, must not exist, and must not be a symlinked ancestor redirect into the checkout. Both model copies are captured through nofollow file descriptors with bounded streaming, original inode/mtime/ctime comparison, and full SHA-256. A new temporary directory and per-target lock preserve fail-closed cleanup; after complete two-form verification, the files and receipt are renamed into the new review-only destination.

## Operator sequence

Only after separately authenticating and publishing the eight unchanged raw Git objects:

```sh
python scripts/verify_emerald_v7_remote_original.py \
  --repo /trusted/Skeleton \
  --output /private/review/emerald-v7-verified-remote

python scripts/stage_emerald_v7_quarantine.py \
  --source /private/review/emerald-v7-verified-remote \
  --output /private/review/emerald-v7-quarantined
```

The new quarantine contains only the two verified GLBs and `v7-quarantine-receipt.json`. The receipt is deliberately explicit:

```json
{
  "quarantine_only": true,
  "approved_for_runtime": false,
  "frontend_public_asset_installed": false,
  "native_original_model_replaced": false,
  "source_current_remote_head_rechecked": false,
  "full_continuous_collision_qualified": false,
  "real_three_mixer_qualified": false,
  "artist_approved": false,
  "physical_rtx_verified": false,
  "release_qualified": false
}
```

This script relies on the **previous remote Git receipt** and does not re-fetch current GitHub branch heads; a successful quarantine is local-byte provenance, not a new assertion about the current live remote. To assert current remote state, run the independent remote verifier again.

## Hold boundaries

The source/ledger/nine-phase suites cover 108 sampled crossfade poses across only three anatomical pairs, with 415,154 near-margin and 59,508 inherited shared-index seam occurrences not qualified by full continuous-time collision. Other anatomical pairs, 171,165 mixed-skin risk triangles, interrupted/repeated live Three.js mixer action scheduling, artist-directed poster fidelity, handcrafted texture painting, original Unreal compilation, physical RTX and release provenance remain unqualified.

At this writing, the Pathfinder and Archivist original V7 binary payload PRs remain *missing-byte review slots*, not certified remote publication. Therefore the quarantine command has not been approved to adopt or install their models. This branch does not modify the installed app or any release configuration.

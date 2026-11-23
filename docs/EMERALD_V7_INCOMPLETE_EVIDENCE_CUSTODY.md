# Emerald V7 — crash-safe incomplete evidence, never an acceptance receipt

The original V7 operator must process two ~115 MB GLBs, **108 actual Three-mixer poses**, and an expensive exact-skinned triangle-distance contact sweep. A single failed transition, time-budget violation, wrong pin, model mutation or missing stage must never accidentally produce a positive qualification receipt.

This draft strengthens the original collision checkpoint and adds a **separate, opt-in, fail-only diagnostic escrow** for source validation and troubleshooting.

## Strict incomplete checkpoint

`scripts/qualify_emerald_v7_three_trace_contacts.py` now rejects a checkpoint if any of its completed/remaining pose counts disagree with the exact trace, any anatomical pair has negative, nonintegral or missing counters, any pair sum differs from the per-frame total, the Three world-matrix error is invalid or negative, or an original sampled transition is omitted or out of order.

Most importantly, **accepted previous checkpoint rows are still re-executed against the real original GLB and reviewed geometry** before a final report is issued. A JSON checkpoint cannot substitute for a measured triangle contact. This policy deliberately trades extra physical work for trustworthy completion evidence and does not treat partial progress as a passing result.

## Failure-only diagnostic delivery

With an exact original V7 source pair and reviewed toolchain:

```sh
python scripts/run_emerald_v7_real_three_qualification.py \
  --models /trusted/v7-exact-original-models \
  --reviewed-tools /trusted/five-sha-reviewed-contact-tools \
  --node /trusted/node24/bin/node \
  --output /unused/fully-qualified-v7-review \
  --failure-evidence /unused/v7-INCOMPLETE-incident \
  --budget-seconds-per-stage 1200
```

`--failure-evidence` must be a separate, **unused, external** directory outside the Skeleton source tree, original GLB directories, reviewed tool sources and positive output path.

If either stage raises an exception before final qualification, the process preserves an atomic, bounded diagnostic directory containing *only* a whitelist of existing Pathfinder/Archivist source Three traces, SLERP parity reports, per-pose contact checkpoints and incomplete contact JSON. The original ~229.5 MB of GLB models, secrets and unrelated application files are **never** copied into the incident escrow. Each allowed JSON file is bounded at 32 MiB and SHA-256 pinned in `INCOMPLETE-DO-NOT-ADOPT.json`.

The failure receipt explicitly states:

```json
{
  "schema": "skeleton.emerald.v7.incomplete-original-mixer-incident.v1",
  "complete_source_pose_count_unverified": true,
  "sampled_evolution_family_admitted": false,
  "sampled_three_mixer_poses_qualified": false,
  "continuous_collision_qualified": false,
  "physical_rtx_verified": false,
  "release_qualified": false
}
```

On a completely successful original pair execution, the **positive** `sampled-execution-receipt.json` appears only in the separate positive output directory; no diagnostic failure directory is created. The operator never invents a negative incident when no original model execution has occurred. If an incident snapshot cannot be created, the operator preserves the underlying source failure and does not elevate status.

### Independent follow-up

Each diagnostic JSON copy retains its exact length, SHA and relative source type. These are troubleshooting and checkpoint input references, **not authenticated execution proofs**. A later retry can use them only after re-verifying the original model, tool and trace hashes and re-executing every claimed saved collision pose; there is no bypass based on a copied checkpoint.

This does not change the original V7 model bytes, no runtime model is installed, the original Hoarder remains pinned, and no optional equipment is enabled.

## Unchanged hard holds

Both raw GitHub V7 model payloads, full arbitrary-loop browser action chains, other anatomical cohorts, 415,154 previously recorded near-margin occurrences, 59,508 inherited weld contacts, complete continuous skinned collision, original hand-authored poster likeness, compiled Unreal/physical RTX, independent device/security evidence, mass merging and release provenance remain **unqualified**. Source-only CI checks synthetic failure fixtures; it cannot assert a physically executed source model run.

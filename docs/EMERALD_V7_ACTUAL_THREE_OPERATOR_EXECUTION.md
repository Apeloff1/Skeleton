# Emerald V7 — actual two-model Three/triangle execution conveyor

## What the recorded 108-pose result does and does not mean

The earlier V7 nine-phase screen used an **offline joint interpolation approximation**, and the new two-stage evidence checker only establishes whether supplied original-model and contact JSON *could be consistent*. Neither alone proves that the actual Three `AnimationMixer` was executed on the exact V7 GLBs. Source-only CI necessarily uses tiny mock and synthetic assets rather than the 229,515,688 original model bytes.

This draft adds `scripts/run_emerald_v7_real_three_qualification.py`, the first controlled operator entry point that can **actually execute the complete source-bound sample workload**, with no simulated model acceptance.

## Original model admission

Place the two complete original SHA-pinned binary GLBs in a trusted, dedicated directory with names `pathfinder.glb` and `archivist.glb`. Their required identities are:

| Stage | Exact original bytes | SHA-256 |
|---|---:|---|
| Pathfinder V7 | 114,696,520 | `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade` |
| Archivist V7 | 114,819,168 | `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf` |

The stage requires five reviewed original contact-analysis Python modules, each independently checked against immutable SHA pins. Use the original two-archive source custodian `scripts/prepare_emerald_v7_reviewed_tools.py` first. Install the frontend's exact **Three 0.186.1** dependency from the trusted lockfile and use **Node 24** with Python 3.13 and the pinned numerical ABI. The operator does not fetch dependencies or install packages.

## Full controlled execution

```sh
python scripts/run_emerald_v7_real_three_qualification.py \
  --models /trusted/v7-original-models \
  --reviewed-tools /trusted/sha-original-contact-tools \
  --node /trusted/node24/bin/node \
  --budget-seconds-per-stage 1200 \
  --output /unused/evidence/v7-actual-three-20261118
```

The destination must be outside the Skeleton source tree, must not exist, and must have sufficient free capacity. Execution is transactional: a unique temporary staging directory holds all traces and contacts; no acceptance receipt is published when **either** stage fails.

For each stage it performs the following source-bound verification:

1. Verify the original GLB **whole-file SHA-256 and length**, not merely a manifest or source-reported metadata.
2. Use the checked-in `frontend/scripts/emerald-v7-three-mixer-trace.mjs` with genuine Three 0.186.1 to extract exactly **54 actual mixer poses**: six routes × nine fade phases, preserving action playheads, weights, all 108 local bone transforms and world matrices.
3. Independently parse and validate the trace and rehash the source model.
4. Run the complete **365,997-vertex** reviewed source skin and triangle-distance contact analyzer with the **five SHA-pinned original geometry tools**, screening three region-pair types. The geometry subprocess fails immediately if new non-welded contacts are detected, if the time budget expires or if a source model or trace hash differs.
5. Check all 54 per-pose collision witnesses against the exact trace SHA, anatomical pair inventory, source tool hashes and independent world-matrix reconstruction.
6. Repeat for the other original model. Require **108 source-derived actual mixer poses**, complete review-only anatomy witness counts and **zero new non-welded contacts**, with both stage processes executing successfully.
7. Rehash **both complete original models again after all execution** and rerun the independent paired report-consistency gate. The latter deliberately states `sampled_evolution_family_admitted: false` because source JSON alone is not runtime execution proof.

Only after the full sequence does this operator write a separate `sampled-execution-receipt.json` with `source_operator_executed_mixer: true`, `source_operator_executed_triangle_contact: true` and `source_operator_sampled_only_qualified: true`. The receipt also includes the exact SHA of all four source executables and the two resulting trace/contact JSON artifacts. The positive flags mean the operator actually ran this bounded source workload—not that the renderer, real browser or physical GPU was executed.

The process runs child commands without a shell; strips inherited Python and Node preload variables, tokens and proxy environment; bounds stdout/stderr and duration; verifies source-model inode stability with a second complete SHA; and publishes a new external evidence directory only on full completion. An incomplete run **never creates an acceptance directory**.

## Actual remaining qualification holds

Even an independently reproduced 108-pose source run does not qualify arbitrary active loop playheads, interrupted/resumed Three actions, other anatomical pair types, source-bind weld seams, **continuous-time** swept triangle intersections, optional equipment, browser WebGL, handcrafted anatomy or human-painted poster fidelity, real Unreal execution, physical RTX, security hold gates, remote GitHub publication of the eight original raw transport objects, or release provenance. The operator does not touch the installed Emerald V1/Hoarder, frontend/public, the crawler or native builds.

These are still review-only stacked drafts. Full source CI is **synthetic and negative-path**, not proof that the original 229.5 MB model workload has been run. This branch has no model adoption, branch merge or release authorization.

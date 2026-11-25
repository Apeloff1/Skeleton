# Emerald V7 — two-stage actual Three mixer contact acceptance

The previous V7 sample baseline of **108/108 poses** was computed with an offline approximation of Three's joint mixing. It is **not** interchangeable with the new real `THREE.AnimationMixer` source trace. This document defines the stricter review-only acceptance boundary for **both** Pathfinder and Archivist V7 models.

## Required independently checkable artifacts

For **each** of the two original evolution stages:

1. The complete exact original V7 GLB, SHA-256 and length verified again against `scripts/check_emerald_v7_three_mixer_trace.py`. Pathfinder: 114,696,520 bytes / `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade`. Archivist: 114,819,168 bytes / `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf`.
2. A complete real **Three 0.186** `AnimationMixer` 108-joint source trace for **nine** phases in **six** transition routes (54 sampled poses per stage), including action playheads/weights and all local/world joint transforms. These are produced by `frontend/scripts/emerald-v7-three-mixer-trace.mjs`.
3. A separately executed, original-SHA-pinned **365,997-vertex skinned triangle distance** report produced by `scripts/qualify_emerald_v7_three_trace_contacts.py` from those exact Three joints, the original GLB, and the five reviewed contact Python source files. The report must contain every one of the three anatomical pair witnesses, original bind-seam candidates, 8-mm near-margin counts and an independent world-matrix recomposition error.

## Operator-only paired gate

Only after the actual original full model tests have completed:

```sh
python scripts/admit_emerald_v7_three_mixer_pair.py \
  --original-models /verified/v7-models \
  --three-traces /verified/v7-real-three-traces \
  --contact-reports /verified/v7-actual-three-contacts \
  --output /new-evidence/emerald-v7-actual-three-sampled-admission.json
```

The gate expects `pathfinder.glb` and `archivist.glb`, `pathfinder-three-mixer.json` and `archivist-three-mixer.json`, plus `pathfinder-actual-three-contacts.json` and `archivist-actual-three-contacts.json` in their respective directories. All six files must be present, unused output path required.

Each original model's complete **SHA** is recomputed; both source traces undergo independent **108-joint, six-route, nine-phase, action-weight** verification; each triangle report must match its *exact source trace SHA*, stage GLB digest, five original geometry-source pins, all 54 phase indices and three anatomy-pair inventories. Per-pair contact counts reconcile to the sample and source summary. Any world matrix mismatch beyond the 5e-5 error bound, missing or altered source, duplicate pose, incomplete stage or newly detected non-welded triangle contact **blocks the combined receipt**.

A matching paired *JSON* receipt is marked `sampled_evolution_family_admitted: false` and `reported_sampled_source_no_new_contacts: true`: source-file consistency alone cannot authenticate actual Three/geometry execution. A separate operator-controlled real-model replay is required for any positive sampled admission. It carries the actually measured near-margin counts and inherited original weld contacts as *unqualified* evidence, not a source hard-coded threshold. The gate does **not** re-run the expensive geometry itself: `actual_three_mixer_collisions_reexecuted_by_this_gate: false` makes that distinction auditable.

## All remaining holds

Even a sampled gate success is **not** proof of arbitrary real viewer loop phase, interrupted action chains, full continuous-time skinned-mesh CCD, other anatomical pairs, 171,165 mixed-influence seam-risk faces, optional equipment, artist poster fidelity, original human-painted textures, installed GPU/WebGL, compiled Unreal, physical RTX, remote original GitHub byte publication, merge readiness or release provenance. The two models remain quarantined and unadopted.

This branch does not add any positive real-V7 Three mixer result. The prior 108/108 pass remains historical approximate evidence; only an independently produced original-model real Three mixer trace and contact report can pass this new gate. Source-only CI uses synthetic, clearly labeled fixtures to check the gate's failure policy.

# P2 spine masterplan

Apeloff1/Skeleton PR #2333. Branch `feat/p2-runtime-spine`. Parent `7648f8f`. This file is the unread-surface land. Parent cite #80. This plan does not sign work off and does not merge.

## Law

No completion checkbox. No implementation signature. No verification signature. `stored_prose=0`. Percentages are reads. `hit` stays false while `apply_landed` is false and both surfaces are unclaimed.

## Landed

| Seam | Owner | Law |
| --- | --- | --- |
| Inbox | `skeleton/persistence/inbox_ledger.py` | exactly-once, contiguous version, tenant bind |
| Fence | `skeleton/persistence/consistency_fence.py` | compare-and-advance, foreign tenant unknown |
| Published outbox | `skeleton/persistence/operation_store.py` | acknowledged rows only |
| Projection | `skeleton/persistence/spine_projection.py` | published row to inbox and fence |
| Land | `skeleton/persistence/spine_land.py` | dispatch then project |
| Hook | `skeleton/persistence/spine_dispatch.py` | publish, project, cursor |
| Worker | `skeleton/persistence/spine_worker.py` | own thread, does not replace runtime dispatcher |
| Bind | `skeleton/persistence/spine_bind.py` | starts worker only |
| Mongo inbox | `skeleton/persistence/mongo_inbox.py` | same accept law, no Motor import |
| Mongo fence | `skeleton/persistence/mongo_fence.py` | open at epoch 0 only |
| Mongo projection | `skeleton/persistence/mongo_projection.py` | SQLite outbox into Mongo |
| Catalogs | `spine_catalog.py`, `mongo_catalog.py` | one tenant, other tenant empty |
| Lag | `skeleton/persistence/spine_lag.py` | pending versus published |
| Batch | `skeleton/persistence/spine_batch.py` | cap 256, poison counts failed |
| Witness | `skeleton/persistence/spine_witness.py` | lag, catalog, status |
| Drift | `skeleton/persistence/spine_drift.py` | sqlite epoch versus mongo epoch |
| Sweep | `skeleton/persistence/spine_sweep.py` | bounded mismatch count |
| Replay | `skeleton/persistence/spine_replay.py` | duplicate does not move fence |
| Hold | `skeleton/persistence/spine_hold.py` | reason stored, applied 0 |
| Export | `skeleton/persistence/spine_export.py` | quarantine JSON |
| Digest | `skeleton/persistence/spine_digest.py` | SHA-256 of gap and drift |
| Ledger | `skeleton/persistence/spine_ledger.py` | append hash |
| Manifest | `skeleton/persistence/spine_manifest.py` | 16 names, apply_landed false |
| Reaccept | `skeleton/persistence/spine_reaccept.py` | digest match, mismatch refused before accept |
| Gate | `skeleton/persistence/spine_gate.py` | held id refused |
| Watch | `skeleton/persistence/spine_watch.py` | epoch unchanged |
| Poison ticket | `skeleton/persistence/spine_poison_ticket.py` | issued only for a hold row |
| Poison apply | `skeleton/persistence/spine_poison_apply.py` | hold row only, digest stable, epoch unchanged |
| Poison witness | `skeleton/persistence/spine_poison_witness.py` | foreign tenant journal is empty |
| Poison chain | `skeleton/persistence/spine_poison_chain.py` | rewritten journal row fails closed |
| Dispatch guard | `skeleton/persistence/spine_dispatch_guard.py` | start_dispatcher identity unchanged, not called |
| Index bind | `skeleton/persistence/spine_index_bind.py` | create_index only when present, live_motor false |
| Bind audit | `skeleton/persistence/spine_bind_audit.py` | running dispatcher fails closed |
| Cut gate | `skeleton/persistence/spine_cut_gate.py` | switch refused |
| Surface | `skeleton/persistence/spine_surface.py` | provider and PR Automation not claimed green |
| Provider probe | `skeleton/persistence/spine_provider_probe.py` | named surface unread, claim writes claimed 0 |
| PR probe | `skeleton/persistence/spine_pr_probe.py` | named check unread, claim writes claimed 0 |
| Unread gap | `skeleton/persistence/spine_unread_gap.py` | foreign tenant empty, skipped seq listed |
| Surface seal | `skeleton/persistence/spine_surface_seal.py` | forged green stripped |


AI-tree mirrors under `skeleton/ai/runtime/persistence` are byte copies.

## Tracker

- Read and project: 95%
- Provider surface claimed: 0%
- PR Automation claimed: 0%
- Poison apply: 55%
- Live Motor bootstrap: 15%
- CI green: 0%
- Merge: 0%

## Next, in order

1. Poison apply is landed as its own seam. The hold row is the only input. A changed digest stays a conflict and is refused before accept. The fence epoch does not advance. `SpineApplyGate` still refuses every intent. This is not a sign-off.
2. Motor index bootstrap stays a plan. `SpineIndexPlan.apply` calls `create_index` only when the injected collection has that method. A deployment module may pass the database. The core package still does not import Motor.
3. The runtime dispatcher is not replaced. `SpineBind` remains the only start path for the composed worker.
4. Provider-surface and PR Automation are not claimed green. `SpineProviderProbe` and `SpinePrProbe` append unread rows only. `claim` writes `claimed=0`. `SpineUnreadGap` lists a skipped sequence for that tenant and returns empty for a foreign tenant. `SpineSurfaceSeal` strips a forged green flag. This is not a sign-off.
5. CI green stays unread. Merge stays unread.

## Implement

Check out `feat/p2-runtime-spine`. Import `SpineManifest` from `skeleton.persistence`. Call `card()`. Expect `count` 32, `apply_landed` false, `poison_apply_landed` true, `completion_checkbox` false. Do not merge from this file.

```bash
python -m pytest -q skeleton/testing/test_spine_manifest.py
```

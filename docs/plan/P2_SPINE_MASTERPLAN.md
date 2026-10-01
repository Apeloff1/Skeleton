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
| CI witness | `skeleton/persistence/spine_ci_witness.py` | complete catalog, ci_green false |
| Merge gate | `skeleton/persistence/spine_merge_gate.py` | merge refused |
| Probe replay | `skeleton/persistence/spine_probe_replay.py` | matching digest does not insert |
| Motor witness | `skeleton/persistence/spine_motor_witness.py` | motor and pymongo imports fail closed |
| Dispatch witness | `skeleton/persistence/spine_dispatch_witness.py` | running dispatcher fails closed |
| Dark | `skeleton/persistence/spine_dark.py` | unwired surfaces stay dark |
| Epoch witness | `skeleton/persistence/spine_epoch_witness.py` | side card does not move the fence |
| Quiet | `skeleton/persistence/spine_quiet.py` | dark card rewrite fails closed |
| Quiet witness | `skeleton/persistence/spine_quiet_witness.py` | lit row fails closed |
| Bind card | `skeleton/persistence/spine_bind_card.py` | joins quiet, dark, epoch; green fails closed |
| Bind journal | `skeleton/persistence/spine_bind_journal.py` | rewrite fails closed |
| Bind read | `skeleton/persistence/spine_bind_read.py` | lit bind row fails closed |
| Bind chain | `skeleton/persistence/spine_bind_chain.py` | rewritten bind row fails closed |
| Bind tenant | `skeleton/persistence/spine_bind_tenant.py` | foreign tenant empty |
| Bind replay | `skeleton/persistence/spine_bind_replay.py` | matching digest does not insert |
| Bind surface | `skeleton/persistence/spine_bind_surface.py` | claimed probe fails closed |
| Bind gap | `skeleton/persistence/spine_bind_gap.py` | missing sequence stays missing |
| Bind snapshot | `skeleton/persistence/spine_bind_snapshot.py` | dark evidence is digest-bound |
| Bind recovery | `skeleton/persistence/spine_bind_recovery.py` | recovery plan cannot self-activate |
| Bind checkpoint | `skeleton/persistence/spine_bind_checkpoint.py` | one immutable recovery digest per tenant |
| Bind checkpoint replay | `skeleton/persistence/spine_bind_checkpoint_replay.py` | replay does not insert |
| Bind checkpoint tenant | `skeleton/persistence/spine_bind_checkpoint_tenant.py` | foreign tenant empty |
| Bind checkpoint chain | `skeleton/persistence/spine_bind_checkpoint_chain.py` | promoted or rewritten row fails closed |
| Bind bundle | `skeleton/persistence/spine_bind_bundle.py` | checkpoint evidence is not activation |
| Bind bundle verify | `skeleton/persistence/spine_bind_bundle_verify.py` | digest verification does not promote |
| Bind restore receipt | `skeleton/persistence/spine_bind_restore_receipt.py` | backup and expected recovery identity are anchored |
| Bind restore verify | `skeleton/persistence/spine_bind_restore_verify.py` | receipt verification does not activate |
| Bind restore journal | `skeleton/persistence/spine_bind_restore_journal.py` | receipt history is append-only |
| Bind restore replay | `skeleton/persistence/spine_bind_restore_replay.py` | receipt replay does not insert |
| Bind restore tenant | `skeleton/persistence/spine_bind_restore_tenant.py` | foreign receipt history stays empty |
| Bind restore chain | `skeleton/persistence/spine_bind_restore_chain.py` | receipt history continuity is recomputed |
| Bind restore continuity | `skeleton/persistence/spine_bind_restore_continuity.py` | durable receipt history remains non-activating |
| Bind restore export | `skeleton/persistence/spine_bind_restore_export.py` | canonical portable evidence stays non-activating |
| Bind restore export verify | `skeleton/persistence/spine_bind_restore_export_verify.py` | strict parser/digest verification grants no authority |
| Motor plan | `skeleton/persistence/spine_motor_plan.py` | deterministic driver-injected index plan |
| Motor bootstrap | `skeleton/persistence/spine_motor_bootstrap.py` | injected async/sync create_index only |
| Motor bootstrap verify | `skeleton/persistence/spine_motor_bootstrap_verify.py` | plan/cardinality/result verification |
| Motor bootstrap replay | `skeleton/persistence/spine_motor_bootstrap_replay.py` | repeated injected bootstrap must be equivalent |
| Motor preflight | `skeleton/persistence/spine_motor_preflight.py` | injected ping/hello and collection protocol probe only |
| Motor preflight verify | `skeleton/persistence/spine_motor_preflight_verify.py` | preflight evidence verification grants no authority |

| PyMongo Async adapter | `skeleton/deploy/spine_pymongo_async.py` | supported driver import is deployment-only and receipt-bound |
| PyMongo Async live qualification | `scripts/qualify_spine_pymongo_async.py` | real async driver/service proof is non-activating |

AI-tree mirrors under `skeleton/ai/runtime/persistence` are byte copies.

## Tracker

- Read and project: 96%
- Provider surface claimed: 0%
- PR Automation claimed: 0%
- Poison apply: 55%
- Async Mongo bootstrap: 80%
- CI green: 0%
- Merge: 0%
- Bind card sealed: 100%

## Next, in order

1. Poison apply is landed as its own seam. The hold row is the only input. A changed digest stays a conflict and is refused before accept. The fence epoch does not advance. `SpineApplyGate` still refuses every intent. This is not a sign-off.
2. Motor bootstrap now has a deterministic content-addressed plan plus an executable driver-injected async bootstrap contract. `SpineMotorBootstrap` accepts only injected collections, supports sync or awaitable `create_index`, fails closed on missing collections, driver faults, or invalid result identities, and is independently verified and replay-compared. `SpineMotorWitness` plus `scripts/check_spine_motor_bootstrap.py` still forbid `motor` or `pymongo` imports in the core seam. `SpineMotorPreflight` now probes an injected database through ping/hello plus canonical collection protocol checks, and `SpineMotorPreflightVerify` independently digest-verifies that evidence. `SpinePyMongoAsyncAdapter` now binds that protocol to the supported PyMongo Async API (pymongo>=4.13) in the deployment layer and emits a package/API identity receipt. Core persistence still imports neither PyMongo nor Motor. The exact-head recovery workflow now exercises the real AsyncMongoClient against its Mongo service, runs preflight, applies all three canonical indexes twice, verifies replay equivalence, and emits a digest-bound qualification receipt. This proves deployment-driver connectivity and bootstrap compatibility only. Runtime driver selection, runtime activation, merge authority, and maturity remain false.
3. The runtime dispatcher is not replaced. `SpineBind` remains the only start path for the composed worker.
4. Provider-surface and PR Automation are not claimed green. `SpineProviderProbe` and `SpinePrProbe` append unread rows only. `claim` writes `claimed=0`. `SpineUnreadGap` lists a skipped sequence for that tenant and returns empty for a foreign tenant. `SpineSurfaceSeal` strips a forged green flag. This is not a sign-off.
5. CI green stays unread. `SpineCiWitness` reports a complete catalog with `ci_green` false. `SpineMergeGate` refuses the merge. `SpineProbeReplay` does not insert. This is not a sign-off.
6. Live Motor bootstrap and the runtime dispatcher stay unwired. `SpineMotorWitness` fails closed on a motor or pymongo import. `SpineDispatchWitness` fails closed if the dispatcher is running and does not call `start_dispatcher`. This is not a sign-off.
7. The bind card joins quiet, dark, and epoch. `SpineBindCard` refuses a lit flag and a moved epoch. `SpineBindJournal` refuses a rewrite. `SpineBindRead` fails closed on a lit row. `SpineBindChain` refuses a rewritten row. `SpineBindTenant` returns empty for a foreign tenant. `SpineBindReplay` does not insert. `SpineBindSurface` refuses a claimed probe. `SpineBindGap` does not fill a missing sequence. This is not a sign-off.
8. The recovery checkpoint lane digest-binds the dark bind evidence, records an immutable per-tenant recovery checkpoint, proves replay does not insert, proves foreign tenants stay empty, seals the checkpoint row into a hash chain, verifies a deterministic evidence bundle, destructively backup/restores the checkpoint authority in a scratch SQLite drill, emits an anchored restore receipt, persists receipt history in an append-only tenant journal, proves replay non-insertion and tenant isolation, recomputes receipt-history continuity, joins those proofs into a durable non-activating continuity card, then serializes that state into canonical portable machine JSON and strictly verifies the exact bytes after a file round-trip. The bind-card evidence tracker is therefore 100%, but this is an evidence-read completion only: no runtime activation, maturity promotion, completion checkbox, implementation signature, verification signature, or merge authority is granted. `scripts/check_spine_bind_recovery.py` fails closed on AI-tree mirror drift, manifest drift, or masterplan drift and is executed by the exact-head State Recovery Drill workflow. `ready`, `activated`, `apply_landed`, `live_motor`, `dispatcher_running`, `ci_green`, and `merged` remain false. This is not a sign-off.

## Implement

Check out `feat/p2-runtime-spine`. Import `SpineManifest` from `skeleton.persistence`. Call `card()`. Expect `count` 74, `apply_landed` false, `poison_apply_landed` true, `completion_checkbox` false. Do not merge from this file.

```bash
python -m pytest -q skeleton/testing/test_spine_manifest.py
```

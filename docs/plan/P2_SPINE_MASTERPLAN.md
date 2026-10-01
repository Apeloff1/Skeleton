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
| Projection | `skeleton/persistence/spine_projection.py` | published row to inbox and fence; duplicate retry reconciles a one-epoch fence gap |
| Land | `skeleton/persistence/spine_land.py` | dispatch then project |
| Hook | `skeleton/persistence/spine_dispatch.py` | publish, project, cursor |
| Worker | `skeleton/persistence/spine_worker.py` | own thread, does not replace runtime dispatcher |
| Bind | `skeleton/persistence/spine_bind.py` | starts worker only |
| Mongo inbox | `skeleton/persistence/mongo_inbox.py` | same accept law, no Motor import |
| Mongo fence | `skeleton/persistence/mongo_fence.py` | open at epoch 0 only |
| Mongo projection | `skeleton/persistence/mongo_projection.py` | SQLite outbox into Mongo; duplicate retry reconciles a one-epoch fence gap |
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
| Poison apply verify | `skeleton/persistence/spine_poison_apply_verify.py` | durable journal + consumed ticket independently reconcile without apply authority |
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
| Bind hold | `skeleton/persistence/spine_bind_hold.py` | held id refuses the seal |
| Bind hold journal | `skeleton/persistence/spine_bind_hold_journal.py` | refusal rewrite fails closed |
| Bind hold read | `skeleton/persistence/spine_bind_hold_read.py` | applied row fails closed |
| Bind hold chain | `skeleton/persistence/spine_bind_hold_chain.py` | rewritten refusal fails closed |
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
| Runtime selection candidate | `skeleton/persistence/spine_runtime_selection.py` | qualified driver does not self-select |
| Runtime selection verify | `skeleton/persistence/spine_runtime_selection_verify.py` | verification grants no selection authority |
| Cutover rehearsal | `skeleton/persistence/spine_cutover_rehearsal.py` | green preconditions do not authorize cutover |
| Cutover rehearsal verify | `skeleton/persistence/spine_cutover_rehearsal_verify.py` | rehearsal verification grants no cutover authority |
| Live PyMongo cutover rehearsal | `scripts/rehearse_spine_pymongo_cutover.py` | live qualification feeds a refused runtime cut |
| Cutover authorization | `skeleton/persistence/spine_cutover_authorization.py` | two externally authenticated approval domains qualify evidence only |
| Cutover authorization verify | `skeleton/persistence/spine_cutover_authorization_verify.py` | verification cannot make authorization effective |
| Cutover effectiveness | `skeleton/persistence/spine_cutover_effectiveness.py` | external change-control may make authorization effective without selecting runtime |
| Cutover effectiveness verify | `skeleton/persistence/spine_cutover_effectiveness_verify.py` | effective authorization remains non-selecting |
| Selection permit | `skeleton/persistence/spine_selection_permit.py` | effective authorization issues one durable non-activating permit |
| Selection permit verify | `skeleton/persistence/spine_selection_permit_verify.py` | permit verification does not select runtime |
| Selection permit consume | `skeleton/persistence/spine_selection_permit.py` | durable permit is consumed exactly once before selection |
| Selection consumption verify | `skeleton/persistence/spine_selection_consumption_verify.py` | consumption proof does not select runtime |
| Driver selection | `skeleton/persistence/spine_driver_selection.py` | consumed permit selects durable driver state only |
| Driver selection verify | `skeleton/persistence/spine_driver_selection_verify.py` | selected-driver verification does not activate runtime |
| Runtime activation gate | `skeleton/persistence/spine_runtime_activation_gate.py` | selected live driver may become activation-eligible only |
| Runtime activation gate verify | `skeleton/persistence/spine_runtime_activation_gate_verify.py` | eligibility verification never activates runtime |
| Activation permit | `skeleton/persistence/spine_activation_permit.py` | external activation-control issues one short-lived permit |
| Activation permit verify | `skeleton/persistence/spine_activation_permit_verify.py` | permit verification does not activate runtime |
| Activation permit consume | `skeleton/persistence/spine_activation_permit.py` | durable activation permit is consumed exactly once |
| Activation consumption verify | `skeleton/persistence/spine_activation_consumption_verify.py` | consumption verification does not activate runtime |
| Runtime activation commit | `skeleton/persistence/spine_runtime_activation_commit.py` | consumed permit commits activation intent only |
| Runtime activation commit verify | `skeleton/persistence/spine_runtime_activation_commit_verify.py` | commitment verification does not activate runtime |
| Runtime activation boundary | `skeleton/persistence/spine_runtime_activation_boundary.py` | commitment leaves runtime and fence unchanged |
| Runtime activation boundary verify | `skeleton/persistence/spine_runtime_activation_boundary_verify.py` | final boundary verification does not activate runtime |
| Runtime activation handoff | `skeleton/persistence/spine_runtime_activation_handoff.py` | authenticated deployment handoff remains non-activating |
| Runtime activation handoff verify | `skeleton/persistence/spine_runtime_activation_handoff_verify.py` | handoff verification grants no activation |
| Runtime transition rehearsal | `skeleton/persistence/spine_runtime_transition_rehearsal.py` | deployment handoff is dry-run against unchanged runtime/fence |
| Runtime transition rehearsal verify | `skeleton/persistence/spine_runtime_transition_rehearsal_verify.py` | dry-run verification proves no transition executed |
| Runtime transition permit | `skeleton/persistence/spine_runtime_transition_permit.py` | external execution authority issues one short-lived non-executing permit |
| Runtime transition permit verify | `skeleton/persistence/spine_runtime_transition_permit_verify.py` | permit verification does not execute transition |
| Runtime transition permit consume | `skeleton/persistence/spine_runtime_transition_permit.py` | durable execution permit is consumed exactly once before any attempt |
| Runtime transition consumption verify | `skeleton/persistence/spine_runtime_transition_consumption_verify.py` | consumption verification does not attempt transition |
| Runtime transition attempt | `skeleton/persistence/spine_runtime_transition_attempt.py` | one consumed permit may drive one deployment-owned fail-closed attempt |
| Runtime transition attempt verify | `skeleton/persistence/spine_runtime_transition_attempt_verify.py` | refused attempt verification cannot promote runtime |
| Runtime transition rollback witness | `skeleton/persistence/spine_runtime_transition_rollback_witness.py` | independently proves the refused attempt left runtime/fence unchanged |
| Runtime transition rollback verify | `skeleton/persistence/spine_runtime_transition_rollback_verify.py` | no-effect rollback proof grants no activation authority |
| Runtime transition slot | `skeleton/persistence/spine_runtime_transition_slot.py` | explicit generation-checked runtime replacement boundary |
| Runtime transition execution | `skeleton/persistence/spine_runtime_transition_execution.py` | swaps runtime, starts candidate dispatcher, and advances deployment fence exactly once |
| Runtime transition execution verify | `skeleton/persistence/spine_runtime_transition_execution_verify.py` | independently verifies direct runtime/dispatcher/fence effects without activation |
| Runtime transition effect rollback | `skeleton/persistence/spine_runtime_transition_effect_rollback.py` | stops candidate, restores original runtime, and advances compensation fence |
| Runtime transition effect rollback verify | `skeleton/persistence/spine_runtime_transition_effect_rollback_verify.py` | independently verifies compensation without activation promotion |
| Runtime transition health | `skeleton/persistence/spine_runtime_transition_health.py` | proves the transitioned runtime can complete and durably publish a live operation |
| Runtime transition health verify | `skeleton/persistence/spine_runtime_transition_health_verify.py` | independently re-reads runtime, operation, slot, and fence health |
| Runtime transition acceptance | `skeleton/persistence/spine_runtime_transition_acceptance.py` | externally authenticated health acceptance remains non-authorizing |
| Runtime transition acceptance verify | `skeleton/persistence/spine_runtime_transition_acceptance_verify.py` | acceptance verification does not grant production activation |
| Runtime production activation authorization | `skeleton/persistence/spine_runtime_production_activation_authorization.py` | short-lived external authority may authorize production activation without performing it |
| Runtime production activation authorization verify | `skeleton/persistence/spine_runtime_production_activation_authorization_verify.py` | authorization verification cannot activate runtime |
| Runtime production activation | `skeleton/persistence/spine_runtime_production_activation.py` | consumes exact authorization + live health once without moving the rollback fence |
| Runtime production activation verify | `skeleton/persistence/spine_runtime_production_activation_verify.py` | independently re-reads activated runtime, durable health operation, slot, and rollback fence |
| Provider surface qualification | `skeleton/persistence/spine_provider_surface_qualification.py` | requires canonical + independent exact-head provider ownership receipts to agree |
| Provider surface qualification verify | `skeleton/persistence/spine_provider_surface_qualification_verify.py` | verifies closure qualification without claiming live external provider health |
| Provider live qualification | `skeleton/persistence/spine_provider_live_qualification.py` | binds exact-head closure to one authenticated credential-bearing provider call |
| Provider live qualification verify | `skeleton/persistence/spine_provider_live_qualification_verify.py` | verifies live provider evidence while PR automation and merge authority remain separate |
| PR automation qualification | `skeleton/persistence/spine_pr_automation_qualification.py` | authenticates one exact-head runner receipt and separates operational health from merge eligibility |
| PR automation qualification verify | `skeleton/persistence/spine_pr_automation_qualification_verify.py` | verifies runner health while merge authority remains false |
| CI qualification | `skeleton/persistence/spine_ci_qualification.py` | authenticates a complete exact-head successful required-check catalog without granting merge authority |
| CI qualification verify | `skeleton/persistence/spine_ci_qualification_verify.py` | independently verifies CI-green evidence while merge authority remains false |
| CI exact-head receipt producer | `skeleton/persistence/spine_ci_receipt.py`, `scripts/qualify_spine_ci_live.py` | reduces the latest six repository-owned workflow runs into HMAC-attested exact-head evidence without merge authority |
| PR Automation receipt producer | `skeleton/persistence/spine_pr_automation_receipt.py`, `scripts/qualify_spine_pr_automation_runner.py` | reduces one exact-target trusted runner report into HMAC-attested operational evidence without merge authority |

AI-tree mirrors under `skeleton/ai/runtime/persistence` are byte copies.

## Tracker

- Read and project: 100%
- Provider surface closure qualified: implemented
- Provider live qualification implementation: landed
- Provider live credential-bearing producer `scripts/qualify_spine_provider_live.py`: landed
- Provider live external credential: runtime/environment dependent
- Provider surface live claim: 0% until authenticated live receipt
- PR Automation operational qualification: implemented
- PR Automation authenticated receipt producer: landed
- PR Automation trusted evidence emission: wired; live claim remains contingent on configured attestation secret + exact-target runner receipt
- PR Automation merge authority: 0%
- Poison apply: 100%
- Apply/cutover readiness: 99%
- Async Mongo bootstrap: 100%
- CI qualification implementation: landed
- CI authenticated exact-head receipt producer: landed
- CI trusted evidence emission: wired; live claim remains contingent on configured attestation secret + complete six-check exact-head catalog
- CI live claim: 0% until complete authenticated exact-head receipt
- Merge: 0%
- Bind card sealed: 100%
- Bind hold refusal: 70%

## Next, in order

1. Poison apply is landed as its own seam. The hold row is the only input. A changed digest stays a conflict and is refused before accept. Tickets are now one-time fail-closed claims: durable consume is idempotent, replay returns `ticket-consumed`, and malformed non-hex digests are rejected before state mutation. The poison journal hash chain now covers the apply timestamp as well as identity, digest, reason, epochs, applied state, and ticket id. Successful poison recovery retains every hold row as audit evidence but releases active holds with the exact consumed ticket, allowing the normal gate to pass the recovered outbox afterward. A consumed ticket can now resume only its exact hold/digest after an interrupted apply, including the crash window after a durable success journal row but before hold release. `SpinePoisonApplyVerify` independently reconciles a successful card to exactly one durable applied row and the matching consumed ticket while keeping `apply_authority=false`. The focused State Recovery Drill executes hold, reaccept, gate, poison apply, poison-apply verification, and poison-chain regressions on the exact PR head. It also executes SQLite and Mongo projection crash-reconciliation regressions so an accepted inbox receipt cannot remain permanently detached from a one-epoch-lagging fence. SQLite projection completion is now journaled per `(consumer_id, outbox_id)` in the same transaction that increments the projection cursor, so crashes after inbox acceptance or fence advance cannot strand `applied_count`. On startup the aggregate cursor is rebuilt from those completion markers, preventing legacy aggregate state from double-counting during replay. Projection poison evidence is also scoped by `(consumer_id, outbox_id)` with legacy-row migration, so one consumer cannot contaminate another consumer's cursor or quarantine view. Bounded reads now use keyset scan cursors instead of repeatedly rescanning the oldest published rows, so backlogs larger than the batch limit cannot starve newer acknowledged outbox events. Exact-head State Recovery run 1894 passed the projection crash-recovery block after these changes, including bounded SQLite and Mongo scan regressions. The fence epoch does not advance. `SpineApplyGate` still refuses every intent. This is not a sign-off.
2. Motor bootstrap now has a deterministic content-addressed plan plus an executable driver-injected async bootstrap contract. `SpineMotorBootstrap` accepts only injected collections, supports sync or awaitable `create_index`, fails closed on missing collections, driver faults, or invalid result identities, and is independently verified and replay-compared. `SpineMotorWitness` plus `scripts/check_spine_motor_bootstrap.py` still forbid `motor` or `pymongo` imports in the core seam. `SpineMotorPreflight` now probes an injected database through ping/hello plus canonical collection protocol checks, and `SpineMotorPreflightVerify` independently digest-verifies that evidence. `SpinePyMongoAsyncAdapter` now binds that protocol to the supported PyMongo Async API (pymongo>=4.13) in the deployment layer and emits a package/API identity receipt. Bootstrap index names are explicit and deterministic, the bootstrap card is content-addressed, and `SpinePyMongoAsyncQualificationVerify` independently reconstructs live qualification without importing a Mongo driver before runtime selection may consume it. Core persistence still imports neither PyMongo nor Motor. The exact-head recovery workflow now exercises the real AsyncMongoClient against its Mongo service, runs preflight, applies all three canonical indexes twice, verifies replay equivalence, and emits a digest-bound qualification receipt. This proves deployment-driver connectivity and bootstrap compatibility only. Runtime selection is now modeled as a digest-bound candidate that requires the live qualification plus an unchanged dispatcher identity proof. Independent verification rejects any selected/authorized/activated flag. `SpineCutoverRehearsal` now requires the candidate, independent selection verification, green cutover reads, chain match, and a closed apply gate, then exercises the existing cut gate and requires the sole refusal reason `switch-not-landed`. Its independent verifier rejects digest drift or any selected/authorized/activated flag. The exact-head State Recovery workflow now feeds the real PyMongo Async qualification receipt into `SpineRuntimeSelection`, verifies the candidate, snapshots and rechecks the real `DurableOperationRuntime.start_dispatcher` binding, generates a green `SpineCutover` read, and requires `SpineCutGate` to refuse the switch with `switch-not-landed`. `SpineCutoverAuthorization` now accepts exactly two externally authenticated, distinct, time-bounded approvals from operations and reliability, scoped to the exact candidate and rehearsal digests. It emits qualified dual-control evidence only: `authorization_effective`, `selection_authorized`, `runtime_driver_selected`, and `runtime_activated` all remain false. `SpineCutoverAuthorizationVerify` independently reconstructs the authorization digest and rejects collapsed identities, scope drift, attestation drift, or authority promotion. `SpineCutoverEffectiveness` now requires the independently verified dual-control digest plus a separate, externally authenticated `change-control` receipt scoped to that exact authorization, bounded to ten minutes, and carrying a one-time nonce. This may set `authorization_effective=true`, but `selection_authorized`, `runtime_driver_selected`, and `runtime_activated` remain false. `SpineCutoverEffectivenessVerify` independently reconstructs the effectiveness digest and rejects scope or authority drift. `SpineSelectionPermitLedger` now persists exactly one selection permit per effectiveness digest and one-time nonce. A valid permit may set `selection_authorized=true`, but the record remains unconsumed and both `runtime_driver_selected` and `runtime_activated` remain false. Duplicate effectiveness evidence or nonce reuse fails closed at the durable SQLite uniqueness boundary, and `SpineSelectionPermitVerify` independently checks permit identity and digest. `SpineSelectionPermitLedger.consume()` now atomically flips the durable permit from unconsumed to consumed only after independent permit verification and before its validity window closes. Replay, missing durable rows, scope drift, nonce drift, persisted digest drift, and stale permits fail closed. `SpineSelectionConsumptionVerify` independently reconstructs the consumption digest. Selection remains authorized but `runtime_driver_selected` and `runtime_activated` remain false. `SpineDriverSelectionLedger` now persists a single `pymongo-async` selected-driver record only from independently verified permit-consumption evidence. Duplicate selection, unsupported targets, verification mismatch, or pre-existing activation fail closed. The selected-driver state may set `runtime_driver_selected=true`, but it records `runtime_object_replaced=false`, `dispatcher_started=false`, and `runtime_activated=false`; core still imports no driver. `SpineDriverSelectionVerify` independently reconstructs the record. `SpineRuntimeActivationGate` now joins independently verified selected-driver state, the live PyMongo Async qualification receipt, and a stable untouched dispatcher identity. It may set `activation_eligible=true` only when those proofs agree, while `runtime_object_replaced`, `dispatcher_started`, and `runtime_activated` stay false. `SpineRuntimeActivationGateVerify` independently reconstructs that eligibility digest. Runtime activation, merge authority, and maturity remain false.
3. The runtime dispatcher is not replaced. `SpineBind` remains the only start path for the composed worker.
4. Provider-surface and PR Automation are not claimed green. `SpineProviderProbe` and `SpinePrProbe` append unread rows only. `claim` writes `claimed=0`. `SpineUnreadGap` lists a skipped sequence for that tenant and returns empty for a foreign tenant. `SpineSurfaceSeal` strips a forged green flag. This is not a sign-off.
5. CI green stays unread. `SpineCiWitness` reports a complete catalog with `ci_green` false. `SpineMergeGate` refuses the merge. `SpineProbeReplay` does not insert. This is not a sign-off.
6. Live Motor bootstrap and the runtime dispatcher stay unwired. `SpineMotorWitness` fails closed on a motor or pymongo import. `SpineDispatchWitness` fails closed if the dispatcher is running and does not call `start_dispatcher`. This is not a sign-off.
7. The bind card joins quiet, dark, and epoch. `SpineBindCard` refuses a lit flag and a moved epoch. `SpineBindJournal` refuses a rewrite. `SpineBindRead` fails closed on a lit row. `SpineBindChain` refuses a rewritten row. `SpineBindTenant` returns empty for a foreign tenant. `SpineBindReplay` does not insert. `SpineBindSurface` refuses a claimed probe. `SpineBindGap` does not fill a missing sequence. This is not a sign-off.
8. The recovery checkpoint lane digest-binds the dark bind evidence, records an immutable per-tenant recovery checkpoint, proves replay does not insert, proves foreign tenants stay empty, seals the checkpoint row into a hash chain, verifies a deterministic evidence bundle, destructively backup/restores the checkpoint authority in a scratch SQLite drill, emits an anchored restore receipt, persists receipt history in an append-only tenant journal, proves replay non-insertion and tenant isolation, recomputes receipt-history continuity, joins those proofs into a durable non-activating continuity card, then serializes that state into canonical portable machine JSON and strictly verifies the exact bytes after a file round-trip. The bind-card evidence tracker is therefore 100%, but this is an evidence-read completion only: no runtime activation, maturity promotion, completion checkbox, implementation signature, verification signature, or merge authority is granted. `scripts/check_spine_bind_recovery.py` fails closed on AI-tree mirror drift, manifest drift, or masterplan drift and is executed by the exact-head State Recovery Drill workflow. `ready`, `activated`, `apply_landed`, `live_motor`, `dispatcher_running`, `ci_green`, and `merged` remain false. This is not a sign-off.

## Implement

Check out `feat/p2-runtime-spine`. Import `SpineManifest` from `skeleton.persistence`. Call `card()`. Expect `count` 138, `apply_landed` false, `poison_apply_landed` true, `completion_checkbox` false. Do not merge from this file.

```bash
python -m pytest -q skeleton/testing/test_spine_manifest.py
```


### Provider closure qualification

The legacy `SpineProviderProbe` remains intentionally dark and claim-refusing. Provider ownership closure is a separate evidence path: `SpineProviderSurfaceQualification` normalizes the canonical provider inventory receipt and the independent provider-ownership receipt, requires both to target the exact same 40-character head SHA, and requires declared ownership and discovered provider-edge digests/counts to agree. A successful card may set `provider_surface_closure_green=true`, but it deliberately keeps `provider_surface_live_green=false`, `provider_surface_green=false`, and `pr_automation_green=false`. `SpineProviderSurfaceQualificationVerify` independently reconstructs the closure card and rejects any live-health overclaim.

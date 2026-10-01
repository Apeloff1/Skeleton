# P2 async Mongo bootstrap (legacy Motor lane name)

Machine owners:
- `skeleton/persistence/spine_motor_plan.py`
- `skeleton/persistence/spine_motor_bootstrap.py`
- `skeleton/persistence/spine_motor_bootstrap_verify.py`
- `skeleton/persistence/spine_motor_bootstrap_replay.py`
- `skeleton/persistence/spine_motor_preflight.py`
- `skeleton/persistence/spine_motor_preflight_verify.py`

AI-tree mirrors live under `skeleton/ai/runtime/persistence`. The supported deployment adapter is `skeleton/deploy/spine_pymongo_async.py`.

## Boundary

This tranche makes the async Mongo bootstrap contract executable without importing or activating a live driver in core. The supported deployment path targets PyMongo Async with pymongo>=4.13. Core `live_motor=false`, `driver_imported=false`, and `activated=false` remain mandatory.

A deployment may inject collection objects exposing `create_index`. The core
supports either synchronous results or awaitable results, which covers the
protocol shape needed by async Mongo drivers while preserving testability and
driver isolation.

## Deterministic plan

`SpineMotorPlan` derives exactly three unique indexes from the canonical
`spine_index.INDEXES` declarations:

1. receipts identity
2. watermarks operation identity
3. tenant/resource fence identity

The normalized plan is canonical-JSON encoded and SHA-256 addressed.

## Fail-closed bootstrap

`SpineMotorBootstrap` rejects:
- missing canonical collections
- collections without callable `create_index`
- driver exceptions
- non-text/non-null index identities

A successful injected run must apply every planned index. It does not prove a
live Motor deployment exists.

## Non-activating deployment preflight

`SpineMotorPreflight` accepts an injected database-like object and exercises
only `ping`, `hello`, and canonical collection lookup. It verifies the
wire-version range and that every canonical collection exposes `create_index`.
It emits canonical SHA-256 evidence while keeping `driver_imported=false`,
`live_motor=false`, and `activated=false`.

`SpineMotorPreflightVerify` independently reconstructs the plan identity,
collection coverage, wire-version constraints, authority flags, and digest.
This qualifies the deployment protocol surface only; it does not activate the runtime.

## Supported PyMongo Async deployment adapter

`SpinePyMongoAsyncAdapter` is intentionally outside the persistence package. It imports `AsyncMongoClient`, requires pymongo>=4.13, uses Stable API v1, and emits a canonical driver identity receipt. The receipt marks the deployment driver import as present while keeping the core driver import and runtime activation false. Motor is not a dependency of this supported path.

## Live CI qualification

`scripts/qualify_spine_pymongo_async.py` opens the supported `AsyncMongoClient` against the workflow Mongo service, performs the core ping/hello preflight, applies all three canonical indexes, verifies the bootstrap card, repeats the bootstrap, and proves replay equivalence. Its receipt explicitly distinguishes deployment-driver connectivity from runtime-driver selection and runtime activation. The scratch database is dropped before client close.

## Runtime selection boundary

`SpineRuntimeSelection` consumes the live PyMongo Async qualification plus a stable dispatcher-identity proof and emits only a non-authorized candidate. It binds driver, plan, preflight, qualification, index, and dispatcher evidence into one digest while keeping `runtime_driver_selected=false`, `selection_authorized=false`, and `runtime_activated=false`. `SpineRuntimeSelectionVerify` independently reconstructs that digest and rejects any authority promotion.

## Cutover rehearsal boundary

`SpineCutoverRehearsal` requires the verified non-selecting candidate plus green cutover and chain reads, then exercises `SpineCutGate`. Even with every precondition green, the gate must return only `switch-not-landed`; it cannot advance a fence, select a driver, authorize selection, or activate runtime. `SpineCutoverRehearsalVerify` independently reconstructs the rehearsal digest and rejects authority promotion.

## Live cutover rehearsal

`scripts/rehearse_spine_pymongo_cutover.py` consumes the exact live qualification receipt produced earlier in the State Recovery workflow. It verifies the actual `DurableOperationRuntime.start_dispatcher` binding without starting it, creates and independently verifies the non-selecting driver candidate, constructs green cutover reads with a closed apply gate, and requires the cut gate to refuse the switch as `switch-not-landed`. The workflow asserts the dispatcher is still stopped and all runtime authority flags remain false.

## Dual-control authorization evidence

`SpineCutoverAuthorization` requires exactly two distinct approval receipts from the `operations` and `reliability` authority domains. Each receipt must target the exact runtime-selection candidate and cutover-rehearsal digests, be valid for no more than 30 minutes, and pass an injected deployment-owned authenticator. The resulting envelope proves authenticated dual-control evidence exists but deliberately keeps `authorization_effective=false`, `selection_authorized=false`, `runtime_driver_selected=false`, and `runtime_activated=false`. `SpineCutoverAuthorizationVerify` independently reconstructs the envelope digest and cannot make it effective.

## Authorization effectiveness boundary

`SpineCutoverEffectiveness` consumes the independently verified dual-control envelope plus a separate deployment-owned `change-control` receipt. The receipt must authenticate externally, target the exact authorization digest, remain inside a ten-minute window, and carry a 64-character one-time nonce. This seam may make authorization effective, but it cannot authorize driver selection or activate runtime. `SpineCutoverEffectivenessVerify` independently reconstructs the digest and preserves that separation.

## Durable single-use selection permit

`SpineSelectionPermitLedger` consumes independently verified effective authorization and persists one permit keyed by the effectiveness digest and one-time nonce. Both are unique in SQLite, so replay and nonce reuse fail closed. Permit issuance can set `selection_authorized=true`, but the permit remains unconsumed and neither a runtime driver nor runtime activation is changed. `SpineSelectionPermitVerify` independently verifies the permit identity and digest without consuming it.

## One-time permit consumption

`SpineSelectionPermitLedger.consume()` requires the independently verified permit, rechecks the durable SQLite row and its scope, rejects expired validity, atomically changes `consumed` from 0 to 1, and refuses replay. The resulting consumption receipt keeps `runtime_driver_selected=false` and `runtime_activated=false`; `SpineSelectionConsumptionVerify` independently reconstructs that receipt.

## Durable selected-driver state

`SpineDriverSelectionLedger` consumes only independently verified one-time permit-consumption evidence and persists `pymongo-async` as the selected target. This control-plane state does not import a driver, replace a runtime object, start a dispatcher, or activate runtime. Replay and unsupported targets fail closed. `SpineDriverSelectionVerify` reconstructs the selection identity and digest independently.

## Runtime activation eligibility

`SpineRuntimeActivationGate` joins durable selected-driver state, independent selection verification, the live `AsyncMongoClient` qualification receipt, and an unchanged dispatcher identity proof. This can produce `activation_eligible=true`, but it neither imports nor instantiates the driver in core, replaces the runtime object, starts the dispatcher, nor activates runtime. `SpineRuntimeActivationGateVerify` independently reconstructs the eligibility digest.

## External activation permit

`SpineActivationPermitLedger` requires independently verified activation eligibility plus an externally authenticated deployment-owned `activation-control` receipt scoped to the exact activation-gate digest. The receipt is capped at five minutes and carries a unique nonce. Permit issuance remains non-activating.

## One-time activation permit consumption

`SpineActivationPermitLedger.consume()` rechecks the durable permit row, exact scope and digest, refuses expired permits, atomically flips `consumed` from 0 to 1, and rejects replay. The consumption receipt remains non-activating and is independently verified.

## Durable activation commitment

`SpineRuntimeActivationCommitLedger` persists one commitment only from independently verified activation-permit consumption. The commitment is replay-resistant and records activation intent while `runtime_object_replaced=false`, `dispatcher_started=false`, and `runtime_activated=false`. Its verifier independently reconstructs identity and digest.

## Final pre-activation boundary witness

`SpineRuntimeActivationBoundaryWitness` joins the verified activation commitment to the actual runtime dispatcher binding and an epoch witness. It proves the dispatcher identity is stable and uncalled, `dispatcher_running=false`, the fence epoch is unchanged, the runtime object is not replaced, and `runtime_activated=false`. This is the final pre-activation evidence boundary, not activation itself.

## Deployment activation handoff

`SpineRuntimeActivationHandoff` binds the independently verified final pre-activation boundary to a short-lived, externally authenticated `runtime-deployment` receipt scoped to the exact boundary digest. The handoff may become `handoff_ready=true`, but the runtime object, dispatcher, fence, and activation state remain unchanged. `SpineRuntimeActivationHandoffVerify` independently reconstructs the digest and rejects authority drift.

## Deployment transition rehearsal

`SpineRuntimeTransitionRehearsal` consumes the exact verified deployment handoff before it expires, snapshots the live dispatcher binding, rechecks that the dispatcher remains stopped, and requires the fence epoch to remain unchanged. It emits a deterministic transition identity while explicitly keeping `transition_attempted=false`, `transition_executed=false`, and `runtime_activated=false`. `SpineRuntimeTransitionRehearsalVerify` independently reconstructs that evidence.

## Runtime transition execution permit

`SpineRuntimeTransitionPermitLedger` requires the independently verified dry-run rehearsal plus a separate externally authenticated `runtime-transition-execution` receipt scoped to the exact rehearsal, transition, and deployment identities. The receipt is capped at two minutes and carries a unique execution nonce. Permit issuance remains non-executing: `transition_attempted=false`, `transition_executed=false`, and `runtime_activated=false`. `SpineRuntimeTransitionPermitVerify` independently reconstructs the permit identity and digest.

## One-time runtime transition permit consumption

`SpineRuntimeTransitionPermitLedger.consume()` rechecks the independently verified permit, durable rehearsal/transition/deployment scope, payload digest, and expiry before atomically changing the persisted permit from unconsumed to consumed. Replay is refused. The resulting receipt keeps `transition_attempted=false`, `transition_executed=false`, and `runtime_activated=false`; `SpineRuntimeTransitionConsumptionVerify` independently reconstructs that receipt.

## Deployment-owned transition attempt

`SpineRuntimeTransitionAttemptLedger` accepts only independently verified, already-consumed execution-permit evidence and invokes a deployment-owned attempt callback exactly once. The callback is required to return a receipt scoped to the same transition and deployment with `decision=refuse-transition`, `transition_executed=false`, and `runtime_activated=false`. The seam snapshots the actual runtime dispatcher binding before the callback and verifies it remains identical and stopped afterwards, while the epoch witness requires the fence to remain unchanged. Any replay, execution claim, dispatcher mutation, fence movement, or activation fails closed. `SpineRuntimeTransitionAttemptVerify` independently reconstructs the attempt identity, result digest, and full card digest.

## Independent rollback/no-effect witness

`SpineRuntimeTransitionRollbackWitness` consumes the independently verified refused attempt and rechecks the actual runtime dispatcher plus fence epoch. It records `rollback_checked=true`, `rollback_required=false`, `rollback_executed=false`, and `rollback_verified=true` only when the refused attempt left no runtime effect. `SpineRuntimeTransitionRollbackVerify` independently reconstructs this card and grants no activation authority.

## Effectful transition and compensation

`SpineRuntimeSlot` owns the explicit deployment runtime reference behind a generation counter. `SpineRuntimeTransitionExecutionLedger` accepts only an independently verified no-effect boundary, durably prepares one execution identity, swaps to a distinct `DurableOperationRuntime`, starts the candidate dispatcher, and advances a tenant-scoped deployment fence exactly once. It records direct effect evidence while keeping `runtime_activated=false`; failure attempts compensation before surfacing.

`SpineRuntimeTransitionEffectRollbackLedger` consumes independently verified execution evidence, stops the candidate dispatcher, restores the original runtime slot, and advances the same fence once more as a compensation epoch. `SpineRuntimeTransitionExecutionVerify` and `SpineRuntimeTransitionEffectRollbackVerify` independently reconstruct identities, digests, generation changes, and fence movement. These seams prove effect/rollback mechanics, not production activation.

## Live post-transition health and acceptance

`SpineRuntimeTransitionHealth` runs a real durable operation through the transitioned candidate runtime. It requires the operation to reach `completed`, the transactional outbox to drain, the candidate dispatcher to remain running, the runtime slot generation to remain unchanged, and the transition fence to remain on the execution epoch. `SpineRuntimeTransitionHealthVerify` independently re-reads those live surfaces rather than trusting the first card.

`SpineRuntimeTransitionAcceptanceLedger` accepts only that independently verified live health plus a short-lived externally authenticated `runtime-transition-acceptance` receipt scoped to the exact health digest, execution identity, and deployment. The acceptance receipt is durable and replay-resistant. It records `activation_accepted=true` while keeping `production_activation_authorized=false` and `runtime_activated=false`. `SpineRuntimeTransitionAcceptanceVerify` independently reconstructs that boundary.

## External production activation authorization

`SpineRuntimeProductionActivationAuthorizationLedger` accepts only independently verified transition acceptance plus a separate short-lived externally authenticated `runtime-production-activation` receipt scoped to the exact acceptance digest, acceptance identity, execution identity, and deployment. It is durable and replay-resistant. The resulting card may set `production_activation_authorized=true`, but it keeps `runtime_activated=false` and `rollback_available=true`. `SpineRuntimeProductionActivationAuthorizationVerify` independently reconstructs that authority boundary without performing activation.

## Final production activation

`SpineRuntimeProductionActivationLedger` consumes one exact, independently verified production-activation authorization together with the exact accepted live-health proof. Before recording activation it re-reads the candidate runtime, durable health operation, runtime slot generation, dispatcher state, and deployment fence. The activation record sets `runtime_activated=true` exactly once but deliberately leaves the deployment fence unchanged. This keeps the existing compensating rollback executable after activation.

`SpineRuntimeProductionActivationVerify` independently reconstructs the activation identity and digest, then re-reads the candidate runtime, durable operation, runtime slot, dispatcher, and unchanged rollback fence. The end-to-end regression activates and then executes the existing rollback path, proving that activation does not destroy rollback authority.

## Independent checks

`SpineMotorBootstrapVerify` independently reconstructs the canonical plan and
checks plan identity, cardinality, collection coverage, keys, uniqueness, and
authority flags.

`SpineMotorBootstrapReplay` requires two injected runs to produce equivalent
plan/result cards.

`scripts/check_spine_motor_bootstrap.py` AST-scans the bootstrap modules and
fails if `motor` or `pymongo` is imported in core.

## Focused verification

```bash
python -m pytest -q --noconftest \
  skeleton/testing/test_spine_motor_bootstrap.py \
  skeleton/testing/test_spine_motor_bootstrap_control.py \
  skeleton/testing/test_spine_motor_witness.py \
  skeleton/testing/test_spine_index_bind.py \
  skeleton/testing/test_spine_pymongo_async_adapter.py \
  skeleton/testing/test_spine_runtime_selection.py \
  skeleton/testing/test_spine_cutover_rehearsal.py \
  skeleton/testing/test_spine_cutover_authorization.py \
  skeleton/testing/test_spine_cutover_effectiveness.py \
  skeleton/testing/test_spine_selection_permit.py \
  skeleton/testing/test_spine_selection_consumption.py \
  skeleton/testing/test_spine_driver_selection.py \
  skeleton/testing/test_spine_runtime_activation_gate.py \
  skeleton/testing/test_spine_activation_permit.py \
  skeleton/testing/test_spine_activation_consumption.py \
  skeleton/testing/test_spine_runtime_activation_commit.py \
  skeleton/testing/test_spine_runtime_activation_boundary.py \
  skeleton/testing/test_spine_runtime_activation_handoff.py \
  skeleton/testing/test_spine_runtime_transition_rehearsal.py \
  skeleton/testing/test_spine_runtime_transition_permit.py \
  skeleton/testing/test_spine_runtime_transition_consumption.py \
  skeleton/testing/test_spine_runtime_transition_attempt.py \
  skeleton/testing/test_spine_runtime_transition_rollback.py \
  skeleton/testing/test_spine_runtime_transition_execution.py \
  skeleton/testing/test_spine_runtime_transition_effect_rollback.py \
  skeleton/testing/test_spine_runtime_transition_health.py \
  skeleton/testing/test_spine_runtime_transition_acceptance.py \
  skeleton/testing/test_spine_runtime_production_activation_authorization.py \
  skeleton/testing/test_spine_runtime_production_activation.py
python scripts/check_spine_motor_bootstrap.py
python scripts/qualify_spine_pymongo_async.py --uri mongodb://127.0.0.1:27017 --database skeleton_p2_pymongo_async_qualification --output /tmp/p2-pymongo-async.json
```

This advances bootstrap readiness only. It does not start a driver, replace the
runtime dispatcher, claim provider/PR surfaces, mark CI authority green, merge,
or sign P2 off.

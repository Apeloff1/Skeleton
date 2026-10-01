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
  skeleton/testing/test_spine_runtime_activation_commit.py
python scripts/check_spine_motor_bootstrap.py
python scripts/qualify_spine_pymongo_async.py --uri mongodb://127.0.0.1:27017 --database skeleton_p2_pymongo_async_qualification --output /tmp/p2-pymongo-async.json
```

This advances bootstrap readiness only. It does not start a driver, replace the
runtime dispatcher, claim provider/PR surfaces, mark CI authority green, merge,
or sign P2 off.

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
  skeleton/testing/test_spine_pymongo_async_adapter.py
python scripts/check_spine_motor_bootstrap.py
```

This advances bootstrap readiness only. It does not start a driver, replace the
runtime dispatcher, claim provider/PR surfaces, mark CI authority green, merge,
or sign P2 off.

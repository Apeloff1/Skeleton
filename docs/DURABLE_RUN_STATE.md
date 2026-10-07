# Durable run and checkpoint state

`Skeleton.state.SQLiteRunStore` is the first durable execution-state primitive for the consolidation program. It is intentionally provider-neutral, stdlib-only, and isolated from agent/provider business logic so API, CLI, orchestration, and background workers can converge on one recovery contract.

## State machine

A run begins as `pending`. The only path into `running` is `claim_run()`, which assigns a worker lease and increments the optimistic concurrency revision. A pending run may also be cancelled. A running run may finish as `succeeded`, `failed`, or `cancelled`. Terminal runs are immutable and remain queryable for audit/debugging.

The lease is part of the correctness boundary, not just telemetry. Step creation, step completion, checkpoint creation, heartbeats, and running-to-terminal transitions require the current live lease owner. A different worker must wait for lease expiry before reclaiming a crashed run. The old worker becomes a fenced zombie once its lease expires.

## Crash recovery

Workers should checkpoint only after state that can be reconstructed has been durably committed. `resume_state()` returns the newest checkpoint plus every persisted step after that boundary in execution order. Checkpoint boundaries are monotonic: a newer checkpoint cannot move behind an older one.

A typical recovery flow is:

```python
from skeleton.state import SQLiteRunStore, StepStatus

store = SQLiteRunStore("var/skeleton-runs.sqlite3")
store.create_run("run-123", {"request": "build"})
store.claim_run("run-123", "worker-a", lease_seconds=30)

store.start_step(
    "run-123",
    "compile",
    "tool",
    worker_id="worker-a",
    effect_key="compile:run-123",
)
store.finish_step(
    "run-123",
    "compile",
    StepStatus.SUCCEEDED,
    worker_id="worker-a",
    result={"artifact": "build-42"},
)
store.checkpoint(
    "run-123",
    {"phase": "compiled"},
    worker_id="worker-a",
    after_step_id="compile",
)
```

After a crash, a new process waits for the previous lease to expire, reclaims the run, and inspects `resume_state()`. Completed steps after the latest checkpoint remain visible, so the orchestrator can reconcile them rather than blindly replaying from the checkpoint.

## Side-effect idempotency

`effect_key` is unique within a run. Re-issuing the same step ID with the same kind, payload, and effect key returns the existing step instead of inserting a duplicate. Rebinding an effect key to a different step fails closed.

This protects the repository's execution model from local duplicate scheduling. It does **not** magically make an external service exactly-once. For irreversible network/process side effects, pass the same idempotency key through to an external system that supports it, or add a reconciliation adapter that can prove whether the effect committed before replay.

## Concurrency and fencing

- SQLite `BEGIN IMMEDIATE` transactions serialize authoritative mutations.
- Run revisions provide compare-and-swap protection for callers that need to reject stale state.
- Active leases block competing workers.
- Expired leases can be reclaimed.
- Every live-run mutation checks worker ownership and lease freshness.
- A run cannot report `succeeded` while any step remains `running`.

## Persistence and schema policy

The current database schema is version `1` and is stored in SQLite `PRAGMA user_version`. The store refuses to open unknown schema versions and also rejects databases that claim the current version while required tables are missing. Payloads are canonical finite JSON with a configurable encoded-size ceiling.

Future schema changes must add an explicit migration step and regression coverage before `SCHEMA_VERSION` changes. Checkpoint payloads also carry their own `state_version`; subsystem-specific state migrations should be implemented above the storage layer so the store remains provider-neutral.

## CI contract

`.github/workflows/durable-state.yml` compiles `skeleton/state` and runs the focused adversarial suite whenever the durable-state package, its tests, or the workflow changes. The tests cover lease fencing, stale revisions, crash/restart recovery, checkpoint monotonicity, duplicate side-effect keys, concurrent duplicate scheduling, terminal immutability, payload limits, and fail-closed schema handling.

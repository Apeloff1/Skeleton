# Automatic native inference daemon — operator qualification hold

This change makes the approved local GGUF model do actual queued work when the
private loopback service is running. A client no longer has to call `work_one`
to consume each accepted job. The request is durable before the worker is woken.
The model cannot call operator recovery, grant itself tools, select another
model, or write a model-quality approval.

## Construction and dependency order

The new `skeleton/ai/runtime/operational_ai/orchestration/flight_control/daemon`
uses these existing authorities, in this order:

1. MBW-00 identity, bounded policy, canonical receipts and immutable model digest.
2. MBW-01 private SQLite/WAL execution spine, revision CAS, audit chain and
   flight queue/outbox, with owner-only descriptor-anchored state.
3. MBW-02 approved model GGUF loader with hash-verified sealed image and
   independently provisioned tokenizer/model identity.
4. MBW-03 bearer-scoped, loopback-only HTTP and independent operator approval.
5. MBW-04 single model caller with fenced lease heartbeat and no blind retry.
6. MBW-05 durable v2 submit, wait, cancel and authenticated health operations.
7. MBW-07 read-only operator metrics and disposable real-model canary.

The canonical bundle manifest already maps `operational_ai/orchestration` to
MBW-04 and `operational_ai/transport` to MBW-05. No binary model, archive or
generated padding is committed to source Git. Every delivered file is below
100 MB; the PR remains under 2 GB.

## Production behavior

`python -m skeleton.ai.runtime.operational_ai.transport.flight.serve \
  --model-root /private/approved-model \
  --state-dir /private/ai-state \
  --bearer-file /private/auth/bearer \
  --tenant local --subject operator --port 8766`

The operator must provision a private, rights-approved model manifest, GGUF
shards and runtime dependencies beforehand; **this command has no mock, API
provider or synthetic generation fallback**. It binds only to literal
`127.0.0.1`, requires a strong owner-only bearer file, and emits no user
prompt or bearer in logs.

`FlightDispatcher` now supports `submit` (durable admission), `wait` (0–2000 ms
bounded poll), `cancel` (immediate for unstarted; request only for running),
`job`, `queue`, `history`, `replay` and `knowledge_search`. No tool execution,
model-written approval or privileged recovery operation is added to HTTP.
`work_one` remains available only for explicitly constructed legacy/manual
flight dispatchers. Production creates the dispatcher with
`allow_manual_work=False`.

The new `GET /v2/health` requires the same bearer/Host/Origin checks as other
operations. It returns 503 while paused, draining, held, stalled, stale, or
otherwise not admitting work. A healthy TCP port is **not** model quality or
release readiness.

### Queued execution safety

- The worker is **single model caller** per activated GGUFBackend instance;
  Python threads cannot make a nonreentrant native backend safe merely by
  having SQLite locks. Different independently loaded workers may coordinate
  through the already fenced durable flight queue.
- The queue's claim-to-model-start transition is durable. Once inference may
  have begun, timeouts, failures and process loss do not imply a safe retry.
- A started job has an OS boot-bound lease with heartbeat. Old claims require
  independent operator reconciliation; the daemon preflights the durable event
  chain and refuses to start against abandoned active jobs.
- If an error happens **after** claim, including a later capacity conflict,
  the worker holds the job and the daemon latches into a held state. It never
  automatically dispatches another ambiguous turn.
- SIGTERM and KeyboardInterrupt unwind the server context. The native worker
  thread is non-daemon, so backend and database custody are not released while
  noninterruptible model generation is still executing. A bounded stop may
  report busy; it is not permission to force-close model memory.
- The production dispatcher now **refuses new admissions** when the worker
  is held, draining, stopped or observably stalled. The operator-paused queue
  may still accept bounded work for later explicit resumption. This prevents
  silently growing a backlog behind a failed native backend.
- `GET /v2/protocol` advertises only actually available production operations:
  manually triggered `work_one` is omitted when the automatic daemon owns the
  backend. Existing explicit manual-mode callers retain their prior contract.
- Operator latency percentiles use nearest-rank semantics; two observations
  cannot be falsely reported with the minimum as p95.
- `wait` and `GET /v2/health` are read-only and cannot execute a model.
  Canceling a running call cannot promise a native GPU interrupt; its durable
  state may still resolve to completed after the request.

### Operator-only inspection and canary

Read-only telemetry, with no prompt text or job IDs:

`python -m skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.operator_cli \
  --state-dir /private/ai-state --tenant local --subject operator \
  --model-sha256 <actual-sha256> --tokenizer-sha256 <actual-sha256>`

Use a **fresh isolated private state** for an actual local GGUF qualification:

`python -m skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.canary_cli \
  --model-root /private/approved-model --fresh-private-state-dir /private/new-state \
  --tenant local --subject operator`

The canary needs a concrete GGUFBackend (not a fixture), an empty flight ledger,
a newly committed native turn, an exact replay receipt and a verified flight
audit chain. No test backend can turn this path green. A successful canary is
still not proof of safety, model rights, device qualification or release.

## Focused validation

```sh
python -m unittest -q skeleton.testing.test_ai_native_daemon
python -m unittest -q skeleton.testing.test_ai_native_daemon_ops
python -m unittest -q skeleton.testing.test_ai_flight_http \
  skeleton.testing.test_ai_flight_control \
  skeleton.testing.test_ai_flight_process \
  skeleton.testing.test_ai_execution_spine
```

These are **fixture-backed** tests of durable model-calling semantics, real
SQLite, real sockets, startup guards, operator privilege separation, queue
serialization, audit proofs, concurrency, and state restoration. The full
approved GGUF and real target laptop/Windows installation must be independently
run and recorded on the final commit. Mandatory exact-head Merge Readiness,
Backend Quality, App E2E, Workflow Input Security, Sealed Context Guard,
Artifact Policy, Malware, Repository Hygiene, Secret Scanning and Dependency
Review remain held until actual successes, not skips or stale evidence.

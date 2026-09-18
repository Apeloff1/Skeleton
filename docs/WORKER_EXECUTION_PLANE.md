# Worker Execution Plane

## Purpose

The worker plane turns the shell execution boundary into an operable, inspectable
fleet model. It does not replace ShellRunner or ShellExecutor. ShellRunner owns
the process boundary; ShellExecutor owns command policy, audit, retry, circuits,
receipts, and sessions. The worker plane owns assignment, scheduling, liveness,
capacity, queue custody, and recovery around that boundary.

The implementation is deliberately synchronous and explicit. No worker module
starts a hidden daemon, polling thread, socket listener, or timer. An outer
service may provide concurrency, but it must call the same primitives described
here.

## Design goals

1. A stale worker generation cannot mutate work owned by a newer generation.
2. A claimed queue item has one current claim token.
3. Recovery requeues work by creating a fresh claim generation.
4. Worker identity is data, not a trust boolean.
5. Liveness is monotonic-clock based.
6. Heartbeat sequence replay and generation rollback fail closed.
7. Capacity, quota, and pressure decisions are explicit and inspectable.
8. Scheduling fairness is deterministic.
9. Worker state changes can be journaled and hashed.
10. Checkpoints detect rollback and forks.
11. Scaling and balancing modules only recommend; they never create workers.
12. Operator shutdown is explicit and bounded.
13. Higher-level worker facades do not bypass ShellExecutor.

## Layer map

### Process security boundary

- skeleton.shells.runner
- skeleton.shells.executor
- skeleton.shells.session
- skeleton.shells.receipts
- skeleton.shells.audit
- skeleton.shells.circuit
- skeleton.shells.retry

The worker layer must route actual commands through these components.

### Identity and registration

- skeleton.shells.worker_identity

WorkerIdentity combines a stable worker ID with a monotonically increasing
generation. Generation is critical: restarting or replacing a worker should use
a new generation so old leases, assignments, heartbeats, and control messages
cannot silently become current again.

WorkerRegistry stores one current generation per worker ID. Replacement requires
a strictly larger generation.

### Liveness

- skeleton.shells.worker_heartbeat

HeartbeatRegistry records monotonically increasing heartbeat sequences for the
current generation. Liveness states are:

- unknown
- healthy
- late
- stale

A new generation may restart its heartbeat sequence. A current generation may
not replay or decrease a sequence number.

### Queue ownership

- skeleton.shells.queue
- skeleton.shells.worker

ShellWorkQueue has explicit states:

- queued
- claimed
- completed
- failed
- cancelled

A claim includes owner and claim ID. Completion and failure require the exact
current claim. Requeueing clears ownership, generates a new queue sequence, and
makes any old claim object stale.

QueueWorker is cooperative. run_once claims at most one item and sends it through
one ShellExecutor-compatible boundary. drain is explicitly bounded.

### Stale claim recovery

- skeleton.shells.worker_recovery

WorkerRecoveryCoordinator combines heartbeat state, worker registration, and
queue claim age. Recovery only touches workers whose heartbeat is stale.

Recovered claims are requeued through ShellWorkQueue.requeue_stale_claims. Old
claim tokens remain invalid after recovery.

A recovery policy can disable or unregister a stale worker. Those actions are
mutually exclusive in one policy.

### Supervision

- skeleton.shells.worker_supervisor
- skeleton.shells.worker_lifecycle

WorkerSupervisor handles fault windows, restart windows, quarantine, and
generation-aware lifecycle state.

WorkerLifecycle provides a smaller strict state machine useful for wrappers
around worker processes:

new -> registered -> starting -> ready -> draining -> stopping -> stopped

Failure transitions are explicit.

### Admission

- skeleton.shells.worker_admission
- skeleton.shells.worker_affinity
- skeleton.shells.worker_capacity
- skeleton.shells.worker_quota
- skeleton.shells.worker_backpressure
- skeleton.shells.worker_topology

Admission composes:

1. global backpressure
2. principal quota
3. role/feature/label affinity
4. liveness
5. capacity
6. topology constraints

The modules are separated so a caller can inspect each reason independently.

### Capacity

WorkerCapacity separates maximum capacity from reserved headroom.

CapacityDemand describes the amount requested by one item.

CapacityView combines declared capacity with current inflight state and liveness.

WorkerCapacityCatalog stores declarations per worker. Unknown workers receive the
configured default declaration.

### Quotas

WorkerQuotaLedger provides per-principal fixed-window limits:

- inflight
- starts per window
- failures per window
- output bytes per window

A reservation is explicit and must be completed or released.

Quota state is separate from queue ownership. Queue claim tokens remain the
authority for queue transitions.

### Backpressure

BackpressureController evaluates queue depth, inflight count, failure ratio, and
latency. States are:

- open
- throttled
- paused

Recovery uses hysteresis so a single good sample cannot immediately reopen a
heavily pressured worker plane.

The controller returns a concurrency factor but does not start or stop workers.

### Fairness

- skeleton.shells.worker_fairness

DeficitFairQueue implements bounded deficit round robin. Each principal has a
weight. Each item has an explicit cost.

This is useful when work is submitted by multiple agents, tenants, projects, or
tool surfaces. Expensive jobs consume more deficit rather than being treated as
equal to tiny probes.

### Assignment and reservations

- skeleton.shells.worker_assignment
- skeleton.shells.worker_reservations

WorkerAssignments binds an item to a worker generation with a TTL and revision.

WorkerReservations reserves capacity after placement. Both layers validate the
current worker generation.

Assignments express ownership intent. Capacity reservations express resource
headroom. Neither replaces the queue claim token.

### Protocol envelopes

- skeleton.shells.worker_protocol
- skeleton.shells.worker_compatibility

WorkerMessage is a JSON-shaped local protocol envelope. It contains no transport
implementation.

ProtocolGuard rejects:

- protocol version mismatch
- generation rollback
- sequence replay

WorkerCompatibility checks required and forbidden features plus protocol ranges.

### Scheduling

- skeleton.shells.worker_schedule
- skeleton.shells.worker_routing
- skeleton.shells.worker_controller

WorkerSchedule stores delayed work in a heap. Nothing wakes it automatically.
The control plane calls pop_ready.

WorkerRoutes maps logical work classes to JobRequirements.

WorkerController performs admission and either queues or schedules a submission.
It never spawns a process.

### Events and evidence

- skeleton.shells.worker_events
- skeleton.shells.worker_journal
- skeleton.shells.worker_checkpoint
- skeleton.shells.worker_snapshot
- skeleton.shells.worker_state_store

WorkerEvents is a bounded synchronous event stream. Observer failures are
isolated from worker execution.

WorkerJournal is a hash-chained append-only event history.

CheckpointChain provides generation-local integrity for worker checkpoints.

FleetSnapshotter creates a canonical JSON-shaped snapshot of registry, heartbeat,
queue, metric, health, and supervision state.

WorkerStateStore offers revisioned compare-and-swap state for small JSON-shaped
worker records.

### Metrics and health

- skeleton.shells.worker_metrics
- skeleton.shells.worker_health
- skeleton.shells.worker_diagnostics

WorkerMetrics intentionally keeps low-cardinality counters keyed by worker ID.

WorkerHealthInspector translates liveness, queue pressure, registration, and
supervision into operator-facing findings.

WorkerDiagnostics checks cross-component invariants such as:

- enabled worker with stale heartbeat
- quarantined worker still enabled
- supervisor generation mismatch
- unregistered claim owner
- disabled claim owner
- claimed work while registry is empty

### Scaling and balancing

- skeleton.shells.worker_scaling
- skeleton.shells.worker_balancer

Both components return recommendations only.

WorkerScaler looks at healthy worker count and queue pressure.

WorkerBalancer looks at declared capacity and utilization.

An outer deployment system may consume those recommendations. The shell package
does not create cloud resources, containers, virtual machines, or host processes
from a scaling recommendation.

### Failover

- skeleton.shells.worker_failover

WorkerFailover manages explicit active/standby groups. Promotion is deterministic
and only selects an enabled worker with a healthy heartbeat.

### Shutdown

- skeleton.shells.worker_shutdown

WorkerShutdownCoordinator performs a bounded cooperative drain. It can stop on
failed workers, respect a deadline, and report incomplete/forced shutdowns.

It does not kill processes directly. Process termination remains inside the
shell execution boundary.

## Core invariants

### Generation invariant

Every stateful worker record that can become stale should carry or validate the
worker generation.

A worker ID without a generation is not enough for ownership-sensitive state.

### Claim invariant

Only the current claim token can complete or fail a claimed queue item.

### Recovery invariant

Recovery creates a new runnable generation of the queue item. It does not
transfer the old claim token.

### Execution invariant

Worker orchestration may select, queue, schedule, retry, supervise, or recover
work, but process execution still routes through ShellExecutor/ShellRunner.

### No hidden work invariant

Library construction must not start threads or loops. Explicit calls drive
heartbeat recording, schedule release, recovery, scaling analysis, and draining.

## Example composition

~~~python
from skeleton.shells.worker_identity import WorkerIdentity, WorkerRole
from skeleton.shells.worker_runtime import WorkerRuntime
from skeleton.shells.worker_controller import WorkerController
from skeleton.shells.runner import ShellCommand

runtime = WorkerRuntime()
worker = WorkerIdentity("builder-a", 1, role=WorkerRole.BUILDER)
runtime.register(worker)
runtime.heartbeat(worker, sequence=1)

controller = WorkerController(runtime)
submission = controller.new_submission(
    principal="jeeves",
    work_class="build",
    command=ShellCommand("python", ("-m", "compileall", "-q", "skeleton")),
    submission_id="compile-1",
)
decision = controller.submit(submission)
assert decision.accepted
~~~

The example performs control-plane work only. A QueueWorker still needs an
executor to claim and execute the queued command.

## Testing expectations

Worker-plane changes should add tests for the relevant invariants. Security and
correctness tests should prefer hostile or stale state:

- old generation attempts unregister
- old generation heartbeat
- duplicate heartbeat sequence
- queue completion using stale claim
- recovery at exact timeout boundary
- quota double completion
- checkpoint rollback
- checkpoint fork
- protocol replay
- protocol generation rollback
- topology skew
- quarantine expiry
- failed observer hooks
- schedule cancellation
- CAS revision conflict

## Extension rules

New worker modules should remain explicit data/control primitives unless there is
a compelling reason to introduce concurrency.

If a feature needs real threads or async tasks, keep lifecycle ownership at the
outer service boundary and reuse the same worker primitives underneath.

Do not add shell-text execution, ambient PATH resolution, unbounded output, or
unbounded environment inheritance to worker code. Those remain prohibited by the
shell execution policy.

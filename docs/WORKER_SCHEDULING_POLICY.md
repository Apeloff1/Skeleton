# Worker Scheduling and Ownership Policy

## Purpose

This document defines the scheduling-side invariants for the Skeleton worker
plane. It complements the shell execution policy: shell policy controls whether
a command may execute; worker policy controls where, when, and under which
ownership generation queued work may be attempted.

## Separation of concerns

Scheduling authority is not process authority.

A worker may be:

- healthy
- eligible
- under quota
- selected by affinity
- within topology constraints

and the command can still be denied by ShellExecutor because executable,
environment, workspace, capability, session, or circuit policy rejects it.

Likewise, a command can be valid for ShellExecutor but remain unscheduled because
the worker plane is paused or lacks healthy capacity.

## Submission path

Recommended submission path:

1. map work class through WorkerRoutes
2. read current fleet liveness
3. inspect backpressure
4. inspect principal quota
5. evaluate role/features/labels
6. evaluate capacity demand
7. apply topology spread
8. select deterministic worker candidate
9. optionally reserve capacity
10. queue immediately or store in WorkerSchedule
11. emit worker submission event

Actual process execution begins only after QueueWorker claims the queue item.

## Work classes

Default classes:

- build
- test
- analysis
- maintenance

Applications may add classes but should keep class names low cardinality.

Work class should describe intent. It should not contain user input, paths,
secrets, or command text.

## Priority

Lower numeric queue priority runs first.

Priority does not bypass:

- quota
- backpressure
- worker health
- executable policy
- command capabilities
- session limits

Recovery may adjust priority with a bounded delta.

## SLA classes

WorkerSLA provides queue/runtime expectations:

- interactive
- standard
- batch
- maintenance

SLA evaluation is descriptive. Breaching an SLA does not automatically widen a
timeout or retry count.

A higher-level controller may choose to:

- emit an alert
- increase deployment capacity
- cancel stale work
- lower future admission

but it must not change shell security policy merely to satisfy an SLA.

## Fair sharing

DeficitFairQueue is recommended for multi-principal admission.

Each principal has:

- a bounded queue
- a weight
- accumulated deficit
- dispatch count

Each item has an explicit scheduling cost.

Fairness weights should be configuration, not arbitrary values supplied by an
untrusted command request.

## Capacity demand

CapacityDemand has:

- inflight units
- weight units

Inflight units model parallel task slots.

Weight units model relative resource pressure.

Both are placement hints bounded by WorkerCapacity. They are not OS resource
limits. Shell runner/process limits remain separate.

## Reservations

Capacity reservation should happen after placement and before dispatch when the
outer workflow needs stronger admission-to-execution continuity.

Reservation TTL must remain finite.

Expired reservations free capacity.

A reservation validates worker generation. Replacement invalidates the old
worker identity.

## Assignment

WorkerAssignment records placement intent for an item.

Assignment and capacity reservation solve different problems:

Assignment: who should own this work?

Reservation: does that owner have reserved headroom?

Queue claim: who currently has mutation authority for this queue item?

Do not collapse these into one opaque token.

## Ownership epochs

WorkerOwnership provides a generic owner token for resources outside the queue.

Each reacquisition increments an epoch.

The token contains:

- resource ID
- worker identity/generation
- epoch
- token
- acquisition time
- expiry

An expired token cannot release a newly acquired epoch.

Use WorkerOwnership for coordination resources that do not already have a
stronger native token such as QueueItem.claim_id.

## Queue claims

Queue claims remain authoritative for queued commands.

Only the exact current claim may:

- complete
- fail
- requeue

Recovery replaces the claim generation.

## Backpressure

BackpressureController should receive low-cardinality aggregate signals:

- queued count
- claimed/inflight count
- recent success count
- recent failure count
- latency

Do not feed secrets, argv, environment values, or output content into
backpressure metrics.

### Throttled

Use concurrency_factor to reduce outer concurrency.

### Paused

Do not admit new work.

Existing in-flight commands are governed by executor/session policy.

## Quota

Quota should be keyed by a bounded principal identity.

Recommended principal examples:

- jeeves:build
- project:skeleton
- service:maintenance

Avoid per-command UUID as a quota principal; it defeats aggregation.

## Topology spread

WorkerTopology uses labels and assignment counts.

Typical topology labels:

- zone
- host
- architecture
- runtime

A placement should not exceed configured skew if another eligible domain can
accept the item.

Topology is an availability rule, not a trust boundary.

## Scaling

WorkerScaler converts healthy worker count and backlog into a recommendation.

It never creates workers.

WorkerBalancer analyzes utilization of existing workers.

An outer deployment controller should combine:

- scaling recommendation
- health
- diagnostics
- topology
- maintenance
- external deployment state

before making infrastructure changes.

## Delayed scheduling

WorkerSchedule is intentionally passive.

No thread wakes when ready_at passes.

An explicit controller calls pop_ready and enqueues returned ScheduledWork.

This makes delayed work deterministic in tests and prevents import-time hidden
activity.

## Drain budgets

WorkerDrainBudget can bound a drain by:

- items
- failures
- elapsed monotonic time

Use it when a maintenance/shutdown loop needs a smaller budget than the global
WorkerPolicy.

Budget exhaustion should produce a report, not an unbounded loop.

## Shutdown scheduling

Before shutdown:

1. stop new admission
2. evaluate whether delayed work should remain scheduled
3. drain under explicit budget
4. request stop
5. persist snapshot
6. recover remaining stale claims after ownership expiry

Do not force queue items to completed merely because shutdown is occurring.

## Determinism

For equal policy state, placement and queue order should be deterministic.

Determinism improves:

- tests
- incident analysis
- auditability
- reproducibility

Avoid random placement inside worker primitives. If an outer scheduler wants
randomization, it should provide an explicit seed/order and record the decision.

## Starvation

Fair-share scheduling and queue priority can interact.

Priority queues favor urgent work globally.

Fair-share queues protect principals.

A higher-level scheduler can stage fair-share selection before enqueueing into
the priority queue.

Do not use unbounded negative priorities as a starvation bypass.

## Failure handling

Scheduling failure types include:

- no eligible worker
- no healthy worker
- quota denial
- paused backpressure
- capacity denial
- topology denial
- assignment conflict
- reservation conflict
- stale ownership
- stale queue claim

Each should remain distinguishable in telemetry and audit output.

## Security reminders

Never build executable paths from worker labels.

Never turn work class into shell text.

Never inherit worker host environment solely because the worker is healthy.

Never widen shell timeout/output bounds in response to SLA pressure.

Never treat a scaling recommendation as authorization to execute infrastructure
commands.

The worker plane is an orchestration boundary around, not a replacement for, the
shell security boundary.

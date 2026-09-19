# Worker API Reference

This reference groups the worker-plane public concepts by responsibility.

## Identity

### WorkerIdentity

Fields:

- worker_id
- generation
- role
- labels
- features
- protocol_version

Use key for human-readable generation identity and fingerprint for deterministic
identity hashing.

### WorkerRegistry

Important methods:

- register
- replace
- get
- find
- current
- require_current
- set_enabled
- unregister
- matching
- snapshot

## Heartbeats

### HeartbeatPolicy

Controls late/stale thresholds, sequence gap, and metric count.

### HeartbeatRegistry

Important methods:

- beat
- latest
- liveness
- stale
- prune_stale
- forget
- snapshot

## Queue

### ShellWorkQueue

Worker-oriented methods:

- enqueue
- claim
- complete
- fail
- requeue
- release_claim
- claimed
- requeue_stale_claims
- cancel
- counts
- snapshot

## Cooperative worker

### QueueWorker

Important methods:

- run_once
- drain
- request_stop
- reset_stop
- snapshot

### WorkerGroup

Important methods:

- drain_round_robin
- request_stop
- snapshot

## Admission

### WorkerAdmission

inspect composes placement, quota, pressure, and capacity.

### WorkerPlacement

evaluate returns all eligible candidates, rejections, and deterministic selected
candidate.

### JobRequirements

Fields include role, features, affinity, inflight cap, and late-worker policy.

## Capacity

### WorkerCapacityCatalog

- set
- get
- remove
- snapshot
- fleet

### CapacityView

- free_inflight
- free_weight
- can_fit

## Quota

### WorkerQuotaLedger

- inspect
- reserve
- complete
- release
- usage
- active_reservations

## Backpressure

### BackpressureController

- observe
- sample_from
- reset
- state

Decision fields include state, concurrency factor, EWMAs, reason, and changed.

## Fairness

### DeficitFairQueue

- set_weight
- enqueue
- pop
- peek_principals
- remove_principal
- queued
- snapshot

## Supervision

### WorkerSupervisor

- attach
- mark_running
- fault
- restart
- begin_stop
- stopped
- release_quarantine
- require
- get
- snapshot

## Recovery

### WorkerRecoveryCoordinator

- recover
- recover_worker

RecoveryReport includes recovered workers, requeued items, timing, and truncation.

## Journal

### WorkerJournal

- append
- verify
- events
- tail
- head_digest

## Checkpoints

### CheckpointChain

- append
- restore
- verify
- head
- snapshot

## Metrics

### WorkerMetrics

- started
- completed
- retried
- recovered
- get
- snapshot
- reset

## Health

### WorkerHealthInspector

- inspect

## Diagnostics

### WorkerDiagnostics

- inspect

## Schedules

### WorkerSchedule

- schedule
- cancel
- pop_ready
- next_ready_at
- snapshot

## Routes

### WorkerRoutes

- set
- remove
- resolve
- snapshot
- defaults

## Controller

### WorkerController

- new_submission
- inspect
- submit
- release_ready

## Events

### WorkerEvents

- subscribe
- unsubscribe
- emit
- events
- tail

## Assignment

### WorkerAssignments

- assign
- renew
- release
- require
- by_worker
- snapshot

## Capacity reservations

### WorkerReservations

- reserve
- release
- require
- snapshot

## Compatibility

### WorkerCompatibility

- check

## Protocol

### ProtocolGuard

- accept
- cursor
- reset

## Scaling

### WorkerScaler

- recommend

Scaling is advisory only.

## Balancing

### WorkerBalancer

- analyze

Balancing is advisory only.

## Topology

### WorkerTopology

- filter

## Failover

### WorkerFailover

- create
- evaluate
- get
- snapshot

## Maintenance

### WorkerMaintenance

- add
- active
- available
- prune
- snapshot

## Failure log

### WorkerFailureLog

- record
- recent
- count

## State store

### WorkerStateStore

- put
- get
- compare_and_swap
- delete
- snapshot

## Fleet snapshots

### FleetSnapshotter

- capture
- loads

## Shutdown

### WorkerShutdownCoordinator

- shutdown

## Runtime

### WorkerRuntime

- register
- replace
- heartbeat
- liveness_map
- inspect_admission
- checkpoint
- recover
- health_report
- snapshot

## Service

### WorkerService

- register
- heartbeat
- submit
- recover
- diagnostics_report
- snapshot
- status

WorkerService remains an explicit facade. Constructing it does not start worker
threads or process loops.

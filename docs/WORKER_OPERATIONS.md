# Worker Operations Guide

## Scope

This guide describes operating the Skeleton worker plane. It focuses on
observable states and explicit operator actions rather than hidden automation.

## Normal startup

A normal worker startup sequence is:

1. allocate a stable worker ID
2. choose a new generation
3. register WorkerIdentity
4. attach supervision
5. transition process wrapper to starting
6. record first heartbeat
7. mark the worker ready/running
8. admit work only after healthy liveness

Reusing an old generation after process replacement defeats stale-owner
protection and should be treated as an operator error.

## Worker IDs

Worker IDs should identify a logical slot, not a process ID.

Good examples:

- builder-oslo-01
- test-linux-amd64-02
- analyst-local-01

The generation identifies replacement of that logical slot.

## Heartbeats

Heartbeat timestamps use a monotonic clock inside the process.

Operators should watch:

- current sequence
- heartbeat age
- busy
- inflight
- bounded numeric metrics

Sequence must increase within one generation.

A sequence restart is valid only after generation increases.

### Healthy

Healthy workers are eligible for placement.

### Late

Late workers are normally excluded from placement unless a specific job
requirement allows late workers.

### Stale

Stale workers are recovery candidates.

Do not immediately complete work on behalf of a stale worker. First recover its
queue claims so old claim tokens are invalidated.

## Queue states

### queued

Work is runnable and has no owner.

### claimed

Work has an owner and claim token.

### completed

Terminal success.

### failed

Terminal failure.

### cancelled

Terminal cancellation before claim.

## Claim recovery

Use requeue_stale_claims or WorkerRecoveryCoordinator.

Recovery checks claim age and can filter by owner.

A recovered item receives:

- state queued
- owner cleared
- claim ID cleared
- new queue sequence
- optionally adjusted priority

The old QueueItem object cannot later complete the recovered item.

## Worker quarantine

WorkerSupervisor quarantines based on fault or restart budgets.

On quarantine:

- registration is disabled
- supervision state becomes quarantined
- quarantine_until is set

Release requires the quarantine interval to expire.

After release, the worker returns to starting. It should produce a fresh healthy
heartbeat before receiving work.

## Backpressure

Backpressure is a fleet condition, not a worker failure.

### open

Normal admission.

### throttled

Admission may continue, but outer concurrency should apply the returned
concurrency factor.

### paused

New work should not be admitted.

Existing in-flight work may be allowed to finish according to operator policy.

## Quotas

Quotas are per principal.

A typical principal may be:

- Jeeves subsystem
- user session
- project
- API client
- scheduled workflow

Quota decisions expose a retry-after value for window-based denial.

Always complete or release reservations.

## Fair share

Use DeficitFairQueue when multiple principals submit worker jobs.

Set weights intentionally. The default weight should remain conservative.

Use item cost to represent relative resource demand. Cost is a scheduling input,
not a security grant.

## Capacity

Declare worker capacity separately from observed inflight count.

Reserve headroom for:

- control probes
- cleanup
- shutdown work
- emergency recovery

Do not advertise host theoretical maximum as usable capacity if doing so removes
operational headroom.

## Topology

Topology spread can reduce correlated failures.

Common labels:

- zone
- rack
- host
- architecture
- runtime

SpreadConstraint operates on a label key and active assignment counts.

Topology filtering is deterministic and should be applied after basic
eligibility but before final assignment.

## Failover

Failover groups have an explicit active worker.

Promotion requires:

- current registration
- enabled registration
- healthy heartbeat

No healthy standby means no promotion.

The failover module never fabricates a worker or marks stale capacity healthy.

## Maintenance

Maintenance windows are explicit intervals.

A maintenance window can be used to:

- stop new placement
- drain the worker
- perform host updates
- rotate local caches
- replace the worker generation

Expired windows should be pruned.

## Delayed work

WorkerSchedule has no timer thread.

The control plane must call pop_ready and then enqueue returned work.

This design prevents module import or object construction from unexpectedly
creating background activity.

## Shutdown

Recommended graceful shutdown sequence:

1. stop new admission
2. optionally release ready scheduled work according to policy
3. drain bounded queue work
4. request stop on workers
5. verify claimed count reaches zero
6. capture fleet snapshot
7. verify journal
8. stop outer runtime

If the deadline expires with claimed work remaining, report forced/incomplete
shutdown and recover those claims on the next control-plane owner.

## Snapshots

Capture a FleetSnapshot before:

- planned maintenance
- fleet replacement
- incident mitigation
- large policy changes
- shutdown
- recovery

The snapshot digest provides a compact identity for the captured state.

Snapshots are diagnostic evidence. They are not authority tokens.

## Journals

WorkerJournal is append-only within its configured capacity.

Verify the chain before exporting or relying on it for incident reconstruction.

A failed verification indicates one of:

- mutation
- truncation/reordering
- corrupted digest linkage
- implementation defect

## Checkpoints

Checkpoints are local to one worker generation.

A new generation starts a new checkpoint chain.

Do not restore a checkpoint from another worker ID or generation.

Rollback and fork detection intentionally fail closed.

## Diagnostics

Run WorkerDiagnostics when:

- queue items appear stuck
- recovery is unexpectedly frequent
- supervisor state and registration disagree
- a worker is disabled but still active
- claimed work exists without known workers

Errors should be resolved before increasing capacity, because extra workers can
hide rather than fix ownership defects.

## Health findings

Critical examples:

- stale enabled worker
- quarantined worker
- queue over critical watermark
- no healthy workers

Warnings include:

- late heartbeat
- unknown heartbeat
- high queue depth
- disabled owner retaining a claim

## Scaling

WorkerScaler and WorkerBalancer return recommendations only.

An outer deployment layer decides whether to act.

Before scale out, verify that the bottleneck is worker capacity rather than:

- paused backpressure due to failures
- external dependency outage
- command circuit breakers
- resource-session exhaustion
- queue ownership corruption

Before scale in, verify:

- enough healthy workers remain
- topology spread remains acceptable
- assignments can drain
- maintenance windows do not remove additional capacity

## Metrics

WorkerMetrics tracks:

- starts
- successes
- failures
- retries
- duration
- output bytes
- recovered claims

Worker ID is the intended cardinality boundary. Avoid adding command arguments,
paths, tokens, correlation IDs, or user-controlled arbitrary strings as metric
keys.

## Operational checks

A minimal pre-flight checklist:

- registry generations current
- heartbeat states healthy
- no stale enabled workers
- no unexpected claimed items
- queue below pressure watermark
- journal verifies
- diagnostics has no errors
- quota capacity available
- topology domains sufficient
- shell execution CI green

## Security boundary reminder

The worker plane decides who should receive work and when.

It does not authorize arbitrary process execution.

Actual commands must still satisfy:

- registered executable policy
- argv-only execution
- environment policy
- workspace policy
- command catalog/admission
- caller capability grant
- session/resource limits
- retry/circuit policy

Worker health does not imply command authority.

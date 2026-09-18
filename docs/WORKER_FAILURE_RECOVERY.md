# Worker Failure and Recovery Runbook

## Objective

Recover work without allowing stale worker state to regain authority.

The central rule is simple: invalidate ownership before redispatch.

## Failure classes

### Command failure

The worker is healthy, the executor returned a non-success result, and queue
transition succeeded.

Action:

- keep worker enabled unless fault budget indicates otherwise
- classify the command failure
- apply configured retry policy inside ShellExecutor
- mark item failed when retry policy is exhausted

### Executor exception

The worker claimed an item but ShellExecutor or a wrapper raised.

Action:

- make the queue item terminal or explicitly requeue through a current claim
- record the exception type without copying secret child output into control logs
- increment fault budget
- consider quarantine for repeated internal errors

### Heartbeat loss

Worker heartbeat becomes late then stale.

Action:

1. stop assigning new work
2. identify current claims by owner
3. wait for stale-claim age threshold
4. requeue stale claims
5. disable or unregister worker generation
6. verify old claim tokens can no longer transition items
7. optionally replace with a higher generation

### Worker process death

Treat as heartbeat loss even if the outer runtime detected exit immediately.

Do not trust local in-memory state from the dead process to finalize queue work.

### Queue transition conflict

A worker tries to complete/fail using a stale claim.

This is evidence that ownership already changed.

Action:

- do not retry the transition using guessed state
- fetch current QueueItem
- inspect current owner/claim
- record transition error
- stop or fail the stale worker wrapper if appropriate

### Lease conflict

Another owner currently holds a lease.

Action depends on policy:

- requeue the queue claim with a new generation, or
- fail the item if duplicate work is unsafe

Never ignore the lease and execute anyway.

### Quota exhaustion

This is admission pressure, not a worker fault.

Action:

- leave work queued/scheduled
- use retry-after information
- do not quarantine worker

### Backpressure pause

This is fleet pressure.

Action:

- stop new admission
- allow bounded in-flight completion
- investigate failure ratio, latency, and queue depth
- require hysteretic recovery samples before reopening

### Supervisor quarantine

Quarantine is an explicit safety state.

Action:

- worker registration should be disabled
- recover stale queue claims
- do not release before quarantine expiry
- require startup + fresh heartbeat after release

## Recovery algorithm

For each stale worker generation:

1. confirm WorkerRegistry still considers that generation current
2. confirm HeartbeatRegistry reports stale
3. enumerate claimed queue items owned by worker ID
4. filter by claim age
5. requeue each eligible claim
6. clear owner and claim ID
7. assign a fresh queue sequence
8. optionally adjust priority
9. disable or unregister stale worker
10. journal recovery event
11. increment recovered-claim metric
12. run diagnostics

## Why generation matters

Worker IDs are intentionally reusable logical names.

Without generation, a replacement process could inherit:

- old assignments
- old protocol sequence
- old checkpoints
- old supervisor state
- old heartbeats

Generation separates those lifetimes.

## Why claim IDs matter

A worker object may remain alive after control-plane recovery.

If requeue only changed state but preserved the claim ID, that stale object could
later complete the new owner's work.

Fresh claim IDs make stale mutations fail.

## Recovery timing

Use two independent concepts:

Heartbeat stale threshold identifies dead/unresponsive worker ownership.

Claim stale threshold identifies work old enough to recover.

They may differ. A conservative system can mark a worker stale before its claims
are eligible for redispatch.

## Priority on recovery

Recovered work may use a positive priority delta to avoid immediate hot-loop
redispatch.

Alternatively, critical work can use a negative delta if the outer policy
explicitly wants recovered tasks prioritized.

Keep the policy deterministic and bounded.

## Repeated recovery

Frequent recovered claims may indicate:

- worker crashes
- too-short heartbeat thresholds
- host suspension
- overloaded event loop
- executor deadlock
- unbounded command timeout elsewhere
- bad lease TTL
- faulty shutdown logic

Do not solve repeated recovery only by adding workers.

## Evidence collection

Capture before destructive intervention when possible:

- FleetSnapshot
- WorkerDiagnosticsReport
- HeartbeatSnapshot
- queue counts
- claimed queue item IDs
- supervisor snapshot
- WorkerJournal verification
- recent WorkerFailureLog
- shell telemetry
- execution receipts

Do not copy child stdout/stderr into broad incident channels unless redaction
policy explicitly permits it.

## Checkpoint recovery

CheckpointChain protects worker-local progress metadata.

Rules:

- same worker ID
- same generation
- strictly increasing sequence
- previous digest equals current head digest
- checkpoint digest verifies

A checkpoint failure should not be bypassed by rewriting the digest in place.

Start a new worker generation if continuity cannot be proven.

## Protocol recovery

ProtocolGuard tracks last sequence per worker generation.

After replacement:

- increment worker generation
- protocol sequence may restart
- reject old-generation messages

Do not reset the guard for a still-current generation merely to accept a replay.

## Failover recovery

For an active/standby group:

1. evaluate active liveness
2. require active to be unhealthy
3. locate first deterministic healthy enabled standby
4. promote by revising group state
5. journal decision
6. route future assignments to new active

Promotion does not mutate queue claims already held by the old active. Recover
those independently.

## Shutdown recovery

If shutdown reaches its deadline with claimed work:

- report incomplete/forced state
- persist snapshot
- stop outer runtime
- on next owner, wait for claim staleness
- recover claims using normal recovery path

Avoid special shutdown-only ownership rules.

## Validation after recovery

Recovery is complete when:

- stale worker disabled/unregistered
- recovered items queued
- old claim tokens rejected
- no orphan claims
- diagnostics has no ownership errors
- journal verifies
- replacement generation healthy if present
- queue/backpressure state understood

## Tests that must remain

The regression suite should retain explicit coverage for:

- stale completion after requeue
- exact stale-age boundary
- owner-filtered recovery
- priority delta
- duplicate recovery prevention
- healthy worker not recovered
- stale worker disable
- stale worker unregister
- quarantine expiry
- generation guard
- heartbeat replay
- protocol replay
- checkpoint rollback/fork

These are ownership invariants, not cosmetic behavior.

# Shell AI Distributed Authority Operations

## Purpose

This document defines production operations for the distributed authority
dependencies used by the AI shell plane.

The AI shell relies on more than local process state.

Production execution may depend on distributed stores for:

- seal replay protection
- quorum approval
- release channels
- release registry
- policy state
- review state
- session state
- evidence chains
- audit witnesses
- idempotency records

A worker must not assume those systems are healthy because the local process is
healthy.

## Core invariant

Execution authority may be consumed only while all required authority
dependencies are healthy enough to preserve their security property.

Examples:

- replay protection must be writable
- quorum state must be writable
- audit witness state must be writable
- release state must be readable
- required evidence state must be readable and writable
- state revisions must support compare-and-swap

If a required dependency cannot prove its property, execution fails closed.

## Why ordinary liveness is insufficient

A successful TCP connection does not prove a state backend is usable.

A backend can be:

- reachable but read-only
- reachable but stale
- reachable but partitioned
- reachable but rejecting CAS
- reachable but serving old data
- reachable but timing out writes
- reachable with broken consistency
- reachable through the wrong namespace

Authority health must prove the operation the control actually needs.

## AuthorityHealthState

The authority health layer uses three states.

HEALTHY means the required property was proven.

DEGRADED means the backend responded but a required consistency or write
property could not be proven.

UNAVAILABLE means the backend could not be used.

Production required dependencies accept only HEALTHY.

## Callable health probes

CallableAuthorityHealthProbe wraps a bounded application-specific health check.

It converts:

- true to HEALTHY
- false to UNAVAILABLE
- exception to UNAVAILABLE

Exception text is sanitized.

Only the exception class is retained.

Do not put backend secrets into health detail.

## Versioned state health probes

VersionedStateHealthProbe can verify read access.

It can also verify read/write/CAS behavior.

Production single-use authority stores should normally use write verification.

The probe writes a private heartbeat record under a dedicated health namespace.

The heartbeat key includes a hash of the worker instance identity.

The raw instance identity is not placed in the key.

## CAS heartbeat

The write probe performs:

1. read current heartbeat
2. determine expected revision
3. build bounded heartbeat payload
4. compare-and-swap heartbeat
5. verify returned revision

This proves more than simple reachability.

It demonstrates that the worker can currently update versioned authority state.

## CAS conflict

A CAS conflict on a per-instance heartbeat is unexpected.

The probe reports DEGRADED.

The health guard fails closed for required dependencies.

The probe does not spin indefinitely.

A later health cycle may recover.

## Heartbeat namespace

Use a dedicated namespace.

Recommended properties:

- isolated from production authority records
- bounded record count
- documented retention
- no secret values
- one key per worker/probe identity
- safe to delete during maintenance after worker retirement

Do not reuse a real seal or quorum key as a health heartbeat.

## Instance identity

Give each worker a unique stable instance identity for its lifetime.

Examples:

- orchestrator workload UID
- instance UUID
- pod UID
- deployment instance token

Do not use a shared constant for every worker.

Shared heartbeat keys create artificial CAS contention.

## Read-only probes

Read-only probes are appropriate for dependencies whose security property is
read-only.

Examples may include:

- immutable configuration mirror
- read-only release evidence replica
- external transparency log reader

Do not use read-only health for a replay registry that must consume authority.

## AuthorityHealthPolicy

AuthorityHealthPolicy defines:

- required dependency names
- maximum acceptable probe latency
- maximum acceptable result age

The policy has a deterministic digest.

The digest can be included in signed trust snapshots.

## Required dependency names

Names should describe the authority role.

Examples:

- release
- model-registry
- quorum
- seal-replay
- audit-witness
- evidence-store
- session-store
- review-store

Keep names stable.

Avoid embedding hostnames or ephemeral IDs in dependency names.

## Optional dependencies

Optional probes may fail without blocking execution.

Examples might include:

- metrics export
- non-authoritative tracing
- best-effort analytics

Optional status remains visible in the report.

Do not classify an authority dependency as optional merely to improve
availability.

## Latency budget

A backend can be technically healthy but too slow for safe authority use.

Excessive latency can create:

- expired seals
- approval races
- stale state
- operator confusion
- retry amplification

Required dependencies exceeding the configured latency budget fail the report.

## Result age

A health result must be recent.

Old successful health evidence is not proof of current availability.

AuthorityHealthPolicy enforces maximum result age.

## Service startup

AIShellService can require authority health at startup.

Recommended order:

1. local diagnostics
2. shell readiness
3. release verification
4. runtime trust pin
5. authority health verification
6. READY

A required authority dependency failure at startup transitions the service to
FAILED.

## Runtime execution

Authority health is rechecked at execution boundaries.

The check happens before authority consumption.

This ordering matters.

A failed health probe should not burn:

- execution seal
- quorum approval
- assurance-only approval

The operator may retry after dependency recovery with the same still-valid
authority when policy permits.

## Sealed execution ordering

Recommended sealed execution sequence:

1. service READY
2. release current
3. runtime trust current
4. authority health healthy
5. plan pin current
6. source preconditions current
7. human approval valid
8. quorum valid
9. assurance binding current
10. seal verify and consume
11. quorum consume
12. approval consume when required
13. child execution
14. receipts
15. evidence finalization
16. audit anchor
17. audit witness

## Why health precedes seal consumption

Suppose the seal replay backend is unavailable.

If the service consumes a local approval first and then discovers replay state
cannot be written, the authority state becomes partially consumed.

Checking required authority dependencies first reduces partial-authority failure.

## Why health does not replace atomic consumption

Health is advisory proof immediately before the operation.

The real state mutation must still use atomic semantics.

Between health check and consume, the backend can fail.

Therefore:

- seal consume still uses atomic insert/CAS
- quorum consume still uses CAS
- audit witness publish still uses CAS

Health reduces predictable failure.

It does not replace concurrency control.

## Fail closed semantics

When a required dependency fails:

- no child process starts
- service may transition to DEGRADED
- current error is returned
- authority is not silently recreated
- no fail-open host fallback occurs
- no local-only replay fallback occurs

## Seal replay backend failure

If distributed seal replay protection is unavailable:

stop distributed sealed execution.

Do not fall back to per-process replay protection.

A process-local registry cannot prove cluster-wide single use.

## Quorum backend failure

If quorum storage is unavailable:

stop quorum-required execution.

Do not copy quorum votes into local memory and continue.

Do not lower required vote count.

Do not convert quorum approval into ordinary approval.

## Release backend failure

If the active release channel cannot be verified:

stop release-required execution.

Do not invent a release.

Do not reuse a stale cached release indefinitely.

## Audit witness backend failure

If audit witness publication is mandatory for the environment:

stop or degrade according to policy before accepting new high-risk work.

If execution already finished before the witness backend failed:

preserve local finalized evidence.

Escalate missing witness publication.

Do not claim rollback-resistant audit completion.

## Evidence backend failure

If durable receipt/evidence persistence is required:

do not claim durable audit guarantees while the backend is unavailable.

High-risk policy should normally stop execution when evidence durability cannot
be ensured.

## Health report

AuthorityHealthReport contains:

- overall ok flag
- ordered probe results
- reasons
- policy digest
- observation time

The report is suitable for internal status and trust snapshots.

## Probe result

Each result contains:

- dependency name
- health state
- check time
- latency
- bounded detail
- optional revision
- bounded metadata

Do not include secrets.

## Audit witness purpose

The audit anchor chain proves internal hash continuity.

A valid old snapshot of that chain can still be internally consistent.

If a backend is restored to an older valid state, ordinary chain verification
may succeed.

AIAuditWitnessStore provides a monotonic signed witness sequence.

The current expected audit root can then detect rollback.

## Audit witness contents

A witness binds:

- schema version
- monotonic sequence
- audit root
- previous witness digest
- runtime trust digest
- release evidence digest
- observation time

The witness is signed.

## Witness chain

Witness 1 has no predecessor.

Witness N points to witness N-1 by digest.

The head points to the canonical latest witness digest and sequence.

The head advances through compare-and-swap.

## Immutable witness nodes

Witness nodes are written with put-if-absent semantics.

They are not overwritten by normal store operations.

The mutable part is the head pointer.

This pattern separates immutable evidence from canonical sequence selection.

## Publish sequence

Witness publication performs:

1. read current head
2. select next sequence
3. construct witness
4. sign witness
5. insert immutable witness node
6. CAS head to new witness

If head CAS loses a race, the inserted node becomes an unreachable orphan.

The publisher retries against the new canonical head.

## Orphan witness nodes

An orphan witness node is not part of the canonical chain.

It may remain in storage.

That is acceptable.

Do not treat every immutable node as canonical.

The head identifies the canonical witness sequence.

## Bounded retries

Witness publishing has a retry bound.

Repeated conflict eventually fails.

The system does not spin forever under pathological contention.

## Witness capacity

The store has a maximum witness count.

Capacity exhaustion is fail closed.

Production retention should prevent unplanned exhaustion.

## Witness verification

Verification walks the canonical sequence.

It checks:

- every canonical node exists
- sequence matches key
- predecessor digest matches
- signature verifies
- final witness digest matches head

Any mismatch fails verification.

## Head tampering

If the head digest is changed without changing the witness:

verification fails.

If the head sequence points to a missing node:

verification fails.

If the head points to an older valid witness:

the old chain may verify internally.

The current expected audit root is then needed to identify rollback.

## Rollback detection

require_current_root compares the current witness against the audit root the
caller expects.

A rollback from root B to older root A therefore fails.

Runtime trust and release digests can also be required.

## External expectation

Rollback resistance is strongest when the expected witness head or audit root
is also retained outside the backend being checked.

Possible external locations:

- deployment control plane
- independent security store
- transparency service
- incident archive
- signed trust snapshot

A malicious actor with unrestricted write access to every copy can defeat
software-only rollback detection.

## Trust snapshots and witnesses

AITrustSnapshot can include:

- runtime trust digest
- authority health policy digest
- audit witness head digest
- audit witness sequence
- release evidence digest
- sandbox binding digest

Signed snapshots provide an external correlation point.

## Backup strategy

Back up:

- authority state
- audit witness nodes
- audit witness head
- release state
- evidence chain state

Backups must preserve revision semantics where required.

## Restore strategy

A restore is not complete when the database starts.

After restore:

1. keep AI shell execution disabled
2. verify database integrity
3. verify release state
4. verify runtime trust
5. verify witness chain
6. compare restored witness head to external expected head
7. compare audit root to external expected root
8. verify authority health
9. issue new trust snapshot
10. only then re-enable execution

## Restore to older snapshot

If restore intentionally uses an older backup:

do not simply accept the older witness head.

Determine the last externally acknowledged head.

Reconcile evidence.

Decide whether lost authority state makes replay possible.

Rotate authority namespaces or keys if necessary.

## Replay state rollback

Rolling back seal replay state can make previously consumed seals appear unused.

This is high severity.

After replay-state rollback:

- stop sealed execution
- identify rollback interval
- invalidate outstanding seals operationally
- consider rotating seal signing key
- inspect execution receipts
- inspect audit witnesses
- redeploy with clean replay namespace when necessary

## Quorum state rollback

Rolling back quorum state can resurrect consumed approvals.

After quorum rollback:

- stop quorum-required execution
- identify affected approvals
- invalidate outstanding quorum records
- reopen approval only through new IDs
- inspect witness and receipt evidence

## Release state rollback

Rolling back release channel state may route workers to old releases.

Runtime trust epochs and signed release evidence should detect this boundary.

Do not resume until release state is reconciled.

## Audit witness state rollback

If witness state is older than externally expected state:

treat it as rollback.

Do not publish forward blindly before understanding the gap.

Capture the restored state first.

Compare external trust snapshots.

Reconstruct missing evidence if possible.

## Multi-region operation

Distributed authority stores need a clear consistency model.

High-risk authority should not rely on eventually consistent writes for
single-use semantics.

Recommended properties:

- linearizable CAS
- atomic put-if-absent
- monotonic revisions
- durable writes
- bounded failover behavior

## Active-active regions

Active-active execution requires cluster-wide authority semantics.

Seal replay state must be global across active regions.

Quorum consumption must be global across active regions.

Audit witness head selection must be globally serialized or partitioned by a
clearly defined authority domain.

## Region partition

During a network partition, availability and single-use safety can conflict.

For high-risk shell authority, prefer safety.

A region that cannot reach the authoritative replay/quorum store should stop
execution.

## Regional authority domains

If regions intentionally have separate authority domains:

- use separate signing scope or namespace
- use separate replay domain
- use separate quorum domain
- include region authority identity in evidence
- do not assume cross-region single use

## Failover

Before failing over to another region:

1. confirm old region stopped issuing authority
2. confirm replicated authority state is current
3. verify witness head
4. verify release state
5. verify runtime trust
6. verify backend health
7. start replacement workers
8. capture trust snapshot

## Split brain

Split-brain authority can create duplicate execution.

Prevent split brain with:

- quorum-based database leadership
- fencing tokens
- linearizable leases
- global CAS
- explicit regional ownership

Application-level health checks cannot repair a broken consensus system.

## Fencing

Fencing tokens protect stale lease holders.

A worker with an old fencing token must not mutate a resource after a newer
owner acquires it.

Use fenced operations for long-lived exclusive authority where supported.

## Lease expiry

Lease expiry must be based on a reliable monotonic or backend clock model.

Do not infer lease validity from wall-clock timestamps copied between hosts
without understanding clock behavior.

## State namespace design

Use separate namespaces for:

- replay
- quorum
- review
- sessions
- health
- witnesses
- release channels
- policy

Namespace separation improves diagnostics and reduces accidental key collision.

## Namespace migration

To migrate a namespace:

1. freeze writers
2. snapshot old namespace
3. verify state
4. copy state
5. verify revisions or canonical identities
6. configure new namespace
7. run health probes
8. restart workers
9. pin new runtime trust when configuration identity changes
10. retire old namespace

## Database migration

Schema migration affecting authority records should be treated like a security
change.

Test:

- CAS semantics
- uniqueness constraints
- replay uniqueness
- revision monotonicity
- transaction isolation
- failure rollback
- serialization/deserialization

## Read replica use

Do not use stale read replicas for decisions that must match a subsequent
single-use write unless the consistency model guarantees correctness.

Examples:

- checking unused seal on replica then consuming on primary
- reading quorum approval on stale replica
- reading old release channel state

Prefer authoritative reads for authority decisions.

## Cache use

Caches must not become the source of truth for single-use authority.

Cache may accelerate:

- status display
- non-authoritative metrics
- immutable artifact lookup

Cache must not decide:

- seal unused
- quorum unconsumed
- current release
- current trust epoch

unless correctness is guaranteed by the underlying protocol.

## Retry policy

Retries must be bounded.

Retry only errors known to be transient.

Do not retry non-idempotent authority mutation blindly.

CAS conflict should reload current state before retry.

## Timeout policy

Distributed authority calls need explicit timeouts at the transport layer.

A synchronous health probe records latency but cannot preempt an unbounded
backend call by itself.

Configure backend clients with network and request timeouts.

## Circuit breakers

Circuit breakers may reduce repeated pressure on a failing backend.

A circuit opening for a required authority dependency should fail execution.

Do not use the circuit to turn a required dependency into optional behavior.

## Rate limiting

Authority stores should protect against accidental request amplification.

Avoid health probes at excessive frequency.

Use one heartbeat per relevant operation or bounded health interval.

Do not schedule sub-second health storms across thousands of workers.

## Health cadence

Useful health points include:

- startup
- before sealed execution
- before other high-risk authority consumption
- periodic operations monitoring

The current service verifies authority health at execution boundaries.

## Health cache

If a future implementation caches health results, the cache age must be bounded.

The policy already exposes maximum result age.

High-risk execution should use sufficiently fresh evidence.

## Monitoring

Recommended counters:

- authority health checks
- healthy results
- degraded results
- unavailable results
- CAS conflicts
- latency violations
- stale-result violations
- witness publishes
- witness publish conflicts
- witness verification failures
- witness rollback mismatches

## Histograms

Useful latency histograms:

- replay store operation
- quorum store operation
- release read
- witness publish
- health probe

Do not label histograms with raw session IDs.

## Alerts

Alert on:

- required dependency unavailable
- repeated CAS heartbeat conflict
- witness verification failure
- expected audit root mismatch
- replay store restore event
- quorum store restore event
- release channel rollback
- authority health latency spike
- witness capacity nearing limit

## Dashboard

A production authority dashboard should show:

- service phase
- runtime trust epoch
- release revision
- authority health policy digest
- each required dependency state
- last health time
- witness sequence
- witness head digest prefix
- recent seal replay failures
- recent quorum failures

## Incident severity

Treat the following as high severity:

- replay-state rollback
- consumed quorum resurrection
- witness signature failure
- audit root rollback
- split-brain authority
- unknown release rollback
- store accepting conflicting CAS writes

## Incident first actions

Recommended first actions:

1. stop new AI shell execution
2. preserve current service state
3. capture trust snapshot
4. capture authority health report
5. capture witness head
6. capture release state
7. preserve backend logs
8. prevent automated repair from overwriting evidence

## Replay incident

For suspected duplicate execution:

1. identify seal ID
2. inspect replay record
3. inspect receipt chain
4. inspect session evidence
5. inspect witness sequence
6. identify all workers that saw the seal
7. identify backend failover events
8. compare region authority domains
9. determine external side effects

## Quorum incident

For suspected approval misuse:

1. identify quorum ID
2. inspect votes
3. inspect voter identities
4. inspect roles
5. inspect consume state
6. inspect seal binding
7. inspect receipt evidence
8. inspect witness timeline

## Witness incident

For witness verification failure:

1. stop execution
2. do not rewrite witness nodes
3. capture raw head record
4. capture affected immutable nodes
5. verify signer key identity
6. compare external trust snapshot
7. compare backup state
8. determine earliest divergence
9. restore only through documented recovery

## Backend credential compromise

If state backend credentials are compromised:

- revoke credentials
- stop writers
- inspect mutation logs
- verify authority state
- verify witness state
- rotate application credentials
- consider namespace rotation
- invalidate outstanding authority if integrity is uncertain

## Seal signing key compromise

If seal signing key is compromised:

- stop seal issuance
- stop sealed execution
- rotate key
- invalidate outstanding seals operationally
- inspect replay state
- inspect receipts
- inspect audit witness timeline

## Audit signing key compromise

If audit witness signing key is compromised:

- stop claiming trustworthy new witnesses
- capture current state
- rotate key
- mark key-rotation boundary
- preserve old verification key material
- issue first new-key witness only after reconciliation

## Trust snapshot key compromise

If trust snapshot signing key is compromised:

- stop using snapshots as independent integrity evidence
- rotate key
- preserve old snapshots for forensic comparison
- record rotation boundary

## Data retention

Retain authority evidence according to risk and compliance needs.

Examples:

- consumed seal metadata
- quorum metadata
- witness chain
- release evidence
- signed trust snapshots
- receipts
- session evidence

Do not retain raw child output by default when classification forbids it.

## Witness retention

Witness nodes form a chain.

Do not delete a predecessor that is required to verify retained head state.

If compaction is introduced in the future, use a signed checkpoint protocol.

Do not truncate witness history silently.

## Health heartbeat retention

Health heartbeat records are operational state.

They may be pruned after worker retirement.

Pruning heartbeat records does not affect execution evidence.

Document pruning policy.

## Disaster recovery drill

Run periodic drills.

A drill should cover:

- authority store restore
- replay-state verification
- quorum-state verification
- release verification
- witness verification
- runtime trust verification
- worker restart
- trust snapshot generation

## Drill success criteria

A successful drill proves:

- no duplicate authority becomes valid
- expected witness head is recovered
- runtime trust matches deployment
- authority health passes
- service enters READY only after verification

## Testing

The repository includes tests for:

- healthy callable probes
- failing callable probes
- sanitized exceptions
- CAS heartbeat success
- CAS heartbeat conflicts
- read-only probes
- latency policy
- stale-result policy
- optional dependencies
- required dependencies
- witness chain continuity
- signature tamper
- predecessor tamper
- missing node
- head tamper
- root rollback
- runtime trust mismatch
- release mismatch
- restart reconstruction

## Test doubles

When using fake backends in tests:

- preserve CAS conflict semantics
- preserve revision monotonicity
- preserve put-if-absent uniqueness
- avoid mocks that always succeed regardless of expected revision

Weak mocks can hide authority bugs.

## Chaos testing

Useful chaos cases:

- replay backend unavailable
- quorum backend unavailable
- witness backend read-only
- CAS conflict storm
- high latency
- stale replica
- restore to old snapshot
- region partition
- signer key mismatch
- release rollback

## Expected behavior under chaos

Required authority failures should produce:

- no child process
- no silent local fallback
- deterministic error class
- DEGRADED or FAILED service state
- preserved unconsumed authority where ordering permits

## Recovery after transient outage

For a transient backend outage:

1. keep service degraded
2. restore backend
3. run direct backend health
4. verify authority state
5. verify witness state
6. restart or explicitly recover service
7. verify runtime trust
8. capture trust snapshot
9. resume

## Recovery after CAS conflict storm

Investigate:

- duplicate worker instance IDs
- split brain
- hot shared heartbeat key
- backend isolation
- application retry bug

Do not merely raise retry limits.

## Recovery after latency spike

Investigate:

- backend saturation
- network path
- replica lag
- transaction contention
- large records
- retry amplification

Keep fail-closed latency policy for high-risk authority unless change control
explicitly approves a new budget.

## Backup validation

A backup is useful only if it can be verified.

Validate backups by restoring into isolated infrastructure and checking:

- witness chain
- release state
- replay records
- quorum records
- revision semantics

## Immutable external archive

For stronger audit resilience, periodically export:

- trust snapshot
- witness head
- release evidence digest
- audit root

to an independent archive.

The archive should have separate credentials and retention controls.

## Transparency service

A high-assurance environment may submit witness head digests to an independent
transparency service.

That creates an external monotonic reference.

The current repository does not require such a service.

AIAuditWitnessStore provides the local signed primitive needed to integrate one.

## Compliance integration

Compliance systems can consume bounded metadata.

Recommended exported fields:

- witness sequence
- witness digest
- runtime trust digest
- release evidence digest
- service phase
- observation time

Avoid exporting raw child output unless specifically required.

## Privacy

Authority metadata can still be sensitive.

Protect:

- internal model IDs
- release names
- infrastructure topology
- worker IDs

Use hashes where full identity is unnecessary.

## Multi-tenant systems

Multi-tenant shell authority should separate trust domains.

Possible partition keys:

- tenant
- environment
- region
- application

Do not share replay or quorum namespaces across tenants without deliberate
cross-tenant authority design.

## Tenant health

One tenant dependency failure should not necessarily block another tenant if
authority domains are fully isolated.

If they share the same authoritative store, shared failure policy applies.

## Production dependency classification

Typical required dependencies for medium/high-risk distributed execution:

- release
- model registry
- seal replay
- evidence store

Typical additional required dependencies for high risk:

- quorum
- sandbox control plane
- audit witness

Exact requirements remain deployment policy.

## Development profile

A local development profile may use:

- in-memory store
- local seal registry
- optional witness
- relaxed authority health

Do not advertise development semantics as distributed production guarantees.

## Staging profile

Staging should exercise production-like authority semantics.

Prefer:

- real CAS backend
- distributed replay
- quorum store
- witness store
- release channel
- trust snapshots

## Production profile

Production should require:

- durable CAS semantics
- distributed single-use authority
- signed release evidence
- runtime trust epoch
- authority health
- audit witnesses
- trust snapshots
- verified sandbox for high risk

## Change-control checklist

Before changing an authority backend:

- identify security property
- identify namespace
- identify consistency requirement
- validate CAS
- validate put-if-absent
- test failover
- test restore
- test health probe
- test rollback detection
- document rollback procedure

## Maintenance window

Before planned maintenance:

1. stop new high-risk execution
2. drain active work
3. capture trust snapshot
4. capture witness head
5. confirm no outstanding critical authority
6. perform maintenance
7. verify backend
8. verify witness
9. verify runtime trust
10. resume

## Schema migration checklist

For authority tables or documents verify:

- key uniqueness preserved
- revisions preserved
- consumed state preserved
- signatures preserved
- digest fields preserved
- timestamps preserved
- canonical serialization preserved

## Replay record migration

Replay migration must preserve consumed seal identity.

Do not regenerate replay IDs from mutable metadata.

Do not drop historical consumed entries until all corresponding seals are
expired and retention policy permits.

## Quorum migration

Quorum migration must preserve:

- approval ID
- principal
- intent fingerprint
- proposal fingerprint
- votes
- roles
- decision
- expiry
- consumed state
- digest-relevant metadata

## Witness migration

Witness migration must preserve exact canonical payloads and signatures.

Changing serialization changes witness digest.

Do not normalize historical payloads in place.

## Release migration

Release migration must preserve signatures and evidence digests.

Do not resign old releases just to fit a new storage schema unless policy
explicitly treats them as new releases.

## Operational ownership

Assign explicit ownership for:

- release store
- model registry
- replay store
- quorum store
- witness store
- evidence store
- signing keys

Unowned security infrastructure degrades silently.

## On-call runbook

On-call should know:

- how to disable AI shell execution
- how to inspect service phase
- how to inspect runtime trust
- how to inspect authority health
- how to inspect witness head
- how to verify release
- how to capture trust snapshot
- who owns each backend

## Safe shutdown

During shutdown:

- stop accepting new work
- drain or cancel according to policy
- finalize receipts
- finalize session evidence
- publish required witness
- capture final trust snapshot
- stop worker

## Unsafe shutdown

If shutdown occurs during execution:

- recovery must inspect receipts
- recovery must inspect session evidence
- recovery must inspect journal evidence
- recovery must verify witness state
- external side effects may require manual reconciliation

## Exactly-once limits

Distributed authority can make authorization single-use.

It cannot make arbitrary external side effects exactly once.

For external systems use:

- idempotency keys
- transactional APIs
- target-system deduplication
- compensating workflows

## Authority versus effect

A seal can be consumed exactly once while the child process partially performs
an external effect.

Receipt and recovery logic must distinguish authority consumption from effect
completion.

## Evidence order

Recommended terminal evidence sequence:

1. child completes
2. receipt recorded
3. verification recorded
4. session evidence finalized
5. audit anchor appended
6. audit witness published
7. trust snapshot optionally captured

## Witness publication failure after child completion

If child completed but witness publication fails:

- do not rerun child automatically
- preserve receipt and session evidence
- mark audit completion incomplete
- recover witness publication separately
- inspect external effects before any retry

## Service status

Service status can include:

- release report
- runtime trust report
- authority health report

Operators should treat DEGRADED status as execution-disabled until resolved.

## Future extensions

Possible future extensions include:

- external transparency witness
- threshold signatures
- hardware-backed signing
- multi-party audit notarization
- signed backend consistency proofs
- region-scoped authority epochs

These should compose with existing digests rather than bypassing them.

## Design principle

Availability is not the only objective.

For AI-directed host execution, duplicate authority and silent rollback are
security failures.

The distributed authority plane therefore prefers explicit failure over
unverifiable execution.

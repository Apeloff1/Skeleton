# Shell AI Distributed Execution Fencing

## Purpose

This document defines distributed execution fencing for the AI shell plane.

A valid reviewed plan and a valid execution seal do not, by themselves, prove
that only one worker currently owns the right to cross the process-creation
boundary.

In a single-process deployment that distinction is easy to miss. In a
multi-worker deployment it is fundamental.

Two workers can observe the same reviewed plan. Two workers can receive the
same failover request. Two workers can race around scheduler retries, network
partitions, delayed messages, process restarts, or control-plane failover.

The execution fence gives the final worker boundary a monotonic ownership
token. Only the current fenced owner may proceed.

## Scope

Use execution fencing for multi-worker Jeeves execution, horizontally scaled
shell workers, failover deployments, sealed production execution, high-risk
sandbox execution, and any deployment where duplicate host-side effects are
unacceptable.

Execution fencing is not a replacement for process-local leases, shell
admission, weighted concurrency, signed seals, approvals, or sandboxing.

It addresses one question: which worker owns this exact execution right now?

## Core invariant

When distributed execution fencing is configured, no reviewed AI plan may
cross the process boundary unless the current worker holds the current fenced
lease for that exact session and plan.

The fence is not a model-visible capability.

The fence is not a planning hint.

The fence is execution authority evidence.

## Authority stack

A production path can include the authenticated principal, AI intent, admitted
provider/model, deterministic review, policy decision, source preconditions,
human approval, quorum approval, release evidence, runtime trust, assurance
policy, verified sandbox, signed execution seal, distributed execution fence,
shell admission, child process, receipts, verification, signed evidence, and
anti-rollback audit witness.

Each layer has a separate job.

The fence supplies fleet ownership. The seal supplies single-use execution
authority. Runtime trust supplies identity continuity. The sandbox supplies
isolation. Receipts and audit evidence explain what actually happened.

## Why a seal alone is not enough

A seal is single use when it is consumed by a correct replay registry, but
ownership races can still happen before or around consumption.

Worker A can receive an action and stall. Worker B can receive a failover copy.
Both can validate the same reviewed plan. One worker can pause while another
takes over. A restarted worker can hold old local state.

A monotonic fence adds an independent ownership check at the process boundary.

## Fence backend

AIExecutionFenceManager uses the existing FencedLeaseBackend protocol.

The backend must support lease acquisition, renewal, release, and current-fence
verification.

Production backends must provide strongly consistent ownership semantics.

The in-memory backend defines reference semantics for tests; it is not a
distributed production store.

## Fencing token

Each acquisition gets a monotonically increasing fencing token for the
resource.

A later owner receives a larger token.

The old token never becomes current again.

This is stronger than a random lock token because a downstream trusted system
can reject stale generations even if an old worker wakes after a pause.

## Resource identity

The fence resource key is derived from the session ID and exact plan
fingerprint.

Changing the plan creates a different ownership resource.

Changing only the worker does not. Workers are intended to compete for
ownership of the same reviewed execution.

The resource key is hashed so the coordination backend does not need raw model
text, argv, stdout, stderr, or secret values.

## Fence binding

AIExecutionFenceBinding commits to the schema version, session ID, principal,
worker ID, plan fingerprint, runtime trust digest, release evidence digest,
required wall-time window, and fence policy digest.

The binding has a deterministic SHA-256 digest.

## Fence digest

AIExecutionFence additionally commits to the actual backend lease.

The resulting digest binds lease namespace, resource key, owner, fencing token,
acquisition time, and expiry.

Two acquisitions for the same logical execution therefore have different
fence digests.

The second acquisition is a new ownership epoch.

## Assurance binding

The execution-fence digest is included in AssuranceBinding.

The signed execution seal therefore commits to the exact distributed fence.

A seal created for fencing generation 7 cannot execute under generation 8.

A seal created for worker A cannot execute on worker B.

A seal created under one trust epoch cannot cross into a later trust epoch.

## Worker identity

AIShellService requires an explicit worker ID when execution fencing is
configured.

Do not rely on a process ID alone, a hostname alone, a mutable display name, or
a pod ordinal alone.

Prefer a deployment-controlled worker identity with generation semantics.

If the broader worker plane already has WorkerIdentity, use a stable
representation of its current generation.

## Principal binding

The fence records the authenticated execution principal.

A plan fenced for Alice is not valid for Bob.

Authentication remains outside the fence manager. The fence records the trusted
result and makes principal substitution detectable.

## Runtime trust binding

The fence binds the current runtime trust epoch when configured.

This catches provider revision drift, adapter drift, tool catalog drift, effect
registry drift, policy drift, assurance drift, release drift, and trusted
workspace drift.

An old fence cannot cross a new runtime epoch.

## Release binding

The fence also commits directly to current release evidence.

Runtime trust normally contains release state, but the explicit release digest
keeps the ownership artifact independently inspectable.

Redundant identity at authority boundaries is intentional.

## Fence policy

AIExecutionFencePolicy defines the default step timeout, per-step overhead,
safety margin, minimum lease lifetime, maximum lease lifetime, and maximum
number of plan steps.

The policy has a deterministic digest.

Changing the policy changes the fence binding.

## Why lease duration derives from the plan

A worker must not legitimately lose its fence while its bounded plan is still
allowed to execute.

If a lease expires before the plan's allowed execution window, another worker
could reacquire ownership while the first child is still validly running.

The lease lifetime therefore covers the deterministic worst-case plan window.

## Current wall-time calculation

The current ShellPlanExecutor runs plan steps in deterministic topological
order.

The conservative fence window is the sum of each step timeout, per-step
overhead, and a safety margin.

If a step has no explicit timeout, the configured fence default is used.

The result is raised to the minimum lease lifetime when necessary.

If the result exceeds the configured maximum lease lifetime, acquisition fails.

## Retry semantics

The ordinary AIShellService plan path currently does not inject a retry policy.

One timeout allowance per step is therefore conservative for that path.

If a future execution backend enables retries, its fence window must account
for maximum attempts, maximum retry delay, per-attempt timeout, and attempt
overhead.

Do not add retries underneath a fence budget that was calculated for one
attempt.

## Future parallel execution

The current plan executor is sequential.

A future parallel DAG executor may use a critical-path bound, but summing all
step bounds remains conservative.

Any optimization of the fence window must be independently reviewed and tested.

## No hidden renewal

The execution fence has no background renewal loop.

That is deliberate.

Hidden renewal would create hidden ongoing authority.

The normal service path expects the initial bounded lease to cover the full
execution attempt.

## Explicit renewal

AIExecutionFenceManager exposes explicit renewal for callers that have a
reviewed reason to extend ownership.

Renewal keeps the same fencing token, produces a new lease instance, invalidates
the old lease object, must cover the required plan window, and cannot exceed
the policy maximum.

If renewal fails, execution must not begin.

## Old lease after renewal

The pre-renewal lease object is stale.

Callers must replace local fence state with the renewed object.

This prevents cached lease objects from silently remaining authoritative.

## Recommended acquisition sequence

A production worker should reach READY, verify the release, verify runtime
trust, verify authority dependency health, verify the reviewed plan pin, then
acquire the execution fence.

After acquisition it can validate preconditions and approvals, build the
assurance binding, and issue the execution seal.

The fence should be acquired close to execution, not during model planning or
long-lived human review.

## Seal issuance

seal_review accepts the exact execution fence.

When fencing is configured, a missing fence is an error.

The service validates session, principal, worker, plan, trust epoch, release
evidence, and current backend fence before the digest enters AssuranceBinding.

Only then can the seal be issued.

## Sealed execution sequence

The production sequence is: verify service readiness, release, runtime trust,
authority health, plan pin, preconditions, human approval, quorum, execution
fence, assurance binding, assurance policy, and execution seal.

After the seal is consumed, the service consumes quorum authority, rechecks the
reviewed execution path, invokes the exact backend, verifies results, records
provenance, and releases the fence in a finally block.

## Why fence validation precedes seal consumption

A stale, missing, or foreign fence is an ownership failure.

It should not burn a one-use execution seal.

A correct worker can reacquire ownership and issue new matching authority after
the state is reconciled.

## Why seal consumption precedes child creation

The fence only proves worker ownership.

It does not grant process authority.

The child starts only after both the fence and signed seal are valid.

## Why fence release uses finally

Once a valid current fence is supplied to execute_sealed, the execution attempt
owns it.

The service releases it on success, seal mismatch, quorum failure, backend
failure, verification failure, or unexpected exception.

This prevents leases from being stranded after failed attempts.

## Missing fence behavior

If fencing is configured and execute_sealed receives no fence, execution stops,
the seal remains unused, and no child starts.

If a caller acquired a fence but never supplied it to the attempt, that caller
still owns the fence and must release it explicitly.

## Direct execution behavior

When distributed execution fencing is configured, AIShellService.execute is
disabled.

Callers must use execute_sealed.

This prevents a supposedly low-risk direct path from bypassing fleet ownership
policy.

A deployment that intentionally allows unfenced low-risk execution should use
a distinct explicit service profile.

## Split-brain example

Assume worker A owns token 10.

Worker A pauses long enough for its lease to expire.

Worker B acquires token 11.

Worker A resumes with its old local state.

The backend rejects worker A because token 10 is stale.

Possession of the old plan, approval, quorum, or seal data does not restore
worker A's ownership.

## Failover procedure

A failover worker waits for expiry or explicit release, acquires a new fence,
receives a larger fencing token, revalidates release and runtime trust,
revalidates or reconstructs reviewed plan state, and obtains a new seal bound
to the new fence.

Do not reuse a seal bound to the previous fence.

## Crash before seal issuance

If a worker crashes after fence acquisition but before seal issuance, no child
ran.

The lease expires or is released by recovery.

The next worker acquires a larger token and creates new authority.

## Crash after seal issuance but before consumption

The old seal is bound to the old fence.

After ownership changes, a new fence produces a different assurance digest.

The old seal cannot be reused under the new owner.

## Crash after seal consumption

This is an interrupted execution problem.

Do not infer that no side effect happened.

Use receipts, session execution evidence, decision journal, recovery checkpoint,
and target-system evidence.

Strict recovery may require verification or manual review.

## Crash during child execution

Fence expiry alone does not prove that the old child stopped.

The old worker may be partitioned rather than dead.

Production isolation should couple worker loss to process lifecycle where
possible through container ownership, cgroups, process groups, or sandbox
supervision.

The shell's process-group termination controls remain necessary.

## External side effects

Fencing prevents concurrent shell authority.

It cannot make an arbitrary external service exactly once.

Use target idempotency keys, transactional APIs, version preconditions, CAS
updates, or valid compensating operations for external mutations.

## Network partition

A worker that cannot prove its current fence must stop.

Do not assume cached ownership.

Do not downgrade to process-local leases.

Do not mint replacement ownership locally.

Fail closed.

## Backend outage before acquisition

If the fence backend is unavailable, acquisition fails.

No production seal should be issued for a fenced deployment.

This is an availability failure, not permission to bypass the control.

## Backend outage after acquisition

The service calls require_fence before seal consumption.

If current ownership cannot be proven, the operation stops while the seal is
still unused.

## Backend outage during execution

The bounded design intentionally avoids hidden mid-command renewal.

After final validation and seal consumption, the bounded attempt may finish
within its precomputed lease window.

The lease lifetime prevents legitimate reacquisition during that allowed
window.

For extremely sensitive targets, also propagate the fencing token into the
trusted target adapter.

## Downstream fencing

A target system can store the largest accepted fencing token and reject smaller
ones.

This is useful for deployment controllers, migration coordinators, artifact
publishers, and infrastructure wrappers.

Never expose the token to the model.

Pass it through trusted execution adapters only.

## Token monotonicity

A production backend must preserve monotonic fencing generation across restarts,
failover, leader changes, and storage recovery.

Resetting token generation can reanimate stale workers.

Treat token rollback as a security incident.

## Namespace

The default namespace is shell-ai-execution-fence.

Deployments may use a deployment-specific namespace, but request data must not
choose arbitrary namespaces.

Changing namespace creates a new ownership domain.

## Privacy properties

The fence backend sees bounded identifiers and hashes.

It does not need raw prompts, raw model reasoning, child stdout, child stderr,
secret values, or the complete argv.

## Fence evidence

Trusted audit surfaces should record at least fence digest, worker identity,
fencing token, resource key, acquisition time, expiry, and policy digest where
operationally appropriate.

Do not log secret environment values.

## Runtime trust and fencing solve different problems

The fence answers which worker currently owns the plan.

Runtime trust answers whether the worker is still operating under the approved
authority epoch.

Production distributed execution should use both.

## Durable runtime trust pin

RuntimeTrustPinStore persists the expected runtime epoch across process restart.

Without a durable pin, a freshly restarted process could accept a changed
runtime surface as its first local epoch.

That behavior is convenient but not fail closed.

## Trust-pin scope

Choose a scope representing one deployment authority domain, such as production,
canary, a regional production fleet, or a dedicated Jeeves worker pool.

Do not use per-request scopes.

The durable pin preserves deployment continuity.

## Initial durable pin

The first approved deployment computes the runtime epoch, signs revision 1,
writes immutable history, creates the current head with compare-and-swap
semantics, and enters READY only when the durable pin matches.

## Concurrent initial workers

Two workers can start at nearly the same time and sign the same epoch at
slightly different wall-clock times.

Their signed bytes differ even though the authority epoch is the same.

The immutable history winner is canonical.

A losing writer reuses the winner when scope, revision, epoch, predecessor, and
change identity agree.

Different authority state at the same revision is a conflict.

## Explicit rollover

A changed epoch is never automatically repinned.

Rollover requires the expected current revision, the new epoch, a change ID,
and a reason.

The new signed pin references the previous pin digest.

## Signed rollover history

Each durable revision records scope, revision, epoch digest, predecessor digest,
change ID, reason, and wall-clock pin time.

This forms a signed predecessor chain.

Deleting a history revision or changing a predecessor breaks verification.

## Stale rollover

Two concurrent change operations cannot both advance the same expected
revision.

The loser refreshes state and must reconsider the new head.

Do not automatically skip revisions.

## Restart after approved rollover

A worker starting under the newly approved runtime epoch can pin against the
durable rollover head and enter READY.

A worker starting under the old epoch fails.

## Old live worker after rollover

A worker that was already running keeps its original expected epoch.

require_current also checks the durable store.

After rollover, the old worker observes that the durable epoch differs and
degrades before new execution authority is used.

## Durable pin rollback

If the durable trust store is restored to an older snapshot, signed history and
external audit evidence should be compared before execution resumes.

For stronger anti-rollback guarantees, witness the trust-pin head in an
independent system.

## Audit witness

AIAuditWitnessStore provides a monotonic signed witness chain over audit roots.

Each witness can bind runtime trust and release evidence.

This connects what executed, which audit root contains it, which runtime epoch
authorized it, and which release was active.

## Finalization order

The hardened evidence finalization path is session evidence, session journal,
recovery checkpoint, audit anchor, anti-rollback witness, and signed top-level
execution evidence.

Every later layer commits to earlier authority or evidence.

## Signed execution evidence

AIExecutionEvidence can bind provenance, recovery checkpoint, session evidence,
session journal, audit anchor, audit-chain node, runtime trust, authority-health
policy, witness digest, witness sequence, seal ID, quorum digest, and other
release/sandbox identity.

The witness digest and sequence are paired.

One without the other is invalid.

## Recovery checkpoint

AIRecoveryCheckpoint binds session state, session execution evidence, session
journal commitment, release, sandbox binding, runtime trust, and
authority-health policy.

This prevents restart logic from silently resuming under a different authority
surface.

## Strict recovery precedence

Recovery uses conservative precedence.

Integrity uncertainty requires manual review.

Potentially interrupted side effects require verification.

Terminal failure remains terminal.

Authority-surface drift requires replan.

Only lower-severity resumable states remain resumable.

A later drift check must not downgrade a stronger earlier obligation.

## Journal corruption plus trust drift

If journal integrity fails and runtime trust also changed, manual review wins.

Replanning cannot resolve uncertainty about whether evidence was modified.

## Interrupted execution plus trust drift

If execution evidence is missing after an interrupted attempt and runtime trust
also changed, verification wins over simple replan.

Side effects may already exist.

## Authority dependency health

The service checks authority-health dependencies before seal issuance and again
before seal consumption.

This prevents a one-use seal from being burned merely because the coordination
or evidence backend is unhealthy.

The final provenance records the authority-health policy digest.

## Health probe examples

Production probes can cover the release backend, durable trust-pin backend,
quorum store, seal replay registry, fence backend, receipt/journal store, and
audit-witness backend.

Required unhealthy dependencies fail closed.

## Runtime trust evidence

Execution provenance carries the runtime trust digest.

Finalization checks that the caller-supplied runtime trust digest agrees with
provenance before signing evidence.

A mismatch is an evidence-finalization failure.

## Authority-health evidence

Execution provenance also carries the authority-health policy digest.

Finalization rejects a different supplied policy identity.

This proves not only which dependencies were consulted, but under which health
policy they were considered sufficient.

## Operational startup checklist

Verify immutable code revision, active AI policy, tool digest, effect digest,
assurance digest, workspace digest where configured, signed release, model
attestations, durable runtime pin, authority dependency health, fence backend,
audit backend, and replay backend.

Only then enter READY.

## Operational execution checklist

Before fenced execution verify service readiness, runtime epoch, durable trust
pin, release, authority health, plan pin, preconditions, human approval, quorum,
sandbox, fence ownership, seal freshness, and assurance binding.

## Fence acquisition timing

Acquire the fence after review and near execution.

Do not hold distributed ownership during lengthy model planning or human review.

This reduces contention and expiry risk.

## Abandoned fence

If execution is abandoned after acquisition but before execute_sealed receives
the fence, the caller must release it.

The service cannot release an object it was never given.

## Submitted fence ownership

Once a valid fence reaches the sealed execution attempt, the service releases
it in finally regardless of outcome.

This gives one clear transfer-of-ownership point.

## Release promotion while fence held

If release promotion changes runtime trust after fence acquisition, current
fence validation fails.

Release the old fence.

Review or reacquire under the new trust epoch.

Do not carry ownership across deployment promotion.

## Model revision while fence held

A model registry revision changes runtime trust.

The service degrades before execution.

The old fence becomes incompatible with current authority.

## Policy change while fence held

An AI policy or assurance-policy change alters trust identity.

Old fence/seal combinations fail.

## Source drift

The fence does not replace preconditions.

A current worker lease cannot make stale source state valid.

High-risk source work should use immutable snapshots in addition to digest
preconditions.

## Quarantine

Quarantine remains effective after fence acquisition.

If a model, proposal, or command becomes quarantined before process creation,
execution stops and ownership is released.

## Cancellation

Cancellation is orthogonal to fencing.

A child already started under valid authority must still honor cancellation and
process-group termination.

## Recommended metrics

Track acquisition attempts, conflicts, stale-token failures, expiries, renewals,
releases, release failures, held duration, budget utilization, time from fence
acquisition to seal, time from seal to execution, trust-pin rollovers, and
durable-pin verification failures.

Avoid raw prompt or child-output labels.

## Recommended alerts

Alert on repeated stale-fence attempts, token regression, unavailable fence
backend, leases held beyond plan window, high conflict rate for one resource,
seal mismatch caused by fence substitution, trust drift while a fence is held,
and durable trust-pin verification failure.

## Incident: stale worker resumes

Stop uncertain execution, identify the resource and latest token, identify the
stale token, determine child process state, inspect receipts/session evidence,
inspect target-side effects, preserve audit evidence, decide compensation, and
add a regression case.

## Incident: duplicate side effect

Investigate whether the effect occurred before fencing, outside the shell
boundary, through a broken fencing backend, through an execution bypass, through
external retries, or during recovery of a non-idempotent action.

Do not assume the coordination lease alone is the root cause.

## Incident: fence backend rollback

Stop fenced execution.

Fencing-token monotonicity may be broken.

Restore a monotonic generation or establish a new reviewed authority namespace
before execution resumes.

## Incident: trust-pin rollback

Stop new execution, verify signed history, compare deployment release, compare
audit witness state, restore the intended durable head through change control,
then restart workers.

## Incident: signing-key compromise

Freeze trust rollovers and signed authority publication.

Rotate the key through an explicit trust boundary.

Preserve old evidence for forensic verification.

Do not rewrite old history.

## Minimum execution-fence tests

Tests should prove single owner, second-owner conflict, token increment after
reacquire, stale owner rejection, expiry rejection, principal substitution,
worker substitution, trust substitution, release substitution, plan
substitution, TTL lower/upper bounds, policy drift, renewal semantics, direct
execution bypass denial, seal/fence binding, and fence release after failed
execution.

## Minimum durable-pin tests

Tests should prove initial pin, same-epoch idempotence, restart persistence,
changed-epoch rejection, explicit rollover, stale revision conflict, required
change evidence, wrong signing key rejection, history deletion detection,
predecessor tamper detection, old-worker rollover detection, and concurrent
initializer convergence.

## Minimum evidence tests

Tests should prove trust and health policy in provenance, trust and health
policy in recovery checkpoint, trust and health policy in audit anchor, witness
publication, witness-chain verification, witness identity in final evidence,
fresh-reader verification, and root mismatch rejection.

## Minimum recovery tests

Tests should prove matching trust preserves the base recovery action, trust
drift requires replan, authority-health policy drift requires replan, integrity
failure dominates drift, interrupted execution verification dominates replan,
and unrelated global evidence does not invalidate session-scoped commitments.

## Production deployment checklist

Use a durable fenced backend, confirm monotonic token semantics, configure a
worker identity, configure execution assurance, use signed execution seals,
use distributed seal replay protection, configure runtime trust, configure the
durable trust-pin store, configure authority health, verify signed release
state, use durable receipts/journal, use audit anchors, publish audit witnesses,
and persist signed final evidence.

## Fence-policy change checklist

Change fence policy intentionally, expect AssuranceBinding to change, expect old
seals to fail, run the complete fence suite, verify wall-time calculation,
verify maximum TTL, deploy through signed release, and re-pin runtime trust if
the trusted surface changed.

## Trust rollover checklist

Build the intended release, verify provider attestations, verify tool/effect
surface, verify assurance policy, verify trusted workspace, compute the new
epoch, inspect current durable revision, create a change ID, record the reason,
CAS-roll the durable pin, deploy/restart workers, confirm old workers degrade,
and confirm new workers pin the exact approved epoch.

## Shutdown checklist

Stop new admission, drain or cancel bounded execution, release owned fences when
safe, finalize terminal evidence, verify the audit witness, persist recovery
state, then stop the process.

## Design rule: possession is not ownership

A worker must never infer execution ownership from possession of a plan.

It proves ownership with the current fence.

## Design rule: a seal is not a fence

A valid seal is necessary but not sufficient when distributed fencing is
configured.

A valid fence is necessary but not sufficient.

Both controls remain independent.

## Design rule: trust is not permission

Runtime trust identifies the authority surface.

Policy still decides whether execution is allowed.

## Design rule: expiry is not proof of no side effect

A fence expiry cannot prove that the old child did nothing.

Use receipts and recovery verification.

## Design rule: no automatic repin

Do not automatically accept a new runtime trust epoch after restart.

Durable rollovers are explicit change-control events.

## Design rule: no hidden renewal

Do not create background authority loops.

Lease lifetime remains bounded and inspectable.

## Design rule: do not hide progress bugs with larger bounds

If a bounded executor repeatedly hits its substep or progress guard, fix the
underlying progress bug.

Do not simply raise execution or lease limits.

## Design rule: fail closed on coordination loss

Backend unavailability is not permission to downgrade.

Production fenced execution stops.

## Final invariant

Production distributed AI shell execution is permitted only when reviewed plan,
principal, worker identity, release, runtime trust, assurance policy,
approvals, preconditions, sandbox/backend, signed seal, and current fenced lease
all agree on one exact authority surface immediately before process creation.

The resulting execution must then produce durable, signed, rollback-resistant
evidence describing the same authority surface.

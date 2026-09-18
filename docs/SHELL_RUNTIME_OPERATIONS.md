# Shell Runtime Operations Guide

## Objective

Operate the shell execution plane under load while preserving security
invariants.

This guide covers runtime controls rather than policy authoring.

## Startup

Recommended startup sequence is to construct ShellRunner with immutable policy,
construct ShellExecutor, bind a receipt chain, construct ShellService, run
diagnostics, enter ready, then accept dispatch.

ShellService.start follows the diagnostic transition from new to starting to
ready.

If diagnostics fail, the service enters failed.

## Ready requirement

ShellService refuses dispatch before ready.

Outer APIs should translate not-ready into explicit service-unavailable behavior
rather than bypassing the service.

Never create a fallback subprocess path.

## Correlation

Every external operation should have one root correlation ID.

Plan steps derive child correlations.

Keep IDs bounded and non-secret.

Use request ID separately when an external request identity exists.

## Cancellation

Create cancellation token when operation starts.

Store it under a bounded operation identity.

On cancellation set reason, stop new plan steps, reject dispatch before executor,
retain state long enough for caller observation, then remove token at lifecycle
end.

User means caller requested cancellation.

Deadline means operation budget elapsed.

Shutdown means service drain.

Superseded means a newer revision replaced old work.

Dependency means upstream prerequisite invalidated.

Policy means control plane revoked operation.

Internal means runtime failure.

## Deadlines

Use monotonic deadlines.

Do not use wall clock for timeout enforcement.

For each child dispatch clamp timeout to remaining deadline.

If no time remains, fail before process creation.

A longer deadline never widens ShellPolicy timeout.

## Time budgets

Use aggregate TimeBudget when multiple commands or retries share one envelope.

Reserve before attempt.

Record measured duration.

Stop when exhausted.

A time budget is control accounting and does not replace OS CPU limits.

## Concurrency

WeightedConcurrency capacity should reflect intended aggregate in-flight
pressure.

Example weights can assign probes one unit, tests two, and builds four.

Do not allow arbitrary unvalidated caller weights.

When saturated wait with bounded timeout or return overload.

Do not launch a process outside limiter.

## Command budgets

Budgets protect against repeated pressure over time.

Watch starts, failures, runtime, and output.

Budget exhaustion differs from circuit open.

Circuit reacts to failure behavior.

Budget reacts to aggregate consumption.

## Admission leases

Use a lease when duplicate simultaneous execution is undesirable.

Examples include one deployment per environment, one migration per database,
one plan step identity, or one maintenance action.

TTL should exceed handoff time but remain finite.

Renew explicitly.

## Events

ShellEvents is short-lived operational inspection, not durable logging.

Watch for admitted without started, started without terminal, and error spikes.

Reconciler reports some inconsistencies.

## Receipts

Every executed attempt should create a receipt.

ShellService binds its receipt chain to executor if executor had none.

Verify chain periodically.

## Circuits

Circuit breakers live in ShellExecutor.

Open circuit should influence health and status.

Do not bypass an open circuit by changing circuit key per attempt.

Use stable keys.

## Retries

Retry should reflect idempotency.

Read-only probes, compilation checks, and deterministic validation can often be
retried.

Deployments, irreversible migrations, external notifications, and destructive
commands require stronger idempotency design.

## Plans

Plans execute in deterministic dependency order.

Failed dependency normally skips dependent step.

Continue-on-failure should be rare and intentional.

Good uses include collecting diagnostics or independent cleanup.

Bad uses include deploy after failed tests or migration after failed validation.

## Plan versions

Store accepted plans in PlanStore.

Record plan ID, version, and fingerprint.

If a plan changes, create a new version.

Cancel old execution as superseded if necessary.

## Dry run

Dry-run model or user generated plans before expensive execution.

It catches unknown commands, capability failures, argument rejection,
environment rejection, and workspace rejection.

Dry run does not reserve concurrency or leases.

Policy can still change after dry run.

For strong consistency bind policy revision at higher layer.

## Maintenance

During maintenance enter maintenance or draining phase, deny new work, allow or
cancel in-flight work according to policy, capture snapshot, perform change, run
diagnostics, clear window, then return ready.

## Shutdown

Stop public admission.

Cancel nonessential operations with shutdown reason.

Stop worker admission.

Drain bounded plans and queue.

Wait for concurrency used to reach zero.

Reconcile.

Verify receipts.

Capture snapshot.

Transition stopping then stopped.

If drain exceeds deadline capture incident and preserve evidence.

## Saturation

Signals include zero concurrency availability, worker backpressure, high queue
depth, exhausted command budgets, and high latency.

Distinguish healthy load from failures before scaling.

Do not widen shell limits as first response.

## Failure spike

Inspect circuits, failure ledger, recent receipts, return codes, timeouts,
policy rollout, executable health, and dependencies.

If a new policy caused failure, use rollback runbook.

## Timeout spike

Possible causes include dependency outage, deadlock, host overload, timeout
narrowing, command behavior change, environment change, or workspace I/O.

Do not automatically widen timeout.

Investigate evidence.

## Output-limit spike

Possible causes include verbose mode, child loop, warnings, error flood, command
version change, or attacker-controlled amplification.

Inspect only safely classified samples.

## Budget exhaustion

Start exhaustion with low failures usually means demand pressure.

Failure exhaustion means repeated bad outcomes.

Runtime exhaustion means long-running pressure.

Output exhaustion means high volume.

## Incidents

Open incident when runtime state cannot be reconciled.

Attach snapshot digest, receipt root, correlation, command, policy revision,
rollout or change identity.

Acknowledge, mitigate, then close after state is understood.

## Reconciliation

Run reconciliation after crash, forced shutdown, policy rollout, receipt anomaly,
or concurrency anomaly.

Findings are not auto-fixed.

## Snapshots

Capture before and after meaningful changes.

Snapshot digest can be logged in change systems.

Snapshot contains bounded control state but no child output.

## Output handling

Classify before retention.

Public and internal output can retain bounded bytes.

Sensitive and secret defaults retain no bytes.

For debugging secret output use explicit incident procedure, minimum scope,
restricted access, and short retention.

## Feature gates

Use feature gates for behavior rollout.

Do not leave permanent partial gates without owner.

After rollout remove gate or set stable documented state.

## Namespaces

Namespaces can separate build, tests, maintenance, deployment, and agent tools.

A namespace denial should fail before execution.

## Approvals

Use approvals for destructive maintenance, deployment, credential-affecting
actions, and broad filesystem mutation.

Bind exact fingerprint.

Use short TTL.

Consume once.

## Cache

ExecutionCache is metadata-only.

Do not use it as correctness cache unless deterministic behavior and cache key
state are proven.

A cache hit does not recreate stdout.

## Tracing

Use spans for latency and control diagnostics.

Do not add raw output, secrets, or arbitrary user strings as attributes.

## Retention

Monitor retained byte capacity.

Prune expired entries from an explicit service loop.

Use external storage for long-term artifacts.

## Worker interaction

Worker plane chooses placement and queue custody.

Shell service owns execution boundary.

Worker healthy plus shell denied usually indicates policy or admission problem.

Worker stale plus shell healthy indicates worker ownership problem.

Both failing may indicate host failure.

## Dashboard

Recommended shell fields include service phase, policy health, receipt validity,
open circuits, concurrency used and available, exhausted budgets, open incidents,
failure counts, and receipt root.

Recommended worker fields include registered, enabled, healthy, stale, queued,
claimed, backpressure, recovery count, and quarantined workers.

## Quick check: nothing runs

Check service ready, maintenance, feature gate, namespace, capability grant,
command catalog, circuit, command budget, concurrency, worker health, and stale
queue claim.

## Quick check: too much runs

Check concurrency capacity, worker parallelism, per-principal quota, command
start budget, retry count, duplicate leases, and schedule release loop.

## Quick check: wrong thing runs

Check logical command mapping, executable registry, command catalog, plan
fingerprint and version, namespace prefix, stale plan, and policy revision.

## Principle

Operational pressure must not cause security boundaries to disappear.

Under load fail closed or degrade explicitly.

Never introduce an alternate subprocess path to keep work moving.

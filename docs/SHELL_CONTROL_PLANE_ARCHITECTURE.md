# Shell Control Plane Architecture

## Scope

The shell execution plane is the repository boundary for invoking host
processes. The control plane around that boundary exists to make process
execution governable, inspectable, bounded, and recoverable without weakening
the runner's core rules.

The architectural rule is simple: higher-level orchestration may decide when and
why to execute, but only ShellRunner decides how a host process is created.

That separation matters because orchestration grows quickly. It gains queues,
workers, retries, plans, workflows, feature gates, maintenance modes, and service
APIs. Without a stable execution boundary those features can become alternate
process-spawn paths. Skeleton intentionally prevents that.

## Hard process boundary

ShellRunner remains the only low-level process creation primitive in the shell
package.

Its responsibilities include:

- argv-only process creation
- explicit shell=False
- absolute executable resolution
- no ambient PATH lookup
- bounded working directory
- bounded environment
- bounded stdin
- bounded output
- bounded timeout
- process-group termination where supported
- closed file descriptors
- bounded child lifecycle

Everything else composes around those guarantees.

## ShellExecutor

ShellExecutor is the policy and evidence boundary immediately above the runner.

It owns capability grants, argument policy, environment policy, workspace
policy, retry policy, circuit breakers, audit events, telemetry, hooks,
execution receipts, and session aggregate budgets.

A feature that needs command execution should prefer calling ShellExecutor over
calling ShellRunner directly unless it is itself part of the executor
implementation.

## Dispatch layer

ShellDispatcher adds admission-time runtime controls around ShellExecutor.

The dispatch sequence is:

1. check cooperative cancellation
2. clamp command timeout to deadline
3. inspect per-command aggregate budget
4. acquire admission lease
5. emit admitted event
6. acquire weighted concurrency permit
7. reserve command start budget
8. re-check cancellation
9. call ShellExecutor
10. record command budget result
11. emit completion or error event
12. release concurrency permit
13. release admission lease

The lease and permit are control-plane tokens. Neither authorizes a command that
ShellExecutor would otherwise reject.

## ExecutionContext

ExecutionContext carries bounded identity across the control plane.

Fields include correlation ID, principal, request ID, parent correlation ID,
low-cardinality tags, and bounded string attributes.

Context is immutable. A child context records its parent correlation ID. Plan
steps derive step-level correlations from the parent plan correlation. Context
fingerprints are deterministic.

Do not place secrets in context attributes. Do not place argv, output, raw
environment values, or file contents in context tags.

## Cancellation

Cancellation is cooperative before child process creation.

CancellationToken provides one-way state, reason, bounded detail, monotonic
timestamp, wait support, and explicit active-state validation.

Cancellation reasons include user, deadline, shutdown, superseded, dependency,
policy, and internal.

Once cancellation is set it cannot be cleared.

A registry provides named bounded cancellation tokens.

The runner's timeout and output termination remain authoritative for a process
that already exists.

Future live child cancellation should integrate with the runner or executor
boundary rather than killing arbitrary PIDs from higher layers.

## Deadlines

A Deadline is an absolute monotonic expiry.

DeadlineClock creates a deadline after a duration, reports remaining time, fails
when expired, and clamps requested command timeout.

A plan-wide deadline should be passed to every step. Each step receives at most
the remaining deadline.

A command must never widen its configured policy timeout because a caller has a
longer deadline.

## Aggregate time budgets

TimeBudget records aggregate consumed duration.

It is useful when a plan has a total runtime envelope, a service request executes
multiple commands, retries share one total budget, or maintenance work has a
bounded window.

Reservation returns the smaller of requested and remaining duration. Recording
can exhaust the budget.

Time budgets are accounting controls, not OS-level CPU limits.

## Weighted concurrency

WeightedConcurrency controls aggregate in-flight work.

A permit has permit ID, weight, owner, and acquisition time.

The semaphore supports nonblocking acquisition, blocking acquisition, bounded
wait timeout, stale-token rejection, owner inspection, and snapshots.

Weight lets expensive jobs consume more than one logical slot. Weight remains a
scheduling concept and does not replace process-level resource limits.

## Admission leases

AdmissionLeases protect dispatch keys from simultaneous execution.

A lease contains lease ID, key, principal, command, acquisition time, expiry,
and revision.

Lease renewal creates a new revision. An old revision cannot release a renewed
lease. Expired leases are pruned before acquisition and lookup.

Typical keys include correlation ID, plan ID plus step ID, idempotency key, and
scheduled execution key.

## Command budgets

CommandBudgets enforce fixed-window aggregate limits by logical command.

Limits include starts, failures, runtime milliseconds, output bytes, and window
length. Policies may be overridden per command.

Budgets are low-cardinality by logical command name. Do not key command budgets
by arbitrary argv strings.

## Events

ShellEvents is a bounded synchronous control-plane event stream.

Events contain sequence, kind, monotonic observation time, correlation ID,
logical command, and bounded data.

Event sink exceptions are isolated.

Important dispatch events include shell.dispatch.admitted,
shell.dispatch.started, shell.dispatch.completed, and shell.dispatch.error.

Events are diagnostic and control evidence. Execution receipts remain the
stronger per-attempt evidence record.

## Tracing

ShellTracer provides bounded span storage.

Spans contain span ID, trace ID, parent span ID, name, start time, optional
finish time, bounded string attributes, and error type.

The tracer does not export automatically. An outer observability adapter may
export spans.

Avoid high-cardinality attributes.

## Execution plans

ExecutionPlan is an immutable dependency graph.

Each PlanStep has step ID, ShellCommand, dependency set, and
continue-on-failure flag.

Plan validation rejects empty plans, duplicate step IDs, unknown dependencies,
self-dependencies, and dependency cycles.

Topological order is deterministic.

Plan fingerprints include plan ID, command logical name, argv, cwd,
environment key names, stdin length, timeout, allowed return codes,
dependencies, and metadata.

Environment values are not included in plan fingerprints. Raw stdin is
represented only by length.

## Plan execution

ShellPlanExecutor runs steps in deterministic topological order.

For each step it checks cancellation, inspects dependency outcomes, skips a
blocked step unless continue-on-failure, derives child execution context,
dispatches through ShellDispatcher, and records state.

Step states are pending, succeeded, failed, skipped, and cancelled.

The plan executor does not call subprocess.

## Plan store

PlanStore keeps immutable plan versions.

A version contains plan ID, version, fingerprint, plan, creation time, and a
superseded flag.

Identical fingerprints are idempotent. Changed fingerprints create a new
version. Expected-version compare-and-swap protects concurrent updates.

## Dry run

ShellDryRun invokes command admission only.

Dry run never creates a process, invokes ShellRunner, invokes ShellExecutor, or
mutates receipt chains.

It can inspect one command or all steps in a plan.

Dry run is suitable for UI validation, agent planning, CI manifest validation,
and policy migration review.

Dry-run success does not reserve concurrency, quotas, or leases.

## Feature gates

Feature gates support deterministic staged behavior changes.

Gate state includes enabled flag, rollout percentage, explicit allow principals,
explicit deny principals, and metadata.

Principal bucketing uses a deterministic SHA-256 bucket.

Explicit deny wins. Explicit allow can enable a principal even if global enabled
is false.

Gates should control control-plane behavior, not bypass command capability
checks.

## Namespaces

ShellNamespace groups principals and command prefixes.

A namespace can restrict allowed principals, logical command prefixes, and
enabled state.

Namespace authorization occurs before command execution.

Namespace membership is not a replacement for capability grants.

Use namespaces to reduce accidental cross-subsystem execution.

## Approvals

ApprovalRegistry supports short-lived one-use approval records.

Approval binds principal, command, command fingerprint, approver, creation time,
and expiry.

Consumption marks the approval unusable.

An approval cannot be replayed against a different principal, command, or
fingerprint.

Approvals are optional policy gates for particularly sensitive maintenance or
deployment commands.

## Change control

ChangeControl models governance over policy and plan changes.

States are proposed, approved, rejected, applied, and superseded.

Change payload is represented by a digest. The control plane does not need to
retain secret change payload data.

Multiple unique approvals can be required. Duplicate approval by the same actor
is not double-counted.

## Policy store

PolicyStore tracks immutable ShellPolicy revisions.

Revision starts at one. Compare-and-swap requires the expected current revision.

Each revision records a policy fingerprint. History can be inspected by
revision.

## Policy rollout

PolicyRolloutManager models staged rollout.

Phases are prepared, canary, broad, complete, and rolled back.

Canary membership is deterministic by rollout ID plus principal.

Rollback restores the base policy as a new PolicyStore revision.

Rollout records retain base and target revision identities.

## Policy health

Policy health validates current filesystem reality against ShellPolicy.

Checks include registered executable still exists, executable is a file,
executable permission, executable symlink warning, cwd root still exists, cwd
root is directory, cwd root symlink warning, and inherited environment
informational finding.

Health inspection performs no child execution.

## Contract linting

CommandContractLinter reviews CommandDefinition surfaces.

Current findings include stdin enabled without extra command-specific capability,
nonzero success enabled without extra command-specific capability, unusually
large argv count, unusually large argv byte budget, high-cardinality environment
allowlist, and environment inheritance.

Contract linting is advisory except for structurally invalid definitions, which
the data model rejects.

## Compatibility

ShellCompatibility checks whether current policy and catalog satisfy a caller's
required schema and surface.

Requirements may include schema range, command names, environment key
availability, and prohibition on environment inheritance.

Compatibility checks perform no execution.

## Migration planning

ShellMigrationPlanner compares old and new policy and catalog.

Risk classes are safe, review, and breaking.

Safe examples include timeout narrowing, output limit narrowing, inherited
environment narrowing, and adding an isolated command.

Review examples include executable path change, timeout widening, output
widening, environment key addition, inherited environment widening, and cwd root
addition.

Breaking examples include executable removal, environment key removal, cwd root
removal, and command removal.

Migration output should be included in policy change review.

## Isolation requirements

IsolationRequirement describes the environment expected around execution.

Levels are host, workspace, and sandboxed.

Requirements can include private temporary directory, clean environment,
read-only source tree, network prohibition, home visibility prohibition, and
allowed write roots.

The current module is declarative and inspectable.

A platform-specific sandbox adapter can enforce these requirements later. Such
an adapter must not weaken ShellRunner's existing process rules.

## Output classification

Output is classified separately from execution success.

Classes are public, internal, sensitive, and secret.

Classification may use deterministic patterns.

Retention policy decides whether bytes are retained.

Sensitive and secret defaults retain digest but not bytes.

## Output retention

OutputRetentionStore is bounded by item count, total retained bytes, and per-item
expiry.

It stores only the bytes already allowed by OutputRetentionPolicy.

It should not become an unbounded log store.

## Execution cache

ExecutionCache stores deterministic-result metadata only.

It stores command, return code, success flags, byte counts, stdout and stderr
digests, time bounds, and hit count.

It deliberately does not store stdout or stderr bytes.

Only callers that can prove a command is safely cacheable should use it.

## Receipts

ExecutionReceipt remains the canonical execution evidence.

Receipt fields include receipt ID, logical command, correlation ID, fingerprint,
wall-clock timestamps, duration, return code, success state, timeout state,
output-limit state, stdout and stderr byte counts, attempt, and bounded metadata.

ReceiptChain hashes receipts into a tamper-evident chain.

## Attestations

HMACAttestor adds keyed integrity over canonical payloads and receipts.

The key is not serialized.

Attestation contains key ID, algorithm, payload digest, and HMAC signature.

This is symmetric integrity evidence, not public-key nonrepudiation.

## Replay verification

EvidenceReplay verifies historical evidence without executing commands.

It can verify receipt chain integrity and per-receipt HMAC attestations.

Replay statuses include verified, invalid chain, invalid attestation, and
missing attestation.

Replay must never become re-run command.

## Result indexing

ReceiptIndex provides bounded receipt metadata queries.

Queries can filter command, correlation ID, success, timeout, and minimum
attempt.

The index does not alter the receipt chain.

## Execution history

ExecutionHistory provides bounded history summaries and query.

Summary includes total receipts, success and failure counts, timeout count,
output-limited count, and per-command counts.

This layer is useful for operator views.

## Failure ledger

ShellFailureLedger records low-cardinality failure classification.

Kinds include policy, capability, argument, environment, workspace, timeout,
output limit, return code, circuit, rate limit, budget, concurrency,
cancellation, and internal.

Failure detail is bounded.

Do not copy raw child output into failure detail.

## Incident registry

IncidentRegistry records shell incidents.

States are open, acknowledged, mitigated, and closed.

Evidence is bounded serializable metadata.

Incidents should reference receipt IDs, correlation IDs, snapshot digests, and
failure classifications rather than duplicating secret output.

## Reconciliation

ShellReconciler checks cross-component control-plane consistency.

Current checks include receipt chain integrity, concurrency overcommit, permit
accounting mismatch, exhausted command budgets, internal failure presence,
terminal dispatch events without starts, and starts without terminal events.

Reconciliation does not repair state automatically.

## Shell diagnostics

ShellDiagnostics combines policy health, receipt integrity, cancellation state,
concurrency saturation, and command budget exhaustion.

Diagnostic findings are operator-facing.

## Snapshots

ShellSnapshotter captures aggregate shell status, diagnostics, cancellation
states, concurrency state, command budget usage, and receipt root.

Snapshots have deterministic digests for handoff and reference.

A snapshot is evidence, not an authority token.

## Shell service

ShellService composes the control plane around an existing ShellExecutor.

Service lifecycle states are new, starting, ready, draining, maintenance,
stopping, stopped, and failed.

Start runs diagnostics before entering ready.

Dispatch and plan execution require ready state.

Constructing the service does not start background work.

The service binds its receipt chain to the executor when the executor does not
already have one.

## Maintenance windows

ShellMaintenance provides explicit admission holds.

A window can scope by command prefix, principal, and interval.

A window can be observational or blocking.

Maintenance scheduling uses monotonic time.

## Resource estimates

ShellResourceEstimator estimates worst-case requested resource envelopes.

Per command it estimates command count, attempt count, timeout sum, input bytes,
policy max output bytes, requested environment bytes, and argv bytes.

Plan estimates sum step estimates.

Estimates are planning values, not guarantees.

## Core composition rule

A high-level shell request should conceptually pass through namespace, feature
gate, maintenance, change and approval gates where required, dry-run and
admission, cancellation and deadline, command budget, admission lease, weighted
concurrency, ShellExecutor, ShellRunner, receipt and evidence,
classification and retention, then history, reconciliation, and diagnostics.

Not every request needs every optional gate.

No optional gate may bypass ShellExecutor or ShellRunner.

## No hidden background execution

The control plane is intentionally explicit.

Cancellation registry, deadline clock, concurrency, admission leases, command
budgets, feature gates, policy rollout, plan store, change control, maintenance,
incidents, retention, tracing, events, and reconciliation do not create hidden
timers or worker loops.

An outer service may poll or schedule these components. Its lifecycle must be
explicit.

## Extension guidance

When adding shell-plane functionality ask whether the feature creates a child
process, introduces another executable resolver, parses shell text, inherits
ambient environment, creates a hidden thread, retains unbounded output,
introduces an unbounded identity key, widens policy implicitly, permits stale
tokens to mutate current state, or can replay historical evidence as execution.

If any answer is risky, keep the feature outside the process boundary and reuse
the existing token and policy primitives.

## Design conclusion

The shell plane is not a command helper.

It is an authority and evidence system around host process creation.

The runner constrains execution. The executor constrains policy. The control
plane constrains orchestration. The worker plane constrains distribution.

Receipts, attestations, snapshots, histories, and incidents preserve evidence.

Those layers should remain separable so security review can reason about each
boundary independently.

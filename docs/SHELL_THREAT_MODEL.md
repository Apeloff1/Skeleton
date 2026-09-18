# Shell Execution Plane Threat Model

## Purpose

This threat model documents attacker-controlled inputs, trust boundaries, abuse
cases, required mitigations, and residual risks for Skeleton host process
execution.

It covers direct shell execution and the worker and control planes layered above
it.

Callers may include ordinary application code, plugins, agent tool invocations,
model-generated plans, user-provided arguments, scheduled workflows, CI jobs,
and maintenance operators.

Not every caller is equally trusted.

The shell plane therefore treats execution as capability authority rather than
string processing.

## Security objectives

Primary objectives are preventing shell injection, executable substitution,
ambient PATH execution, cwd escape, uncontrolled environment inheritance,
unbounded argv, input, output, or runtime, capability escalation, stale ownership
replay, evidence tampering, and secret leakage into logs or metrics.

## Trust boundary: caller to command model

The caller may supply logical command name, argv values, cwd request,
environment values, stdin bytes, timeout, and allowed success return codes.

These fields are data.

They must never be concatenated into shell text.

## Trust boundary: command model to ShellExecutor

ShellExecutor checks capability grant, command-specific argument policy,
environment policy, workspace policy, retry authority, circuit state, and
session budget.

Failure at this boundary must stop before ShellRunner.

## Trust boundary: ShellExecutor to ShellRunner

ShellRunner accepts prepared command data but independently enforces ShellPolicy.

Defense in depth is intentional.

## Trust boundary: ShellRunner to operating system

This is the final process boundary.

Required properties include argv vector, no shell, absolute executable, bounded
cwd, bounded env, bounded stdin, bounded output, bounded runtime, and
process-group termination.

## Trust boundary: control plane to ShellExecutor

Dispatcher, plan executor, workers, schedulers, and services can choose when to
call ShellExecutor.

They do not gain a separate process-spawn primitive.

## Trust boundary: worker to queue

Queue ownership is protected by claim IDs.

Worker identity alone cannot complete a queue item.

## Trust boundary: evidence

Receipts, chains, attestations, snapshots, and journals should verify what
happened without containing secret child output by default.

## Threat: shell injection

An attacker may supply semicolons, pipes, ampersands, redirections, command
substitutions, quotes, newlines, wildcards, and option-looking values.

Mitigation is argv execution with shell=False.

No shell text exists.

Repository scanners reject shell execution and definite string command builders.

Residual risk remains when the explicitly authorized executable itself
interprets a string as code or shell syntax.

An interpreter with broad arguments is therefore a command-contract risk.

Use narrow ArgumentPolicy for untrusted callers.

## Threat: executable substitution

An attacker may try to choose a path or rely on malicious PATH.

Mitigation is logical command names mapped to resolved absolute files.

No runtime PATH lookup is required.

Residual risk is on-disk executable replacement after registration.

Policy health detects missing paths and basic filesystem changes.

High-assurance deployments can add file digest or artifact provenance binding.

## Threat: working-directory escape

An attacker may request cwd outside approved workspace using parent traversal,
absolute paths, symlinks, or replaced directories.

Mitigation is resolved cwd containment under configured roots plus optional
WorkspacePolicy narrowing.

Residual race risk can remain on hostile mutable filesystems.

Mount namespace or fd-based containment can provide stronger isolation.

## Threat: environment injection

An attacker may supply high-impact variables such as PATH, PYTHONPATH,
LD_PRELOAD, DYLD variables, NODE_OPTIONS, language startup hooks, proxy settings,
or credentials.

EnvironmentPolicy is default deny.

ShellPolicy allowed_env is explicit.

Inherited environment is explicit per key.

Values and total child environment are bounded.

Residual risk remains for the semantic power of a permitted environment key.

Command owners must understand each allowed key.

## Threat: inherited secrets

A child might receive parent credentials unintentionally.

Full environment inheritance is not default.

EnvironmentPolicy selects inherited keys.

Policy health reports inheritance.

Migration planner marks inheritance widening for review.

## Threat: stdin abuse

Large or unexpected stdin can drive parser bugs or blocking behavior.

stdin requires explicit capability in ShellExecutor.

CommandDefinition can disable stdin.

ShellPolicy bounds input bytes.

ShellRunner writes bounded bytes and closes the pipe.

## Threat: output flooding

A child can write unbounded stdout or stderr.

ShellRunner applies a combined output byte budget, drains pipes, and terminates
the child process group on breach.

Receipt records output-limited state and byte counts.

## Threat: timeout evasion

A child can fork descendants or ignore graceful termination.

On supported POSIX systems the runner creates a process group or session.

Timeout termination can escalate to kill.

Higher-level deadlines only clamp timeout downward.

## Threat: return-code widening

A caller could mark arbitrary nonzero return codes successful.

Nonzero success requires capability.

CommandDefinition may disable it.

Allowed return-code set is bounded.

## Threat: retry amplification

One failed command can become many attempts.

Retry requires capability.

RetryPolicy has bounded attempts and sleep.

Session budgets, command budgets, and circuits constrain aggregate impact.

## Threat: concurrency amplification

A caller may launch many commands.

WeightedConcurrency bounds in-flight dispatch.

Worker capacity bounds distributed work.

Per-principal quotas and worker backpressure further constrain admission.

## Threat: stale admission lease replay

An old holder may try to mutate renewed lease state.

AdmissionLease has revision.

An old revision cannot release the renewed lease.

## Threat: stale queue claim

A worker dies, claim is recovered, then old worker later completes item.

Recovery creates a fresh runnable queue generation with cleared claim ID.

Old QueueItem fails transition validation.

## Threat: heartbeat replay

A stale worker may replay prior heartbeat.

Heartbeat sequence must increase within generation.

Generation rollback fails.

Replacement uses a higher generation.

## Threat: protocol replay

An old worker message can be resent.

ProtocolGuard stores generation and last sequence.

Same-generation non-increasing sequence fails.

Older generation fails.

## Threat: policy race

Concurrent policy editors can overwrite each other.

PolicyStore uses revision compare-and-swap.

PlanStore and WorkerStateStore use equivalent version protection.

## Threat: unsafe policy rollout

Broad policy widening could reach all principals immediately.

PolicyRollout supports deterministic canary and staged phases.

Migration planner classifies widening and breaking changes.

ChangeControl can require approvals.

Feature gates can further isolate behavior rollout.

## Threat: approval replay

Approval for one command may be reused for another.

ExecutionApproval binds principal, command, and fingerprint.

Approval has TTL and one-use consumption.

## Threat: namespace confusion

One subsystem may run another subsystem's commands.

ShellNamespace can bind principals and command prefixes.

Namespace authorization remains additive to capability checks.

## Threat: maintenance bypass

New commands may enter during a drain.

ShellMaintenance can deny new admission by command prefix and principal.

Service lifecycle includes maintenance and draining states.

## Threat: evidence tampering

Receipt data may be modified after execution.

ReceiptChain hashes sequence, prior hash, and receipt.

Verification recomputes the chain.

HMACAttestor can provide keyed integrity.

WorkerJournal provides separate worker-event integrity.

## Threat: evidence replay becomes execution

A replay tool might accidentally rerun historical commands.

EvidenceReplay accepts receipt and attestation data and has no runner or executor
dependency.

Replay means verification only.

## Threat: secret output leakage

A secret can appear in stdout and get copied into logs, metrics, exceptions, or
incidents.

ExecutionReceipt stores byte counts rather than output content.

ShellExecutionError avoids child output.

Failure ledger detail is bounded.

OutputClassifier can classify sensitive or secret output.

Retention defaults keep no sensitive or secret bytes.

ExecutionCache stores output digests and counts only.

## Threat: metric cardinality

A caller may inject unique argv or correlation values into metric keys.

Core telemetry keys by logical command.

Worker metrics key by worker ID.

Control events are bounded rings rather than metric dimensions.

## Threat: incident evidence overflow

A caller may trigger huge evidence payloads.

Incident evidence field count and summaries are bounded.

Raw output should not be put in incident evidence.

## Threat: unbounded history

A long-running service can accumulate receipts, events, traces, failures, and
output.

Stores are explicitly bounded or intended for external bounded persistence.

Operators must select deployment-appropriate limits.

## Threat: hidden background work

Constructing a helper could silently start polling or execution.

Control-plane primitives are synchronous and passive.

No hidden daemon is started by constructors.

Scheduling requires explicit polling or release.

Workers are cooperative unless an outer service deliberately adds concurrency.

## Threat: scaling recommendation becomes authority

Autoscaling logic might execute infrastructure commands directly.

WorkerScaler and WorkerBalancer only return recommendations.

An infrastructure adapter must independently pass normal shell policy.

## Threat: cache confusion

A result for one context could be reused for another.

ExecutionCache key is caller-provided fingerprint and stores metadata only.

Only proven deterministic commands should use it.

Future cache keys should include policy and command-contract identity.

## Threat: plan mutation after approval

Approved plan content might change before execution.

ExecutionPlan is frozen.

PlanStore records version and fingerprint.

Approval can bind fingerprint.

ChangeControl stores payload digest.

## Threat: dependency bypass

A plan step might execute despite failed prerequisite.

ShellPlanExecutor skips dependency-blocked steps unless
continue-on-failure is explicit.

That flag is part of plan fingerprint.

## Threat: deadline widening

A caller might provide a long deadline to obtain more execution time.

Dispatcher clamps requested timeout to remaining deadline.

ShellPolicy max timeout still applies.

Deadlines never widen policy.

## Threat: cancellation race

Cancellation can arrive between admission and execution.

Dispatcher checks cancellation before admission and again after concurrency
permit acquisition before calling executor.

Cancellation after child creation is currently handled by bounded timeout and
runner termination.

Future live cancellation should integrate at runner child-lifecycle boundary.

## Threat: fingerprint secret exposure

ShellPolicy fingerprint contains executable paths, cwd roots, allowed env key
names, inherited env key names, and numeric limits.

It does not include runtime environment values.

Plan fingerprint input includes argv and cwd, so secrets should not be placed in
argv.

Environment values are represented only by key names in plan shape.

## Threat: interpreter exposure

An argv-safe interpreter can still execute arbitrary code if its arguments are
broad.

Use command-specific ArgumentPolicy.

Prefer narrow wrappers for untrusted tool surfaces.

Require stronger capability or approval for sensitive interpreters.

## Threat: child reads home

Core runner constrains cwd but is not a complete filesystem sandbox.

IsolationRequirement can declare home invisibility.

OS-level sandbox adapter is required for enforcement.

This is a residual risk on plain host execution.

## Threat: child network access

Core runner does not implement network namespaces.

IsolationRequirement can declare network prohibition.

OS or container enforcement is required.

This is a residual risk on ordinary host execution.

## Threat: CPU, memory, disk, fd exhaustion

Runner bounds time, input, and output but does not universally enforce every OS
resource.

Session and worker budgets reduce amplification.

Future platform adapters can enforce memory, CPU, process, fd, and disk quotas.

Those adapters must preserve argv and no-shell rules.

## Threat: symlink and TOCTOU races

Executable registration resolves strict path.

Policy health warns on symlink paths.

Workspace paths are normalized.

Residual time-of-check versus time-of-use risk remains on hostile mutable
filesystems.

Stronger fd-based execution or sandbox mounts can harden this.

## Threat: subprocess scanner bypass

A developer may introduce another process API or alias.

Repository-wide static process safety scanning covers backend, skeleton, and
scripts.

It rejects shell execution, unsafe aliases, and definite string command
builders.

Regression tests cover alias, partial, dynamic lookup, and similar bypasses.

## Threat: test bypass

A shell feature might be added without tests.

Canonical quality gate runs every skeleton/testing/test_shell_*.py file.

The backend security regression gate runs the same shell glob again.

New tests using that convention automatically join both gates.

## Threat: policy health drift

An executable may disappear or a cwd root may be removed after service startup.

Policy health can be run repeatedly.

ShellService startup runs diagnostics.

Operators should run health after host maintenance and policy rollout.

## Threat: broad feature gate

A 100 percent gate can expose new control behavior rapidly.

Feature gates do not bypass security, but they can create operational risk.

Use canary percentages and explicit principals for high-risk behavior.

## Threat: retention misconfiguration

Internal output retention can fill memory or preserve sensitive data.

Retention store bounds item count and total bytes.

Classification should happen before storage.

Sensitive and secret defaults retain no bytes.

## Threat: HMAC key leakage

If attestation key leaks, attacker can forge HMAC evidence.

Store key outside receipts and source control.

Rotate by key ID.

Treat HMAC as symmetric integrity, not public identity proof.

## Threat: change-control metadata leak

Change metadata can accidentally contain secrets.

Metadata is bounded but not automatically redacted.

Store references and digests instead of secret payloads.

## Threat: service not-ready bypass

An outer API might bypass ShellService because it is not ready.

Do not do this.

Not-ready should be an explicit service-unavailable response.

Direct fallback subprocess execution is prohibited.

## Threat: worker healthy implies command trusted

Worker health only means liveness.

It does not authorize a command.

Command still passes namespace, capability, argument, environment, workspace,
executor, and runner policy.

## Security severity guidance

Critical issues include shell execution, arbitrary executable path, stale claim
mutation after recovery, capability widening, unbounded child output, secret
output copied broadly, or corrupted receipt chain silently accepted.

High issues include cwd escape, environment injection, policy CAS bypass,
approval replay, generation rollback, or sensitive maintenance bypass.

Medium issues include observability drift, retention misconfiguration, and
bounded scheduling fairness defects without authority impact.

Low issues include cosmetic status formatting.

## Security review checklist

Before merging a shell feature verify no new subprocess path outside runner, no
shell=True, no shell string builder, no PATH executable lookup, no unrestricted
environment inheritance, no unbounded stdin, output, or runtime, no hidden
background thread, stale tokens are rejected, registries are bounded, history
stores are bounded, child output is not copied into broad errors or metrics,
policy widening is explicit, and failure and tamper tests exist.

## Residual risk statement

Skeleton's shell plane substantially reduces command-injection and orchestration
risk but is not equivalent to a hardened OS sandbox.

Plain host execution still shares the host kernel, filesystem, and network
according to the invoked process identity.

For adversarial untrusted code, use a dedicated sandbox, container, or VM
boundary integrated underneath the same command policy and evidence model.

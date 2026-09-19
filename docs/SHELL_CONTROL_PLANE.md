# Skeleton Shell Control Plane

## Purpose

The shell subsystem is the repository's explicit boundary between Skeleton/Jeeves logic and host process execution. It exists so code that genuinely needs a compiler, test runner, version-control client, local interpreter, or other host tool does not need to construct an ad-hoc `subprocess` policy every time.

The design is intentionally conservative. A shell command is not a string. It is a logical command name plus an argument vector, a bounded working directory, a bounded environment, optional bounded stdin, an execution budget, and a caller capability grant.

The control plane never turns untrusted text into executable paths. Executable authority is installed ahead of time by trusted application configuration.

## Design goals

1. Keep `shell=False` and argv-only execution universal.
2. Make executable selection explicit and independent from ambient `PATH`.
3. Make environment inheritance opt-in rather than default.
4. Keep process cwd inside explicit roots.
5. Bound time, output, input, environment, and argument resources.
6. Keep raw secrets out of audit events, receipts, exception text, and status responses.
7. Make policy narrowing easy and policy widening visible.
8. Provide a single executor that higher-level batches, pipelines, and tool adapters reuse.
9. Give Jeeves a queue/control surface without creating a hidden background scheduler.
10. Preserve the existing repository-wide static subprocess scanner as an independent line of defense.

## Layer model

### Layer 1: primitive runner

`ShellRunner` owns the actual process spawn. It receives `ShellCommand` and enforces `ShellPolicy`.

The primitive runner guarantees:

- argv vector invocation;
- literal `shell=False`;
- registered absolute executable paths;
- no ambient command lookup;
- cwd confinement;
- environment-key allowlisting;
- opt-in parent environment inheritance;
- argument count and byte limits;
- stdin byte limits;
- combined stdout/stderr capture limits;
- wall-clock timeout limits;
- process-group termination on POSIX timeout/output overflow;
- no raw child output in raised execution errors.

The runner is intentionally unaware of retries, sessions, queues, pipelines, agent semantics, audit retention, and policy manifests.

### Layer 2: command contracts

`CommandDefinition` binds one registered executable to:

- an `ArgumentPolicy`;
- an `EnvironmentPolicy`;
- required capabilities;
- command-specific timeout ceiling;
- stdin permission;
- nonzero-success permission;
- descriptive metadata and tags.

`CommandCatalog` is default-deny. A command that is executable at the primitive policy level is not automatically admitted through the command catalog.

This separation matters because executable authority and application-level command authority are different decisions. A Python interpreter can be registered for multiple safe tasks while some arguments remain forbidden on an agent-facing surface.

### Layer 3: admission and preflight

`CommandAdmission` checks a `ShellCommand` without spawning it.

Admission verifies:

- the logical command exists in the catalog;
- the caller grant contains the command's required capabilities;
- custom environment requires `custom_env`;
- stdin is allowed by both capability and command definition;
- nonzero accepted return codes are allowed by both capability and command definition;
- timeout is within the command definition;
- argv satisfies the argument grammar;
- environment values satisfy the environment grammar;
- cwd satisfies workspace confinement.

`PreflightAnalyzer` applies the same admission contract to a set of commands or a full pipeline and returns a non-executing report.

Preflight reports command counts, argument counts, environment-key counts, and per-item admission decisions. It never executes a probe to decide whether authority should be granted.

### Layer 4: high-level executor

`ShellExecutor` is the normal runtime entry point.

It combines:

- capability checks;
- optional argument policy set;
- optional environment policy;
- optional workspace policy;
- circuit breaker;
- retry policy;
- aggregate session budget;
- audit events;
- low-cardinality telemetry;
- tamper-evident receipts;
- pre/post hooks;
- deterministic command fingerprints.

Higher-level components should depend on `ShellExecutor`, not call `subprocess` and not call `ShellRunner` directly unless they are infrastructure code extending the primitive boundary itself.

## Capabilities

The current capability vocabulary is deliberately small:

| Capability | Meaning |
| --- | --- |
| `execute` | Run a registered logical command. |
| `custom_env` | Supply environment values beyond fixed/inherited policy. |
| `inherit_env` | Reserved authority marker for surfaces that expose inheritance decisions. |
| `stdin` | Supply bytes to child stdin. |
| `nonzero_success` | Treat explicitly configured nonzero return codes as accepted. |
| `long_running` | Request a timeout above the normal long-running threshold. |
| `large_output` | Use a primitive runner configured above the normal output threshold. |
| `parallel` | Use `BatchExecutor`. |
| `pipeline` | Use `PipelineExecutor`. |
| `retry` | Retry a failed process. |
| `audit_export` | Reserved for audit export/control surfaces. |
| `manifest` | Reserved for declarative manifest ingestion surfaces. |

`CapabilityGrant.narrow()` cannot add authority. `CapabilityGrant.intersect()` keeps only common authority.

Do not use a broad grant as a substitute for command-specific policy. Capabilities answer what category of action a caller may perform. Command definitions answer what each executable may actually receive.

## Executable registry

`ExecutableRegistry` records canonical executable metadata:

```python
registry.register_path(
    "python",
    sys.executable,
    capabilities={ShellCapability.EXECUTE},
    tags={"runtime", "python"},
    description="Repository Python interpreter",
)
```

Registration resolves the executable to an absolute existing file.

Aliases are logical convenience only. A frozen registry snapshot contains canonical executables and a deterministic SHA-256 digest. `to_policy_mapping()` intentionally exports canonical names only.

A registry can be built during application startup, reviewed, frozen, and then used to construct `ShellPolicy` objects.

Never register a path supplied by model output, HTTP input, a manifest, or a task prompt.

## Argument policies

Argv-only execution prevents shell parsing, but a dangerous executable may still expose dangerous flags. `ArgumentPolicy` is a per-command grammar.

It supports:

- known option names;
- options with values;
- repeatability rules;
- `--option=value` control;
- `--` separator control;
- fixed and variadic positional constraints;
- positional count limits;
- token deny sets;
- deny regexes;
- total argument count and byte limits;
- value regex/choice/length constraints.

Example:

```python
compile_policy = ArgumentPolicy(
    options={
        "-q": OptionRule("-q"),
        "-m": OptionRule(
            "-m",
            takes_value=True,
            value=ValueConstraint(choices=frozenset({"compileall"})),
        ),
    },
    variadic=ValueConstraint(pattern=r"[A-Za-z0-9_./-]+"),
    max_positionals=4,
)
```

The policy does not reinterpret quoting. Each element is already one argv element.

## Environment policies

`EnvironmentPolicy` defines the complete child environment vocabulary for a command surface.

Each allowed key can have:

- regex validation;
- enumerated choices;
- per-value byte limit;
- empty-value policy.

The policy can also define:

- fixed values;
- required keys;
- explicitly inherited keys;
- total child-environment byte limit.

Unknown keys are rejected.

A command contract should usually start with `EnvironmentPolicy.empty()` and add only the keys the executable demonstrably requires.

Avoid inheriting `PATH`, cloud credentials, GitHub tokens, SSH agent variables, model-provider credentials, or proxy credentials into generic agent/tool executions.

## Workspace policy

`WorkspacePolicy` resolves cwd paths before use and requires the resolved directory to be inside an allowed root.

It supports denied subroots and optional maximum relative depth.

Example use cases:

- allow a generated project workspace while denying its secret staging directory;
- allow a repository worktree while denying `.git` administration roots;
- give a tool a specific task directory instead of repository-wide cwd authority.

`WorkspacePolicy.narrow()` only accepts child roots that are already under parent roots.

## Policy algebra

`narrow_policy(parent, ...)` creates a child `ShellPolicy` while refusing authority expansion.

Narrowing can:

- remove executables;
- move cwd roots deeper;
- remove allowed environment keys;
- remove inherited environment keys;
- lower timeout/output/input/environment/argument limits.

It cannot:

- add executables;
- retarget an executable;
- move cwd authority outside a parent root;
- add environment keys;
- increase a resource ceiling.

`intersect_policies(left, right)` produces common authority only.

`diff_policies()` describes widening versus narrowing changes so configuration review can surface authority expansion explicitly.

## Sessions and resource budgets

`ShellSession` is an aggregate budget shared by a sequence of process spawns.

`ResourceLimits` currently bound:

- total process spawns;
- total failures;
- cumulative duration;
- cumulative stdout bytes;
- cumulative stderr bytes;
- total retries.

Each actual retry is a separate process spawn and consumes command budget.

Closing a session permanently prevents further execution through that session object.

Sessions are useful for agent turns, tool-use tasks, pipeline runs, and bounded repair loops.

## Retries

Retries are disabled by default.

`RetryPolicy` can opt into:

- selected transient return codes;
- timeouts;
- output-limit events.

Output-limit retry should generally remain disabled because repeating a command that floods output is rarely corrective.

Backoff is deterministic and capped. There is no hidden jitter by default, which keeps tests and evidence reproducible.

The executor also caps requested retry sleep against `ExecutorConfig.max_retry_sleep_seconds`.

## Circuits

`CircuitBreaker` protects repeatedly failing logical commands.

States are:

- `closed`;
- `open`;
- `half_open`.

Failure threshold and recovery delay are explicit. No background timer is used. State refresh happens during normal breaker access.

A half-open failure reopens immediately. A configured number of half-open successes closes the breaker.

`CircuitRegistry` keeps breakers keyed by a low-cardinality command/service key.

## Audit

Audit events are structured and intentionally avoid raw argv and raw environment values.

The executor emits:

- `shell.execution.started`;
- `shell.execution.completed`;
- `shell.execution.retry`.

Started events use hashes for argv and environment-key sets.

Available sinks include:

- no-op sink;
- bounded in-memory sink;
- composite fan-out sink;
- recursive redacting sink;
- bounded append-only JSONL sink.

The JSONL sink refuses symlink targets and refuses oversized serialized events.

File permissions, rotation, shipping, and retention remain deployment responsibilities.

## Receipts

`ExecutionReceipt` is the evidence record for one process attempt.

It includes:

- logical command name;
- correlation ID;
- request fingerprint;
- timestamps;
- measured duration;
- return code;
- success/timeout/output-limit flags;
- stdout/stderr byte counts;
- retry attempt number;
- bounded safe metadata.

It does not include raw argv, raw environment values, raw cwd, executable path, stdin, stdout, or stderr.

`ReceiptChain` creates a SHA-256 hash chain over receipts. It supports integrity verification and a current root hash suitable for higher-level evidence packets.

## Telemetry

`ShellTelemetry` keeps bounded, in-process counters by logical registered command name.

It tracks:

- starts;
- completions;
- failures;
- timeouts;
- output-limit events;
- stdout/stderr bytes;
- cumulative duration;
- retries.

Arbitrary arguments, cwd values, correlation IDs, task IDs, and environment values are deliberately excluded from metric labels to prevent cardinality explosions and secret leakage.

## Batch execution

`BatchExecutor` requires the `parallel` capability.

It provides bounded thread-pool concurrency over the same `ShellExecutor` security boundary.

Batch item IDs must be unique and bounded.

Fail-fast mode stops submitting useful follow-on work where cancellation is still possible, but it does not pretend that already-running OS processes can be atomically cancelled by Python future cancellation.

## Pipelines

`PipelineSpec` is a bounded DAG of `PipelineStep` objects.

Validation rejects:

- duplicate step IDs;
- self-dependencies;
- unknown dependencies;
- cycles;
- step-count overflow.

`PipelineExecutor` requires the `pipeline` capability and executes steps through the canonical `ShellExecutor`.

Failed dependencies block dependent steps. Independent steps may continue when the failed step is configured `continue_on_failure=True`.

`pipeline_from_commands()` is a convenience for strict linear pipelines.

## Declarative manifests

Shell manifests are versioned JSON documents.

Important restriction: manifests contain logical command names, never executable paths.

The parser rejects unknown fields such as `shell`, `executable`, or arbitrary extension keys instead of silently ignoring them.

Manifest limits cover:

- total JSON bytes;
- step count;
- arguments per step;
- environment keys per step;
- individual string length.

Pipeline validation runs after manifest decoding, so dependency errors and cycles remain fail-closed.

A parsed manifest still requires normal command catalog admission and caller capabilities before execution.

## Tool adapter

`ShellToolAdapter` is intended for agent/tool interfaces.

By default its response contains metadata only. Raw output is omitted.

A caller may request a bounded output view. Output is recursively scrubbed with `SecretRedactor` and limited to a caller-bounded character count with a hard upper ceiling.

Tool responses never expose executable paths or child environment values.

## Queue, leases, rate limits, and dedupe

`ShellWorkQueue` is an explicit bounded priority queue. It is not a hidden worker.

Callers must explicitly:

- enqueue;
- claim;
- execute;
- complete or fail.

`LeaseRegistry` provides TTL ownership for low-cardinality execution keys and prevents local stampedes.

`RateLimiter` provides bounded per-key token buckets.

`DedupeRegistry` provides caller-declared idempotency keys tied to command fingerprints. Reusing an idempotency key for a different fingerprint fails closed.

These primitives are process-local coordination helpers, not distributed consensus. Distributed deployments must put durable/distributed coordination above them where needed.

## Control-plane facade

`ShellControlPlane` composes:

- command catalog;
- admission;
- preflight;
- rate limiter;
- dedupe registry;
- lease registry;
- work queue.

It is policy-only and never spawns a process.

This makes it suitable for Jeeves planning/admission stages before work reaches an executor worker.

## Status

`status_snapshot()` combines:

- non-executing policy health;
- telemetry;
- circuit state;
- optional receipt-chain integrity/root.

Policy health checks executable existence/executable bit where applicable, cwd-root existence, and notable inheritance configuration.

Health checks do not execute registered binaries merely to prove they exist.

## Integration rule

New host execution code should follow this decision order:

1. Determine whether host execution is actually necessary.
2. Register the executable in trusted startup configuration.
3. Define a command contract and argument grammar.
4. Define environment and workspace authority.
5. Give the caller the narrowest capability grant.
6. Preflight if the command comes from a plan or manifest.
7. Execute through `ShellExecutor`.
8. Keep evidence in receipts/audit, not raw exception strings.
9. Use session budgets for loops and autonomous tasks.
10. Add an adversarial regression before expanding authority.

Direct new `subprocess` usage remains subject to `scripts/check_repository_process_safety.py` and should be exceptional.

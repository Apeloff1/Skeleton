# Shell Plane API Reference

This reference summarizes the public concepts introduced by `skeleton.shells`. It is intentionally contract-oriented; implementation details remain in module docstrings and tests.

## Primitive execution

### `ShellPolicy`

Defines primitive host execution authority.

Core fields:

- `executables: Mapping[str, str]`
- `cwd_roots: tuple[Path, ...]`
- `allowed_env: frozenset[str]`
- `inherited_env: frozenset[str]`
- `default_timeout: float`
- `max_timeout: float`
- `max_output_bytes: int`
- `max_input_bytes: int`
- `max_env_bytes: int`
- `max_args: int`
- `max_arg_bytes: int`

Construction validates executable paths, cwd roots, environment names, and resource bounds.

### `ShellCommand`

Immutable process request.

Fields:

- logical command name;
- tuple argv elements excluding executable;
- optional cwd;
- custom environment mapping;
- optional stdin bytes;
- optional timeout;
- accepted return-code set.

### `ShellResult`

Immutable primitive execution result.

Fields:

- logical command;
- return code;
- stdout bytes;
- stderr bytes;
- timeout flag;
- output-limit flag;
- accepted flag.

`ok` is true only when the result was accepted and neither timeout nor output-limit termination occurred.

### `ShellRunner`

`run(command) -> ShellResult`

`run_checked(command) -> ShellResult`

`run_checked` raises `ShellExecutionError` for unsuccessful outcomes. Exception text does not embed raw child output.

## Capability API

### `ShellCapability`

Enum of shell-plane authority categories.

### `CapabilityGrant`

Important methods:

- `none()`
- `execution_only()`
- `from_names()`
- `has()`
- `require()`
- `require_all()`
- `narrow()`
- `intersect()`
- `to_dict()`

## Registry API

### `ExecutableSpec`

Canonical executable metadata with resolved absolute path, capabilities, tags, and description.

### `ExecutableRegistry`

Important methods:

- `register()`
- `register_path()`
- `alias()`
- `remove()`
- `resolve()`
- `by_tag()`
- `snapshot()`
- `freeze()`

### `RegistrySnapshot`

Immutable snapshot with deterministic digest.

Important methods:

- `resolve()`
- `names()`
- `to_policy_mapping()`

## Argument API

### `ValueConstraint`

Value-level regex, choice, and length bounds.

### `OptionRule`

Declares one allowed option and whether it takes/repeats a value.

### `ArgumentPolicy`

Validates a command argv vector.

Important configuration:

- options;
- positional constraints;
- variadic constraint;
- min/max positionals;
- double-dash policy;
- `option=value` policy;
- deny tokens/patterns;
- total arg count/bytes.

### `ArgumentPolicySet`

Default-deny mapping from logical command name to argument policy.

## Environment API

### `EnvironmentValueRule`

Per-key value constraint.

### `EnvironmentPolicy`

Defines allowed/fixed/required/inherited child environment.

Important methods:

- `empty()`
- `build()`
- `allowed_keys()`

## Workspace API

### `WorkspacePolicy`

Fields:

- allowed roots;
- denied roots;
- optional relative depth limit.

Important methods:

- `resolve()`
- `narrow()`

## Command contract API

### `CommandDefinition`

Binds `ExecutableSpec` to:

- `ArgumentPolicy`;
- `EnvironmentPolicy`;
- required capabilities;
- command timeout ceiling;
- stdin permission;
- nonzero-success permission;
- description.

### `CommandCatalog`

Important methods:

- `register()`
- `get()`
- `names()`
- `by_tag()`
- `freeze()`
- `to_dict()`

## Admission API

### `CommandAdmission`

`admit(command, grant)` raises on denial.

`inspect(command, grant)` returns an `AdmissionDecision` instead of raising.

### `AdmissionDecision`

Safe metadata only:

- allowed;
- command;
- required capability names;
- environment key names;
- argument count;
- reason.

## Preflight API

### `PreflightAnalyzer`

- `commands()`
- `pipeline()`

Returns `PreflightReport` with per-item decisions and aggregate counts.

## High-level execution API

### `ShellExecutor`

`execute(command, retry=None, session=None, correlation_id=None, circuit_key=None)`

Returns `ExecutionOutcome`.

The executor coordinates capability checks, optional argv/env/workspace policies, circuits, sessions, audit, telemetry, receipts, hooks, and retry.

### `ExecutorConfig`

Controls executor thresholds such as long-running classification, large-output classification, and retry sleep cap.

### `ExecutionOutcome`

Contains:

- final `ShellResult`;
- tuple of attempt receipts;
- correlation ID.

Convenience properties:

- `ok`
- `final_receipt`

## Retry API

### `RetryPolicy`

Fields:

- max attempts;
- initial delay;
- multiplier;
- max delay;
- retry return-code set;
- timeout retry flag;
- output-limit retry flag.

Important methods:

- `none()`
- `transient_codes()`
- `delay_for_attempt()`
- `decide()`

## Circuit API

### `CircuitPolicy`

- failure threshold;
- recovery seconds;
- required half-open successes.

### `CircuitBreaker`

- `allow()`
- `record_success()`
- `record_failure()`
- `reset()`
- `snapshot()`
- `state()`

### `CircuitRegistry`

Creates/reuses breakers by key.

## Resource/session API

### `ResourceLimits`

Aggregate ceilings for command count, failures, duration, stdout/stderr, and retries.

### `ResourceBudget`

Thread-safe usage tracker.

### `ShellSession`

Important methods:

- `require_start()`
- `require_retry()`
- `record()`
- `receipts()`
- `snapshot()`
- `close()`

## Receipt API

### `ExecutionReceipt`

Safe evidence record for one process attempt.

### `ReceiptChain`

Important methods:

- `append()`
- `snapshot()`
- `verify()`
- `root_hash()`

## Audit API

### `AuditEvent`

Structured audit event with correlation ID and bounded safe data.

### Sinks

- `NullAuditSink`
- `MemoryAuditSink`
- `CompositeAuditSink`
- `RedactingAuditSink`
- `JsonlAuditSink`

## Redaction API

### `RedactionPolicy`

Controls secret key vocabulary, regex rules, collection bounds, string bound, and depth bound.

### `SecretRedactor`

- `redact_text()`
- `redact()`
- `redact_mapping()`
- `add_literals()`

## Telemetry API

### `ShellTelemetry`

- `started()`
- `retried()`
- `completed()`
- `snapshot()`
- `reset()`

### `CommandMetrics`

Safe command-level aggregate metrics.

## Hook API

### `HookRegistry`

- `add_pre()`
- `add_post()`
- `run_pre()`
- `run_post()`
- `counts()`

Pre-hooks can veto. Post-hook exceptions are isolated and returned by exception type.

## Template API

### `TemplateSlot`

Named constrained value slot.

### `CommandTemplate`

Builds a `ShellCommand` from fixed argv tokens plus whole-token slots.

No shell interpolation is performed.

### `TemplateCatalog`

Named template registry.

## Batch API

### `BatchItem`

Item ID, command, optional retry policy.

### `BatchExecutor`

Bounded parallel execution over `ShellExecutor`.

Requires `parallel` capability.

### `BatchResult`

Contains outcome/error/skipped maps.

## Pipeline API

### `PipelineStep`

Step ID, command, dependencies, optional retry, continue-on-failure flag.

### `PipelineSpec`

Validates IDs, dependencies, cycles, and step bounds.

### `PipelineExecutor`

Dependency-aware execution through `ShellExecutor`.

Requires `pipeline` capability.

### `PipelineResult`

Contains per-step `PipelineStepResult` and actual execution order.

## Manifest API

### `ManifestLimits`

Bounds serialized manifest input.

### `parse_manifest()`

Decodes strict schema-versioned JSON to `PipelineSpec`.

### `manifest_dict()`

Converts a pipeline spec back to serializable manifest shape.

## Tool adapter API

### `ToolExecutionRequest`

Bounded agent/tool request.

### `ShellToolAdapter`

Executes through `ShellExecutor` and returns a compact `ToolExecutionResponse`.

Output is omitted by default and redacted/bounded when requested.

## Output API

### `render_output()`

Creates bounded redacted head/tail view of one stream.

### `combined_summary()`

Returns bounded redacted stdout/stderr metadata and views.

## Queue API

### `ShellWorkQueue`

- `enqueue()`
- `claim()`
- `complete()`
- `fail()`
- `cancel()`
- `get()`
- `counts()`
- `snapshot()`

The queue does not start background workers.

## Lease API

### `LeaseRegistry`

- `acquire()`
- `renew()`
- `release()`
- `held()`
- `snapshot()`

## Rate-limit API

### `RateLimitPolicy`

Token-bucket capacity/refill/cost settings.

### `RateLimiter`

Bounded key registry of token buckets.

## Dedupe API

### `DedupeRegistry`

- `reserve()`
- `complete()`
- `get()`
- `snapshot()`

Keys bind to a command fingerprint for a bounded TTL.

## History API

### `ReceiptHistory`

Bounded newest-first receipt history.

### `HistoryQuery`

Filters by command, correlation ID, success, minimum attempt, and result count.

## Policy API

### `narrow_policy()`

Constructs a child policy and rejects authority widening.

### `intersect_policies()`

Builds common authority only.

### `is_narrower_or_equal()`

Checks the authority relation.

### `diff_policies()`

Returns `PolicyDiff` with individual `PolicyChange` records labeled wider/narrower.

## Profiles API

### `PolicyProfileCatalog`

Named `PolicyProfile` registry.

### `build_default_profiles()`

Builds conservative `inspection`, `build`, and `agent-tool` profiles for a trusted executable mapping and workspace.

## Failure API

### `classify_result()`

Classifies `ShellResult` into:

- success;
- timeout;
- output limit;
- exit code;
- termination;
- unknown.

The retryable flag is a diagnostic hint only. Actual retries remain governed by `RetryPolicy`.

## Status API

### `inspect_policy()`

Non-executing policy health check.

### `status_snapshot()`

Combines policy health, telemetry, circuits, and optional receipt-chain integrity.

## Control plane API

### `ShellControlPlane`

Policy-only composition root.

It combines admission, preflight, rate limiting, dedupe, leases, and queueing without spawning processes.

Important methods:

- `inspect()`
- `admit_with_rate_limit()`
- `preflight_commands()`
- `explain()`

## Serialization API

### `dumps()`

Bounded JSON serialization for shell-plane records.

Bytes serialize as length metadata, not raw content.

### `loads_object()`

Bounded JSON object decoder.

### `receipt_from_dict()`

Strict minimum-field receipt reconstruction.

## Provenance API

Helpers:

- `canonical_json()`
- `sha256_hex()`
- `digest_mapping()`
- `digest_arguments()`
- `digest_environment_keys()`
- `digest_path()`
- `command_fingerprint()`
- `policy_fingerprint()`

Use fingerprints as correlation/evidence helpers, not as an authorization substitute.

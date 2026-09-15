# Canonical agent orchestration lifecycle

Issue #117 consolidates model/agent turns, tool execution, retries, cancellation, and terminal state handling behind one lifecycle engine: `skeleton.frontier.orchestration.CanonicalOrchestrator`.

## State model

Runs move only through these transitions:

- `pending -> running`
- `pending -> cancelled`
- `running -> completed | failed | cancelled`

Completed, failed, and cancelled runs are terminal. Any attempted transition out of a terminal state raises `InvalidTransitionError`.

Steps move through:

- `pending -> running | cancelled`
- `running -> succeeded | failed | cancelled | retrying`
- `retrying -> running | cancelled`

Succeeded, failed, and cancelled steps are terminal. The orchestrator owns these mutations; drivers and tools return values/errors rather than editing state themselves.

## Turn driver contract

Provider-, agent-, or compatibility-specific code implements `OrchestrationDriver.next_turn`. A turn must either:

- return `TurnOutcome(terminal=True, output=...)`; or
- request one or more normalized `ToolInvocation` values.

Drivers receive normalized `ToolResult` values from the previous turn. This separates the orchestration lifecycle from provider SDK response types and allows current/legacy agent paths to migrate incrementally.

## Tool lifecycle

Tools are resolved through `ToolRegistry`. Every invocation gets one `StepRecord` with an explicit attempt count and terminal status. Unknown tools and non-transient tool errors fail the run. Only `TransientToolError` is retryable.

`RetryBudget.max_attempts` is the hard attempt ceiling. Exhaustion converts the tool step to `failed` and the run to `failed`; no running/retrying step is left behind.

## Cancellation

The orchestrator uses the provider-neutral `CancellationToken` introduced by #116. Pre-cancelled runs terminate before a model/driver call. In-flight async driver/tool work races the cancellation token and transitions the active step/run to cancelled deterministically.

External `asyncio` task cancellation is not swallowed: active internal work is cancelled and the `CancelledError` is re-raised after state cleanup.

## Loop bound

`max_turns` is mandatory and positive. A driver that continues requesting tools beyond this bound terminates the run as failed with a turn-budget error. This prevents unbounded model/tool loops even when every individual operation succeeds.

## Migration rule

New agent/orchestration paths should adapt to `OrchestrationDriver` and register tools through `ToolRegistry`. Existing coordinators should migrate state mutation and retry logic behind `CanonicalOrchestrator`; adding another independent run-status/retry loop is not an accepted migration path.

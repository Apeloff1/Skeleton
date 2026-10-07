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

Sensitive tools also declare explicit `ToolCapability` requirements. A run receives a capability grant set; the default is empty. Capability decisions are recorded on the canonical `RunRecord` before handler invocation, and a denied capability fails the tool step without executing the handler.

## Cancellation

The orchestrator uses the provider-neutral `CancellationToken` introduced by #116. Pre-cancelled runs terminate before a model/driver call. In-flight async driver/tool work races the cancellation token and transitions the active step/run to cancelled deterministically.

External `asyncio` task cancellation is not swallowed: active internal work is cancelled and the `CancelledError` is re-raised after state cleanup.

## Loop bound

`max_turns` is mandatory and positive. A driver that continues requesting tools beyond this bound terminates the run as failed with a turn-budget error. This prevents unbounded model/tool loops even when every individual operation succeeds.

## Legacy coordinator adapter

`skeleton.agents.coordination.Coordinator` remains a compatibility API for the older agent-pool surface. Agent selection and capacity accounting stay in `AgentPool`, but any task type with a registered local handler is adapted into the canonical lifecycle:

1. the compatibility task is assigned to an available agent;
2. a small `OrchestrationDriver` requests the registered handler as a canonical tool call;
3. `CanonicalOrchestrator` owns the run/tool transitions and terminal state;
4. the final `RunRecord` is projected back to legacy `TaskStatus`, `result`, and `error` fields;
5. agent capacity is released after the canonical run reaches a terminal state.

`Coordinator.get_run_record(task_id)` exposes the canonical record for migrated local tasks. Async callers use `await Coordinator.dispatch_async(...)`; the synchronous `dispatch(...)` wrapper deliberately refuses to nest an event loop and tells event-loop callers to use the async API. Tasks without a registered local handler preserve the historical externally-executed behavior and remain `RUNNING` after pool assignment.

## Migration rule

New agent/orchestration paths should adapt to `OrchestrationDriver` and register tools through `ToolRegistry`. Compatibility layers may project canonical run state into legacy types, but they must not add another independent run-status, retry, or tool-exception lifecycle.
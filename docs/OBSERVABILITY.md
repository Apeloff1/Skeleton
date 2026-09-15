# Canonical observability contract

Issue #121 consolidates observability around the existing `skeleton.observability` package and the kernel `EventBus`. New runtime code should extend these primitives rather than create another logging, tracing, or metrics stack.

## Correlation

`DomainEvent.correlation_id` is the subsystem-neutral correlation field. `EventBus.emit(..., correlation_id=...)` preserves it on emitted events. API request IDs, orchestration run IDs, agent task IDs, and tool call IDs should be related through this field or included as explicit structured payload fields when crossing subsystem boundaries.

Correlation identifiers are operational metadata, not a place to store credentials or user payloads.

`ObservableOrchestrator` is the canonical instrumentation adapter for `CanonicalOrchestrator`. It delegates every lifecycle decision to the canonical orchestrator and adds metadata-only events for run and tool start/completion/failure, capability denial, cancellation, and retry evidence. Tool arguments, tool outputs, and exception messages are never copied into those events.

API integrations should resolve one request identifier with `skeleton.api.correlation.request_correlation_id()` and invoke orchestration through `run_with_request_correlation()`. A valid request-state ID wins, otherwise exactly one valid `X-Request-ID` is accepted; duplicate or malformed header values fail closed to a server-generated identifier. The request correlation ID is then preserved on every orchestration event while `run_id` and `call_id` remain explicit structured fields.

## Redaction

`skeleton.observability.redaction` is the canonical telemetry sanitization boundary.

- credential-shaped keys such as `authorization`, `cookie`, `password`, `secret`, `api_key`, and access/refresh tokens are replaced with `[REDACTED]`;
- common inline `token=...`, `api-key=...`, password/secret assignments, and Bearer credentials are scrubbed from free text;
- nested telemetry payloads have a bounded depth;
- arbitrary exception messages are not persisted by shared health/tracing helpers; stable exception type names are retained instead.

`StructuredLogger`, `Tracer`, health probes, and the event-to-metrics bridge all use the same redaction helpers. Callers should sanitize before exporting any additional telemetry surface.

## Structured event bridge

`EventMetricsBridge` subscribes to kernel events without mutating the source event. It retains a bounded redacted event window and feeds the existing `MetricsRegistry`.

Baseline metric names are:

- `observability.events_total` — event count by topic;
- `observability.failures_total` — failed events or HTTP-style status >= 500;
- `observability.retries_total` — retry/retrying events;
- `observability.rate_limits_total` — rate-limit events / status 429;
- `observability.latency_ms` — duration histogram when `duration_ms` is present;
- `observability.queue_depth` — latest non-negative queue depth gauge;
- `observability.memory_bytes` — latest non-negative memory-use gauge.

These names are the baseline contract for future API/runtime/agent/tool instrumentation. Provider- or subsystem-specific labels belong on the metric rather than in separate registries.

## Orchestration event surface

The correlated orchestration adapter emits:

- `orchestration.run.started`
- `orchestration.run.completed` / `.failed` / `.cancelled`
- `orchestration.tool.started`
- `orchestration.tool.succeeded` / `.failed` / `.denied` / `.cancelled`
- `orchestration.tool.retry`

Every event carries the same `DomainEvent.correlation_id`. Run events include `run_id`; tool events also include `call_id` and `tool_name`. Failure events expose only stable exception type names. Timing, attempt counts, and lifecycle status may be emitted, but user/tool payloads are prohibited.

## Existing package surface

The package root exposes the canonical health, metrics-registry, structured-logging, tracing, event-bridge, orchestration-observability, and redaction primitives. Older specialist modules under `skeleton/observability/` remain implementation modules; they should converge on these shared contracts rather than define competing correlation or secret-handling rules.

## Regression policy

`tests/test_observability.py` and the Frontier contract suite pin:

- correlation preservation through `EventBus.emit`;
- API request ID propagation through orchestration and tool execution;
- duplicate request-ID fail-closed behavior;
- metadata-only tool lifecycle events with no argument/output/exception-message leakage;
- health-probe exception redaction;
- structured-log redaction;
- trace failure/attribute redaction;
- bounded event collection and baseline metric classification;
- compatibility with the current `MetricsRegistry` API.

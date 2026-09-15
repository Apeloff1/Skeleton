# Canonical observability contract

Issue #121 consolidates observability around the existing `skeleton.observability` package and the kernel `EventBus`. New runtime code should extend these primitives rather than create another logging, tracing, or metrics stack.

## Correlation

`DomainEvent.correlation_id` is the subsystem-neutral correlation field. `EventBus.emit(..., correlation_id=...)` preserves it on emitted events. API request IDs, orchestration run IDs, agent task IDs, and tool call IDs should be related through this field or included as explicit structured payload fields when crossing subsystem boundaries.

Correlation identifiers are operational metadata, not a place to store credentials or user payloads.

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

## Existing package surface

The package root now exposes the canonical health, metrics-registry, structured-logging, tracing, event-bridge, and redaction primitives. Older specialist modules under `skeleton/observability/` remain implementation modules; they should converge on these shared contracts rather than define competing correlation or secret-handling rules.

## Regression policy

`tests/test_observability.py` is part of `scripts/quality-gates.sh`. It pins:

- correlation preservation through `EventBus.emit`;
- health-probe exception redaction;
- structured-log redaction;
- trace failure/attribute redaction;
- bounded event collection and baseline metric classification;
- compatibility with the current `MetricsRegistry` API.

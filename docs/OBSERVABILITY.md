# Canonical observability contract

Issue #121 consolidates observability around the existing `skeleton.observability` package and the kernel `EventBus`. New runtime code should extend these primitives rather than create another logging, tracing, or metrics stack.

## Correlation

`DomainEvent.correlation_id` is the subsystem-neutral correlation field. `EventBus.emit(..., correlation_id=...)` preserves it on emitted events. API request IDs, orchestration run IDs, agent task IDs, background-job IDs, scheduler job IDs, queue task IDs, worker-pool work IDs, and tool call IDs should be related through this field or included as explicit structured payload fields when crossing subsystem boundaries.

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

These names are the baseline contract for API/runtime/agent/tool/background-job instrumentation. Provider- or subsystem-specific labels belong on the metric rather than in separate registries.

## Core runtime attachment

Core background execution paths emit metadata-only lifecycle events through the shared kernel `EventBus` so one attached `EventMetricsBridge` observes them without subsystem-specific exporters.

`JobOrchestrator` accepts an optional shared bus and emits `jobs.submitted`, `jobs.started`, `jobs.progress`, `jobs.completed`, `jobs.failed`, `jobs.paused`, `jobs.resumed`, and `jobs.retry`. Job events carry job identity, status, progress, duration, and stable exception type when relevant. Chunk contents, checkpoint data, and exception messages are excluded. A caller-supplied request/run correlation identifier is preserved for the full job lifecycle; otherwise the job ID is used.

`Scheduler` emits add/remove/enable/disable/start/completion/failure lifecycle events on the same bus. A scheduler job can preserve an upstream correlation identifier across recurring executions; run history retains only stable exception type names, never arbitrary exception messages. Scheduler duration and failure fields feed the canonical latency/failure metrics automatically.

`TaskQueue` accepts the same shared bus and emits enqueue/dequeue/retry/completion/dead-letter lifecycle events. Queue events carry task/queue identity, attempts, queue depth, in-flight count, dead-letter depth, and completion latency. Task payloads are never copied into telemetry. The queue task ID is the correlation identifier for its lifecycle.

`WorkerPool` emits enqueue/retry/completion/failure/rejection lifecycle events with opaque work IDs, worker identity, attempts, latency, and queue depth. Work payloads and handler exception messages are excluded. Retries and terminal failures therefore feed the same canonical retry/failure metrics as orchestration and background jobs.

Because these events use the canonical field names (`status`, `duration_ms`, `retrying`, and `queue_depth`), `EventMetricsBridge` automatically produces baseline failure, retry, latency, and queue-depth metrics from real core execution paths.

## Existing package surface

The package root exposes the canonical health, metrics-registry, structured-logging, tracing, event-bridge, orchestration-observability, and redaction primitives. Older specialist modules under `skeleton/observability/` remain implementation modules; they should converge on these shared contracts rather than define competing correlation or secret-handling rules.

## Regression policy

`tests/test_observability.py`, the Frontier correlation suite, and `skeleton/testing/test_core_observability_attachment.py` are part of `scripts/quality-gates.sh`. Together they pin:

- correlation preservation through `EventBus.emit`;
- API request correlation through canonical orchestration/tool execution;
- background-job, scheduler, task-queue, and worker-pool correlation through real core runtime paths;
- secret-free core job/scheduler/queue/worker event payloads and exception state;
- baseline failure/retry/latency/queue metric emission;
- health-probe exception redaction;
- structured-log redaction;
- trace failure/attribute redaction;
- bounded event collection and baseline metric classification;
- compatibility with the current `MetricsRegistry` API.

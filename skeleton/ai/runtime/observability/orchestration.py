"""Correlation-aware observability adapter for canonical orchestration.

The adapter subclasses :class:`CanonicalOrchestrator` only to observe its
existing lifecycle. It does not own state transitions, retry policy, tool
authorization, cancellation, or result handling. Event payloads are metadata-
only: tool arguments, outputs, and exception messages never enter telemetry.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Iterable, Mapping

from skeleton.observability.correlation import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)

from skeleton.frontier.model_runtime import CancellationToken, ProviderCancelledError
from skeleton.frontier.orchestration import (
    CanonicalOrchestrator,
    CapabilityDeniedError,
    OrchestrationDriver,
    RetryBudget,
    RunRecord,
    RunStatus,
    StepKind,
    ToolCapability,
    ToolDefinition,
    ToolInvocation,
    ToolRegistry,
    ToolResult,
)
from skeleton.kernel.events import EventBus
from skeleton.observability.event_bridge import EventMetricsBridge
from skeleton.observability.logging import StructuredLogger
from skeleton.observability.tracing import Tracer


def _normalized_correlation_id(value: str | None, *, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise TypeError("correlation_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("correlation_id must not be empty")
    if normalized != value:
        raise ValueError("correlation_id must be normalized")
    if len(value) > 128:
        raise ValueError("correlation_id must be at most 128 characters")
    return value


class ObservableOrchestrator(CanonicalOrchestrator):
    """Canonical orchestrator with the shared observability primitives attached.

    Every instance owns an event bus, event-to-metrics bridge, structured logger,
    and tracer by default. Callers may inject any of those primitives. When the
    supplied bus already owns the canonical bridge (for example ``JournaledBus``),
    that bridge is reused without creating or subscribing a second metrics plane.

    Lifecycle logs, spans, and events contain operational metadata only. Tool
    arguments, outputs, and arbitrary exception messages stay outside these
    telemetry surfaces.
    """

    def __init__(
        self,
        *,
        tools: ToolRegistry | None = None,
        tool_retry_budget: RetryBudget = RetryBudget(),
        max_turns: int = 16,
        event_bus: EventBus | None = None,
        metrics_bridge: EventMetricsBridge | None = None,
        logger: StructuredLogger | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        super().__init__(
            tools=tools or ToolRegistry(),
            tool_retry_budget=tool_retry_budget,
            max_turns=max_turns,
        )
        self.event_bus = event_bus or EventBus()
        bus_metrics_bridge = getattr(self.event_bus, "metrics_bridge", None)
        if metrics_bridge is None and isinstance(
            bus_metrics_bridge, EventMetricsBridge
        ):
            self.metrics_bridge = bus_metrics_bridge
        elif metrics_bridge is not None and metrics_bridge is bus_metrics_bridge:
            self.metrics_bridge = metrics_bridge
        else:
            self.metrics_bridge = metrics_bridge or EventMetricsBridge()
            self.metrics_bridge.attach(self.event_bus)
        self.logger = logger or StructuredLogger()
        self.tracer = tracer or Tracer("skeleton.orchestration")

    def _emit(self, topic: str, payload: dict[str, object]) -> None:
        correlation_id = get_correlation_id()
        self.event_bus.emit(
            topic,
            payload,
            correlation_id=correlation_id,
        )
        log = (
            self.logger.error
            if topic.endswith((".failed", ".denied"))
            else self.logger.info
        )
        log_context = dict(payload)
        log_context["correlation_id"] = correlation_id
        log(topic, **log_context)

    async def run(
        self,
        driver: OrchestrationDriver,
        *,
        cancellation: CancellationToken | None = None,
        run_id: str | None = None,
        capabilities: Iterable[ToolCapability | str] = (),
        correlation_id: str | None = None,
    ) -> RunRecord:
        effective_run_id = run_id or uuid.uuid4().hex
        effective_correlation_id = _normalized_correlation_id(
            correlation_id,
            fallback=effective_run_id,
        )
        token = set_correlation_id(effective_correlation_id)
        started = time.perf_counter()
        try:
            with self.tracer(
                "orchestration.run",
                trace_id=effective_correlation_id,
                run_id=effective_run_id,
                correlation_id=effective_correlation_id,
            ) as span:
                self._emit(
                    "orchestration.run.started",
                    {
                        "run_id": effective_run_id,
                        "status": RunStatus.RUNNING.value,
                    },
                )
                try:
                    record = await super().run(
                        driver,
                        cancellation=cancellation,
                        run_id=effective_run_id,
                        capabilities=capabilities,
                    )
                except asyncio.CancelledError:
                    span.set_attribute("status", RunStatus.CANCELLED.value)
                    self._emit(
                        "orchestration.run.cancelled",
                        {
                            "run_id": effective_run_id,
                            "status": RunStatus.CANCELLED.value,
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 3
                            ),
                            "error_type": "CancelledError",
                        },
                    )
                    raise
                else:
                    span.set_attribute("status", record.status.value)
                    span.set_attribute("turns", record.turns)
                    span.set_attribute("step_count", len(record.steps))
                    if record.status is RunStatus.FAILED:
                        span.status = "ERROR"
                    self._emit(
                        f"orchestration.run.{record.status.value}",
                        {
                            "run_id": record.run_id,
                            "status": record.status.value,
                            "turns": record.turns,
                            "step_count": len(record.steps),
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 3
                            ),
                        },
                    )
                    return record
        finally:
            reset_correlation_id(token)

    async def _execute_tool(
        self,
        record: RunRecord,
        call: ToolInvocation,
        *,
        cancellation: CancellationToken | None,
        granted_capabilities: frozenset[ToolCapability],
        tool_definitions: Mapping[str, ToolDefinition],
    ) -> ToolResult:
        started = time.perf_counter()
        with self.tracer(
            "orchestration.tool",
            trace_id=get_correlation_id(),
            run_id=record.run_id,
            call_id=call.call_id,
            tool_name=call.name,
        ) as span:
            self._emit(
                "orchestration.tool.started",
                {
                    "run_id": record.run_id,
                    "call_id": call.call_id,
                    "tool_name": call.name,
                    "status": "running",
                },
            )
            try:
                result = await super()._execute_tool(
                    record,
                    call,
                    cancellation=cancellation,
                    granted_capabilities=granted_capabilities,
                    tool_definitions=tool_definitions,
                )
            except BaseException as exc:
                step = next(
                    (
                        candidate
                        for candidate in reversed(record.steps)
                        if candidate.kind is StepKind.TOOL and candidate.name == call.name
                    ),
                    None,
                )
                attempts = step.attempt if step is not None else 0
                if isinstance(exc, CapabilityDeniedError):
                    suffix = "denied"
                elif isinstance(exc, (asyncio.CancelledError, ProviderCancelledError)):
                    suffix = "cancelled"
                else:
                    suffix = "failed"
                span.set_attribute("status", suffix)
                span.set_attribute("attempts", attempts)
                self._emit(
                    f"orchestration.tool.{suffix}",
                    {
                        "run_id": record.run_id,
                        "call_id": call.call_id,
                        "tool_name": call.name,
                        "status": suffix,
                        "attempts": attempts,
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000, 3
                        ),
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            else:
                step = next(
                    (
                        candidate
                        for candidate in reversed(record.steps)
                        if candidate.kind is StepKind.TOOL and candidate.name == call.name
                    ),
                    None,
                )
                attempts = step.attempt if step is not None else 1
                span.set_attribute("status", "succeeded")
                span.set_attribute("attempts", attempts)
                if attempts > 1:
                    self._emit(
                        "orchestration.tool.retry",
                        {
                            "run_id": record.run_id,
                            "call_id": call.call_id,
                            "tool_name": call.name,
                            "status": "succeeded",
                            "retrying": True,
                            "retry_count": attempts - 1,
                        },
                    )
                self._emit(
                    "orchestration.tool.succeeded",
                    {
                        "run_id": record.run_id,
                        "call_id": call.call_id,
                        "tool_name": call.name,
                        "status": "succeeded",
                        "attempts": attempts,
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000, 3
                        ),
                    },
                )
                return result

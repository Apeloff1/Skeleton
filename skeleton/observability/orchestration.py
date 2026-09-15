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
from contextvars import ContextVar
from typing import Iterable

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
    ToolInvocation,
    ToolRegistry,
    ToolResult,
)
from skeleton.kernel.events import EventBus
from skeleton.observability.event_bridge import EventMetricsBridge


_CURRENT_CORRELATION_ID: ContextVar[str] = ContextVar(
    "skeleton_orchestration_correlation_id",
    default="",
)


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
    """Canonical orchestrator with metadata-only lifecycle events attached.

    Every instance owns an event bus and an attached :class:`EventMetricsBridge`
    by default, so choosing the observable runtime cannot silently drop lifecycle
    metrics. Callers that already own either primitive may inject them; the
    supplied bridge is attached to the supplied (or generated) bus exactly once
    by this runtime boundary.
    """

    def __init__(
        self,
        *,
        tools: ToolRegistry | None = None,
        tool_retry_budget: RetryBudget = RetryBudget(),
        max_turns: int = 16,
        event_bus: EventBus | None = None,
        metrics_bridge: EventMetricsBridge | None = None,
    ) -> None:
        super().__init__(
            tools=tools or ToolRegistry(),
            tool_retry_budget=tool_retry_budget,
            max_turns=max_turns,
        )
        self.event_bus = event_bus or EventBus()
        self.metrics_bridge = metrics_bridge or EventMetricsBridge()
        self.metrics_bridge.attach(self.event_bus)

    def _emit(self, topic: str, payload: dict[str, object]) -> None:
        self.event_bus.emit(
            topic,
            payload,
            correlation_id=_CURRENT_CORRELATION_ID.get(),
        )

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
        token = _CURRENT_CORRELATION_ID.set(effective_correlation_id)
        started = time.perf_counter()
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
            self._emit(
                "orchestration.run.cancelled",
                {
                    "run_id": effective_run_id,
                    "status": RunStatus.CANCELLED.value,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error_type": "CancelledError",
                },
            )
            raise
        else:
            self._emit(
                f"orchestration.run.{record.status.value}",
                {
                    "run_id": record.run_id,
                    "status": record.status.value,
                    "turns": record.turns,
                    "step_count": len(record.steps),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            )
            return record
        finally:
            _CURRENT_CORRELATION_ID.reset(token)

    async def _execute_tool(
        self,
        record: RunRecord,
        call: ToolInvocation,
        *,
        cancellation: CancellationToken | None,
        granted_capabilities: frozenset[ToolCapability],
    ) -> ToolResult:
        started = time.perf_counter()
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
            self._emit(
                f"orchestration.tool.{suffix}",
                {
                    "run_id": record.run_id,
                    "call_id": call.call_id,
                    "tool_name": call.name,
                    "status": suffix,
                    "attempts": attempts,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
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
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            )
            return result

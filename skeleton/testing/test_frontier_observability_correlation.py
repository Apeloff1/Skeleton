"""End-to-end correlation coverage for API -> orchestration -> tool telemetry."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from skeleton.api.correlation import request_correlation_id, run_with_request_correlation
from skeleton.frontier.orchestration import (
    OrchestrationDriver,
    RetryBudget,
    RunRecord,
    RunStatus,
    ToolInvocation,
    ToolRegistry,
    ToolResult,
    TransientToolError,
    TurnOutcome,
)
from skeleton.kernel.events import EventBus
from skeleton.observability.event_bridge import EventMetricsBridge
from skeleton.observability.orchestration import ObservableOrchestrator


class _Headers:
    def __init__(self, request_ids: list[str]) -> None:
        self._request_ids = list(request_ids)

    def getlist(self, name: str) -> list[str]:
        return list(self._request_ids) if name.lower() == "x-request-id" else []


class _Request:
    def __init__(self, request_ids: list[str]) -> None:
        self.headers = _Headers(request_ids)
        self.state = SimpleNamespace()


class _OneToolDriver(OrchestrationDriver):
    def __init__(self, *, arguments: dict[str, object] | None = None) -> None:
        self.requested = False
        self.arguments = arguments or {}

    async def next_turn(
        self,
        *,
        run: RunRecord,
        tool_results: tuple[ToolResult, ...],
    ) -> TurnOutcome:
        del run
        if not self.requested:
            self.requested = True
            return TurnOutcome(
                tool_calls=(
                    ToolInvocation(
                        call_id="call-123",
                        name="lookup",
                        arguments=self.arguments,
                    ),
                )
            )
        assert len(tool_results) == 1
        return TurnOutcome(output=tool_results[0].output, terminal=True)


class _TerminalDriver(OrchestrationDriver):
    async def next_turn(
        self,
        *,
        run: RunRecord,
        tool_results: tuple[ToolResult, ...],
    ) -> TurnOutcome:
        del run, tool_results
        return TurnOutcome(output="ok", terminal=True)


def _observed_orchestrator(
    handler,
    *,
    retry_budget: RetryBudget = RetryBudget(),
) -> tuple[ObservableOrchestrator, EventMetricsBridge]:
    tools = ToolRegistry()
    tools.register("lookup", handler)
    bus = EventBus()
    bridge = EventMetricsBridge()
    return (
        ObservableOrchestrator(
            tools=tools,
            tool_retry_budget=retry_budget,
            event_bus=bus,
            metrics_bridge=bridge,
        ),
        bridge,
    )


def test_observable_runtime_attaches_metrics_bridge_by_default() -> None:
    async def scenario() -> None:
        orchestrator = ObservableOrchestrator()

        record = await orchestrator.run(
            _TerminalDriver(),
            run_id="run-default-observability",
            correlation_id="req-default-observability",
        )

        assert record.status is RunStatus.COMPLETED
        events = orchestrator.metrics_bridge.events()
        assert [event.topic for event in events] == [
            "orchestration.run.started",
            "orchestration.run.completed",
        ]
        assert {event.correlation_id for event in events} == {
            "req-default-observability"
        }
        assert orchestrator.metrics_bridge.registry.get_counter(
            "observability.events_total",
            labels={"topic": "orchestration.run.started"},
        ) == 1.0
        assert orchestrator.metrics_bridge.registry.get_counter(
            "observability.events_total",
            labels={"topic": "orchestration.run.completed"},
        ) == 1.0

    asyncio.run(scenario())


def test_injected_metrics_bridge_is_runtime_bridge() -> None:
    bridge = EventMetricsBridge()
    bus = EventBus()
    orchestrator = ObservableOrchestrator(event_bus=bus, metrics_bridge=bridge)

    assert orchestrator.event_bus is bus
    assert orchestrator.metrics_bridge is bridge


def test_request_id_survives_api_to_run_to_tool_without_payload_leakage() -> None:
    async def scenario() -> None:
        orchestrator, bridge = _observed_orchestrator(
            lambda arguments: {"secret_output": arguments["secret_input"]}
        )
        request = _Request(["req-abc-123"])
        record = await run_with_request_correlation(
            orchestrator,
            request,
            _OneToolDriver(arguments={"secret_input": "do-not-log"}),
            run_id="run-123",
        )

        assert record.status is RunStatus.COMPLETED
        assert request.state.seal == "req-abc-123"
        assert request.state.request_id == "req-abc-123"

        events = bridge.events()
        topics = [event.topic for event in events]
        assert topics == [
            "orchestration.run.started",
            "orchestration.tool.started",
            "orchestration.tool.succeeded",
            "orchestration.run.completed",
        ]
        assert {event.correlation_id for event in events} == {"req-abc-123"}

        tool_events = [event for event in events if ".tool." in event.topic]
        assert tool_events
        for event in tool_events:
            assert event.payload["run_id"] == "run-123"
            assert event.payload["call_id"] == "call-123"
            assert event.payload["tool_name"] == "lookup"
            rendered = repr(event.payload)
            assert "do-not-log" not in rendered
            assert "secret_input" not in rendered
            assert "secret_output" not in rendered

    asyncio.run(scenario())


def test_existing_gate_seal_wins_over_request_header() -> None:
    request = _Request(["header-id"])
    request.state.seal = "gate-seal-123"

    resolved = request_correlation_id(request)

    assert resolved == "gate-seal-123"
    assert request.state.seal == "gate-seal-123"


def test_retry_event_is_correlated_and_does_not_store_exception_message() -> None:
    async def scenario() -> None:
        attempts = 0

        def handler(arguments):
            nonlocal attempts
            del arguments
            attempts += 1
            if attempts == 1:
                raise TransientToolError("token=retry-secret")
            return "ok"

        orchestrator, bridge = _observed_orchestrator(
            handler,
            retry_budget=RetryBudget(max_attempts=2),
        )
        record = await run_with_request_correlation(
            orchestrator,
            _Request(["req-retry"]),
            _OneToolDriver(),
            run_id="run-retry",
        )

        assert record.status is RunStatus.COMPLETED
        retry_events = [
            event for event in bridge.events() if event.topic == "orchestration.tool.retry"
        ]
        assert len(retry_events) == 1
        assert retry_events[0].correlation_id == "req-retry"
        assert retry_events[0].payload["retry_count"] == 1
        assert "retry-secret" not in repr(retry_events[0].payload)

    asyncio.run(scenario())


def test_tool_failure_event_exposes_type_not_secret_message() -> None:
    async def scenario() -> None:
        def handler(arguments):
            del arguments
            raise RuntimeError("password=failure-secret")

        orchestrator, bridge = _observed_orchestrator(handler)
        record = await run_with_request_correlation(
            orchestrator,
            _Request(["req-fail"]),
            _OneToolDriver(),
            run_id="run-fail",
        )

        assert record.status is RunStatus.FAILED
        failed = [
            event for event in bridge.events() if event.topic == "orchestration.tool.failed"
        ]
        assert len(failed) == 1
        assert failed[0].correlation_id == "req-fail"
        assert failed[0].payload["error_type"] == "ToolExecutionError"
        assert "failure-secret" not in repr(failed[0].payload)
        assert "password" not in repr(failed[0].payload)

    asyncio.run(scenario())


def test_duplicate_request_id_headers_fail_closed_to_generated_id() -> None:
    request = _Request(["one", "two"])
    resolved = request_correlation_id(request)

    assert resolved not in {"one", "two"}
    assert len(resolved) == 16
    assert request.state.seal == resolved
    assert request.state.request_id == resolved

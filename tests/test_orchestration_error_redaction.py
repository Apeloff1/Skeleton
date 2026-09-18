import asyncio

from skeleton.frontier.orchestration import (
    CanonicalOrchestrator,
    RetryBudget,
    RunStatus,
    StepStatus,
    ToolInvocation,
    ToolRegistry,
    TransientToolError,
    TurnOutcome,
)


_SECRET_DETAIL = "api-key=do-not-persist"


class _SingleToolDriver:
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name

    async def next_turn(self, *, run, tool_results):
        return TurnOutcome(
            tool_calls=(ToolInvocation("call-1", self.tool_name, {}),)
        )


def test_handler_exception_message_is_not_persisted_in_run_or_step_records():
    def explode(_arguments):
        raise RuntimeError(_SECRET_DETAIL)

    async def run():
        tools = ToolRegistry()
        tools.register("explode", explode)
        return await CanonicalOrchestrator(tools=tools).run(
            _SingleToolDriver("explode"),
            run_id="redacted-handler-error",
        )

    record = asyncio.run(run())

    assert record.status is RunStatus.FAILED
    assert record.error is not None
    assert "ToolExecutionError" in record.error
    assert "RuntimeError" in record.error
    assert _SECRET_DETAIL not in record.error

    tool_step = record.steps[-1]
    assert tool_step.status is StepStatus.FAILED
    assert tool_step.error is not None
    assert "ToolExecutionError" in tool_step.error
    assert "RuntimeError" in tool_step.error
    assert _SECRET_DETAIL not in tool_step.error


def test_transient_handler_message_is_redacted_when_retry_budget_is_exhausted():
    def retryable(_arguments):
        raise TransientToolError(_SECRET_DETAIL)

    async def run():
        tools = ToolRegistry()
        tools.register("retryable", retryable)
        orchestrator = CanonicalOrchestrator(
            tools=tools,
            tool_retry_budget=RetryBudget(max_attempts=2),
        )
        return await orchestrator.run(
            _SingleToolDriver("retryable"),
            run_id="redacted-transient-error",
        )

    record = asyncio.run(run())

    assert record.status is RunStatus.FAILED
    assert record.error is not None
    assert "RetryBudgetExceeded" in record.error
    assert _SECRET_DETAIL not in record.error

    tool_step = record.steps[-1]
    assert tool_step.status is StepStatus.FAILED
    assert tool_step.attempt == 2
    assert tool_step.error == "TransientToolError: retryable tool failure"
    assert _SECRET_DETAIL not in tool_step.error

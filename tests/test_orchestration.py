from __future__ import annotations

import asyncio

from skeleton.frontier.model_runtime import CancellationToken
from skeleton.frontier.orchestration import (
    CanonicalOrchestrator,
    InvalidTransitionError,
    RetryBudget,
    RunRecord,
    RunStatus,
    StepKind,
    StepStatus,
    ToolCapability,
    ToolInvocation,
    ToolRegistry,
    TransientToolError,
    TurnOutcome,
)


def test_happy_path_tool_turn_is_unambiguous():
    class Driver:
        def __init__(self):
            self.calls = 0

        async def next_turn(self, *, run, tool_results):
            self.calls += 1
            if self.calls == 1:
                assert tool_results == ()
                return TurnOutcome(
                    tool_calls=(ToolInvocation("c1", "echo", {"value": 7}),)
                )
            assert tool_results[0].output == {"echo": 7}
            return TurnOutcome(output="done", terminal=True)

    async def run():
        tools = ToolRegistry()
        tools.register("echo", lambda arguments: {"echo": arguments["value"]})
        orchestrator = CanonicalOrchestrator(tools=tools)
        record = await orchestrator.run(Driver(), run_id="run-1")
        assert record.status is RunStatus.COMPLETED
        assert record.output == "done"
        assert [step.kind for step in record.steps] == [
            StepKind.MODEL,
            StepKind.TOOL,
            StepKind.MODEL,
        ]
        assert all(step.status is StepStatus.SUCCEEDED for step in record.steps)

    asyncio.run(run())


def test_transient_tool_failure_uses_bounded_retry_budget():
    class Driver:
        def __init__(self):
            self.calls = 0

        async def next_turn(self, *, run, tool_results):
            self.calls += 1
            if self.calls == 1:
                return TurnOutcome(tool_calls=(ToolInvocation("c1", "flaky", {}),))
            assert tool_results[0].output == "ok"
            return TurnOutcome(output="done", terminal=True)

    class Flaky:
        def __init__(self):
            self.calls = 0

        async def __call__(self, arguments):
            self.calls += 1
            if self.calls < 3:
                raise TransientToolError("retry")
            return "ok"

    async def run():
        flaky = Flaky()
        tools = ToolRegistry()
        tools.register("flaky", flaky)
        record = await CanonicalOrchestrator(
            tools=tools,
            tool_retry_budget=RetryBudget(max_attempts=3),
        ).run(Driver())
        assert record.status is RunStatus.COMPLETED
        tool_step = next(step for step in record.steps if step.kind is StepKind.TOOL)
        assert tool_step.attempt == 3
        assert tool_step.status is StepStatus.SUCCEEDED
        assert flaky.calls == 3

    asyncio.run(run())


def test_exhausted_tool_failure_terminates_run_and_step():
    class Driver:
        async def next_turn(self, *, run, tool_results):
            return TurnOutcome(tool_calls=(ToolInvocation("c1", "broken", {}),))

    async def broken(arguments):
        raise TransientToolError("still broken")

    async def run():
        tools = ToolRegistry()
        tools.register("broken", broken)
        record = await CanonicalOrchestrator(
            tools=tools,
            tool_retry_budget=RetryBudget(max_attempts=2),
        ).run(Driver())
        assert record.status is RunStatus.FAILED
        assert "exhausted retry budget" in record.error
        tool_step = record.steps[-1]
        assert tool_step.status is StepStatus.FAILED
        assert tool_step.attempt == 2
        assert not any(step.status is StepStatus.RUNNING for step in record.steps)

    asyncio.run(run())


def test_precancelled_run_has_no_ambiguous_steps():
    class Driver:
        async def next_turn(self, *, run, tool_results):
            raise AssertionError("driver should not be called")

    async def run():
        token = CancellationToken()
        token.cancel()
        record = await CanonicalOrchestrator().run(Driver(), cancellation=token)
        assert record.status is RunStatus.CANCELLED
        assert record.steps == []

    asyncio.run(run())


def test_turn_budget_fails_closed():
    class Driver:
        async def next_turn(self, *, run, tool_results):
            return TurnOutcome(tool_calls=(ToolInvocation("c", "echo", {}),))

    async def run():
        tools = ToolRegistry()
        tools.register("echo", lambda arguments: "ok")
        record = await CanonicalOrchestrator(tools=tools, max_turns=2).run(Driver())
        assert record.status is RunStatus.FAILED
        assert record.turns == 2
        assert "maximum turn budget exhausted" in record.error
        assert all(
            step.status not in {StepStatus.RUNNING, StepStatus.RETRYING}
            for step in record.steps
        )

    asyncio.run(run())


def test_invalid_terminal_transition_is_rejected():
    record = RunRecord("r")
    record.transition(RunStatus.RUNNING)
    record.transition(RunStatus.COMPLETED)
    try:
        record.transition(RunStatus.FAILED)
    except InvalidTransitionError:
        pass
    else:
        raise AssertionError("terminal state transition was accepted")


def test_sensitive_tool_capability_is_denied_by_default():
    called = False

    class Driver:
        async def next_turn(self, *, run, tool_results):
            return TurnOutcome(
                tool_calls=(ToolInvocation("network-call", "fetch", {}),)
            )

    def fetch(_arguments):
        nonlocal called
        called = True
        return "should not run"

    async def run():
        tools = ToolRegistry()
        tools.register("fetch", fetch, capabilities={ToolCapability.NETWORK})
        record = await CanonicalOrchestrator(tools=tools).run(
            Driver(), run_id="cap-denied"
        )

        assert record.status is RunStatus.FAILED
        assert called is False
        assert "denied capabilities: network" in record.error
        tool_step = record.steps[-1]
        assert tool_step.kind is StepKind.TOOL
        assert tool_step.status is StepStatus.FAILED
        assert tool_step.attempt == 1
        assert len(record.capability_decisions) == 1
        decision = record.capability_decisions[0]
        assert decision.run_id == "cap-denied"
        assert decision.call_id == "network-call"
        assert decision.tool_name == "fetch"
        assert decision.capability is ToolCapability.NETWORK
        assert decision.allowed is False

    asyncio.run(run())


def test_explicit_capability_grant_allows_tool_and_audits_decision():
    class Driver:
        def __init__(self):
            self.calls = 0

        async def next_turn(self, *, run, tool_results):
            self.calls += 1
            if self.calls == 1:
                return TurnOutcome(
                    tool_calls=(ToolInvocation("repo-call", "mutate", {}),)
                )
            assert tool_results[0].output == "changed"
            return TurnOutcome(output="done", terminal=True)

    async def run():
        tools = ToolRegistry()
        tools.register(
            "mutate",
            lambda _arguments: "changed",
            capabilities={ToolCapability.REPOSITORY_MUTATION},
        )
        record = await CanonicalOrchestrator(tools=tools).run(
            Driver(),
            run_id="cap-allowed",
            capabilities={ToolCapability.REPOSITORY_MUTATION},
        )

        assert record.status is RunStatus.COMPLETED
        assert record.output == "done"
        assert len(record.capability_decisions) == 1
        decision = record.capability_decisions[0]
        assert decision.run_id == "cap-allowed"
        assert decision.call_id == "repo-call"
        assert decision.tool_name == "mutate"
        assert decision.capability is ToolCapability.REPOSITORY_MUTATION
        assert decision.allowed is True

    asyncio.run(run())


def test_tool_capabilities_reject_unknown_values():
    tools = ToolRegistry()
    try:
        tools.register("bad", lambda _arguments: None, capabilities={"root"})
    except ValueError as exc:
        assert "unknown tool capability: root" in str(exc)
    else:
        raise AssertionError("unknown tool capability was accepted")

from __future__ import annotations

import pytest

from skeleton.jeeves.agent.cortex import JeevesCortex
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.types import (
    AgentResult,
    Goal,
    TerminationReason,
    Usage,
)


class TickClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


class ExplodingCortex(JeevesCortex):
    def observe_checkpoint(self, *args, **kwargs):
        raise RuntimeError("synthetic cortex failure")


def _inputs(run_id: str = "run-cortex") -> RunInputs:
    return RunInputs(
        goal=Goal(
            "goal-cortex",
            "Produce a bounded, evidence-aware answer.",
            success_criteria=("Do not bypass runtime safety controls.",),
        ),
        tenant_id="tenant-cortex",
        user_id="user-cortex",
        workspace_id="workspace-cortex",
        session_id="session-cortex",
        run_id=run_id,
    )


def _runtime(
    clock: TickClock,
    *,
    cortex: JeevesCortex | None = None,
    cortex_required: bool = False,
    cortex_enabled: bool = True,
) -> FrontierJeevesAgentRuntime:
    provider = DeterministicProvider(("unused",))
    return FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        cortex=cortex,
        cortex_enabled=cortex_enabled,
        cortex_required=cortex_required,
        wall_clock=clock,
        monotonic=clock,
    )


def test_frontier_runtime_automatically_feeds_cortex_advice_into_run_scratch() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-cortex-auto")

    state = runtime._new_state("run-cortex-auto", inputs)

    advisory = state.scratch.get(runtime._CORTEX_ASSESSMENT_KEY)
    assert advisory is not None
    assert advisory["authority"] == "advisory_only"
    assert advisory["checkpoint_sequence"] == 1
    assert advisory["checkpoint_fingerprint"] == runtime.checkpointer.latest(
        "run-cortex-auto"
    ).fingerprint
    assert advisory["mode"]
    assert advisory["decision_id"]
    assert "cortex:assessment" in state.scratch.render(maximum_chars=16_000)

    cortex_state = runtime.cortex.state("run-cortex-auto")
    assert cortex_state is not None
    assert cortex_state.checkpoint_count == 1

    summary = runtime.cortex_summary()
    assert summary["enabled"] is True
    assert summary["authority"] == "advisory_only"


def test_frontier_runtime_attaches_cortex_report_to_terminal_result() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-cortex-result")
    state = runtime._new_state("run-cortex-result", inputs)
    result = AgentResult(
        run_id=state.run_id,
        goal_id=inputs.goal.goal_id,
        success=True,
        reason=TerminationReason.GOAL_REACHED,
        answer="Bounded result.",
        usage=Usage(),
    )

    enriched = runtime._observe_cortex_result(state, result)

    assert enriched.metadata["cortex"]["status"] == "observed"
    assert enriched.metadata["cortex"]["authority"] == "advisory_only"
    assert enriched.metadata["cortex"]["belief_count"] >= 1
    assert enriched.metadata["cortex"]["report_fingerprint"]
    assert runtime.cortex.report(state.run_id) is not None


def test_optional_cortex_failure_is_visible_without_becoming_an_authority_bypass() -> None:
    clock = TickClock()
    cortex = ExplodingCortex(clock=clock, monotonic=clock)
    runtime = _runtime(clock, cortex=cortex)

    state = runtime._new_state("run-cortex-degraded", _inputs("run-cortex-degraded"))

    error = state.scratch.get(runtime._CORTEX_ERROR_KEY)
    assert error["stage"] == "checkpoint"
    assert error["error_type"] == "RuntimeError"
    assert error["authority"] == "advisory_only"
    assert runtime.checkpointer.latest("run-cortex-degraded") is not None


def test_required_cortex_fails_closed_on_supervisor_error() -> None:
    clock = TickClock()
    cortex = ExplodingCortex(clock=clock, monotonic=clock)
    runtime = _runtime(clock, cortex=cortex, cortex_required=True)

    with pytest.raises(RuntimeError, match="synthetic cortex failure"):
        runtime._new_state("run-cortex-required", _inputs("run-cortex-required"))


def test_cortex_can_be_explicitly_disabled_for_compatibility() -> None:
    clock = TickClock()
    runtime = _runtime(clock, cortex_enabled=False)
    state = runtime._new_state("run-cortex-disabled", _inputs("run-cortex-disabled"))

    assert runtime.cortex is None
    assert state.scratch.get(runtime._CORTEX_ASSESSMENT_KEY) is None
    assert runtime.cortex_summary() == {"enabled": False, "required": False}

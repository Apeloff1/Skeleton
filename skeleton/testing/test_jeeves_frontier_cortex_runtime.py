from __future__ import annotations

import pytest

from skeleton.jeeves.agent.action_model import SkillSpec
from skeleton.jeeves.agent.cortex import CortexError, JeevesCortex
from skeleton.jeeves.agent.evidence import EvidenceLedger
from skeleton.jeeves.agent.execution_audit import AuditEventKind
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.tools import ToolSpec
from skeleton.jeeves.agent.types import (
    AgentResult,
    Goal,
    Plan,
    PlanStep,
    RiskTier,
    TerminationReason,
    ToolObservation,
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


def test_planner_receives_cortex_advisory_through_compiled_context() -> None:
    clock = TickClock()
    provider = DeterministicProvider(
        (
            (
                '{"rationale":"bounded","steps":[{"id":"step-1","title":"Reason",'
                '"description":"Analyze the bounded goal.","dependencies":[],"tool":null,'
                '"arguments":{},"expected_outcome":"bounded analysis","verification":"",'
                '"risk":"read_only","max_attempts":1}]}'
            ),
        )
    )
    runtime = FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    inputs = _inputs("run-cortex-planner-context")
    state = runtime._new_state("run-cortex-planner-context", inputs)

    runtime._plan(state)

    assert len(provider.requests) == 1
    user_message = next(
        message.content
        for message in provider.requests[0].messages
        if message.role.value == "user"
    )
    assert "cortex:assessment" in user_message
    assert "advisory_only" in user_message
    assert "checkpoint_sequence" in user_message


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


def test_required_cortex_cannot_be_disabled() -> None:
    clock = TickClock()
    with pytest.raises(ValueError, match="cortex_required"):
        _runtime(clock, cortex_enabled=False, cortex_required=True)


def test_cortex_learning_preserves_audited_tool_risk_and_verification_score() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-cortex-learning")
    state = runtime._new_state("run-cortex-learning", inputs)
    runtime.cortex.register_skill(
        SkillSpec.tool("mutate_value", risk=RiskTier.READ_ONLY)
    )
    observation = ToolObservation(
        call_id="call-risk-bound",
        tool_name="mutate_value",
        ok=True,
        payload={"status": "ok"},
        latency_ms=3.0,
    )
    result = AgentResult(
        run_id=state.run_id,
        goal_id=inputs.goal.goal_id,
        success=True,
        reason=TerminationReason.GOAL_REACHED,
        answer="Mutation was verified.",
        usage=Usage(tool_calls=1),
        observations=(observation,),
    )

    report = runtime.cortex.observe_result(
        inputs,
        result,
        verification_scores={"call-risk-bound": 0.73},
        action_costs={"call-risk-bound": 4.25},
        action_risks={"call-risk-bound": RiskTier.MUTATING},
    )

    assert len(report.learned_skill_ids) == 1
    profile = runtime.cortex.skills.require_profile(report.learned_skill_ids[0])
    assert profile.spec.risk is RiskTier.MUTATING
    episodes = runtime.cortex.skills.episodes(
        skill_id=profile.spec.skill_id,
        run_id=state.run_id,
    )
    assert len(episodes) == 1
    assert episodes[0].verification_score == pytest.approx(0.73)
    assert episodes[0].cost == pytest.approx(4.25)
    assert episodes[0].verified is True


def test_frontier_cortex_learning_signals_are_derived_from_guard_audit() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    state = runtime._new_state(
        "run-cortex-audit-signals",
        _inputs("run-cortex-audit-signals"),
    )
    ledger = runtime.runtime_guard.audit_store.get_or_create(state.run_id)
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "call_id": "call-audited",
            "risk": RiskTier.EXTERNAL.value,
        },
        operation_id="operation-audited",
    )
    ledger.append(
        AuditEventKind.EXECUTION_FINALIZED,
        {"verification_score": 0.81},
        operation_id="operation-audited",
    )

    scores, costs, risks = runtime._cortex_learning_signals(state.run_id)

    assert scores == {"call-audited": pytest.approx(0.81)}
    assert costs == {}
    assert risks == {"call-audited": RiskTier.EXTERNAL}


def test_cortex_current_risk_uses_host_tool_risk_not_model_understatement() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    runtime.tools.register(
        ToolSpec(
            name="external_write",
            description="External side effect used to verify risk binding.",
            risk=RiskTier.EXTERNAL,
        ),
        lambda arguments, context: {"ok": True},
    )
    inputs = _inputs("run-cortex-host-risk")
    state = runtime._new_state("run-cortex-host-risk", inputs)
    state.plan = Plan(
        plan_id="plan-host-risk",
        goal_id=inputs.goal.goal_id,
        steps=(
            PlanStep(
                step_id="step-host-risk",
                title="External write",
                description="Exercise host risk binding.",
                tool="external_write",
                risk=RiskTier.READ_ONLY,
            ),
        ),
    )

    assert runtime._cortex_current_risk(state) is RiskTier.EXTERNAL


def test_resume_rebinds_existing_cortex_run_to_restored_evidence_ledger() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-cortex-resume")
    original = runtime._new_state("run-cortex-resume", inputs)
    checkpoint = runtime.checkpointer.latest(original.run_id)
    assert checkpoint is not None
    cortex_state = runtime.cortex.require_state(original.run_id)
    assert cortex_state.world.evidence_ledger is original.ledger
    assert cortex_state.checkpoint_count == 1

    restored = runtime._state_from_checkpoint(inputs, checkpoint)

    resumed_cortex = runtime.cortex.require_state(original.run_id)
    assert resumed_cortex.world.evidence_ledger is restored.ledger
    assert resumed_cortex.world.evidence_ledger is not original.ledger
    assert resumed_cortex.checkpoint_count == 1
    advisory = restored.scratch.get(runtime._CORTEX_ASSESSMENT_KEY)
    assert advisory["checkpoint_sequence"] == checkpoint.sequence


def test_cortex_rejects_reusing_run_id_across_scope_boundaries() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-cortex-scope")
    state = runtime._new_state("run-cortex-scope", inputs)
    mismatched = RunInputs(
        goal=inputs.goal,
        tenant_id=inputs.tenant_id,
        user_id=inputs.user_id,
        workspace_id="other-workspace",
        session_id=inputs.session_id,
        run_id=inputs.run_id,
    )

    with pytest.raises(CortexError, match="scope"):
        runtime.cortex.begin(
            mismatched,
            run_id=state.run_id,
            evidence_ledger=state.ledger,
        )


def test_fresh_cortex_can_rebind_shared_world_model_to_restored_ledger() -> None:
    clock = TickClock()
    first = JeevesCortex(clock=clock, monotonic=clock)
    inputs = _inputs("run-cortex-shared-world")
    first_ledger = EvidenceLedger(clock=clock)
    first_state = first.begin(
        inputs,
        run_id=inputs.run_id,
        evidence_ledger=first_ledger,
    )
    restored_ledger = EvidenceLedger(clock=clock)

    second = JeevesCortex(
        world_model=first.world_model,
        clock=clock,
        monotonic=clock,
    )
    restored_state = second.begin(
        inputs,
        run_id=inputs.run_id,
        evidence_ledger=restored_ledger,
    )

    assert restored_state.world is first_state.world
    assert restored_state.world.evidence_ledger is restored_ledger


def test_repeated_checkpoint_assessment_is_idempotent() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-cortex-idempotent")
    state = runtime._new_state("run-cortex-idempotent", inputs)
    checkpoint = runtime.checkpointer.latest(state.run_id)
    assert checkpoint is not None
    first = runtime.cortex.observe_checkpoint(inputs, checkpoint)
    after_first = runtime.cortex.require_state(state.run_id)

    second = runtime.cortex.observe_checkpoint(inputs, checkpoint)
    after_second = runtime.cortex.require_state(state.run_id)

    assert second == first
    assert second.decision.decision_id == first.decision.decision_id
    assert after_first.checkpoint_count == 1
    assert after_second.checkpoint_count == 1
    assert len(runtime.cortex.meta.history(run_id=state.run_id)) == 1

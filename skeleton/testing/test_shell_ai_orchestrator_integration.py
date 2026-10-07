"""End-to-end AI shell orchestration over the real bounded shell service."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.approval import AIApprovalError
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.tool_guard import AIToolGuardRegistry, ToolGuardDecision, ToolGuardTripwire
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentConstraint, IntentKind
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def command_catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec(
                    "python",
                    sys.executable,
                    tags=frozenset({"inspect", "test", "analyze"}),
                ),
                ArgumentPolicy.allow_any(),
                description="Bounded Python runtime tool.",
            ),
        )
    )


def effect_registry():
    return EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.READ_FILESYSTEM}),
                idempotent=True,
                reversible=True,
            ),
        )
    )


def shell_service(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    runner = ShellRunner(
        ShellPolicy(
            executables={"python": sys.executable},
            cwd_roots=(root,),
            default_timeout=2,
            max_timeout=5,
            max_output_bytes=4096,
            max_input_bytes=4096,
            max_env_bytes=4096,
            max_args=32,
            max_arg_bytes=4096,
        )
    )
    service = ShellService(ShellExecutor(runner), concurrency_capacity=2)
    service.start()
    return service


def intent():
    return AIIntent(
        "intent-1",
        "Print a deterministic verification marker.",
        kind=IntentKind.TEST,
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            max_steps=4,
            max_timeout_seconds=2,
            allow_network=False,
            allow_writes=False,
            allow_destructive=False,
            require_reversible=True,
        ),
    )


def model_port(*, confidence=0.95, uncertainty=0.05, command="python"):
    def propose(request):
        plan = AIPlanProposal(
            "proposal-1",
            request.intent.intent_id,
            (
                AIAction(
                    "step-1",
                    command,
                    ("-c", "print('AI_SHELL_OK')"),
                    timeout_seconds=1,
                    purpose="produce verification marker",
                ),
            ),
            confidence=confidence,
            uncertainty=uncertainty,
            model_id="fake-structured-model",
        )
        return AIModelResponse(request.request_id, plan)

    return CallableAIModelPort("fake-structured-model", propose)


def orchestrator(tmp_path, *, policy=None, model=None, effects=None, guards=None):
    effect_set = effects or effect_registry()
    tool_catalog = AIToolCatalog(command_catalog())
    model = model or model_port()
    policy = policy or AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    planner = AIPlanner(
        model,
        tool_catalog,
        AIToolRouter(tool_catalog, effect_set),
        policy_fingerprint=policy.fingerprint,
    )
    critic = AIPlanCritic(effect_set, policy)
    compiler = AIPlanCompiler(effect_set)
    return AIShellOrchestrator(
        planner=planner,
        critic=critic,
        compiler=compiler,
        shell_service=shell_service(tmp_path),
        guards=guards,
    )


def test_ai_orchestrator_autonomous_happy_path(tmp_path):
    ai = orchestrator(tmp_path)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    assert session.phase is AISessionPhase.REVIEW
    assert review.critique.accepted_for_execution
    assert review.compiled is not None

    result = ai.execute(
        session,
        review,
        context=ExecutionContext("corr-1", principal="jeeves"),
    )
    assert result.ok
    assert session.phase is AISessionPhase.COMPLETE
    assert result.report.steps[0].dispatch.outcome.result.stdout.strip() == b"AI_SHELL_OK"
    assert result.verification.verified
    assert len(ai.memory.snapshot()) == 1
    assert ai.calibration.get("fake-structured-model").attempts == 1
    assert ai.journal.verify()


def test_ai_orchestrator_provenance_binds_policy_tools_effects(tmp_path):
    ai = orchestrator(tmp_path)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    result = ai.execute(
        session,
        review,
        context=ExecutionContext("corr-1", principal="jeeves"),
    )
    provenance = result.provenance
    assert provenance.policy_fingerprint == ai.planner.policy_fingerprint
    assert provenance.tool_catalog_digest == ai.planner.catalog.digest
    assert provenance.effect_digest == ai.compiler.effects.digest
    assert provenance.receipt_root == ai.shell_service.receipts.root_hash()


def test_ai_orchestrator_review_uses_shared_budget(tmp_path):
    ai = orchestrator(tmp_path)
    session = AIShellSession("session-1", intent())
    ai.review(session)
    usage = ai.budget.snapshot()
    assert usage.model_calls == 1
    assert usage.critique_calls == 1
    assert ai.planner.budget is ai.budget


def test_ai_orchestrator_human_approval_flow(tmp_path):
    policy = AIShellPolicy(
        autonomy=AutonomyMode.PROPOSE,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    ai = orchestrator(tmp_path, policy=policy)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    assert review.critique.requires_approval
    approval = ai.approve(
        session,
        review,
        principal="jeeves",
        approved_by="operator",
    )
    result = ai.execute(
        session,
        review,
        context=ExecutionContext("corr-1", principal="jeeves"),
        approval=approval,
    )
    assert result.ok
    assert result.provenance.approval_id == approval.approval_id


def test_ai_orchestrator_approval_cannot_cross_principal(tmp_path):
    policy = AIShellPolicy(
        autonomy=AutonomyMode.PROPOSE,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    ai = orchestrator(tmp_path, policy=policy)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    approval = ai.approve(
        session,
        review,
        principal="alice",
        approved_by="operator",
    )
    with pytest.raises(AIApprovalError):
        ai.execute(
            session,
            review,
            context=ExecutionContext("corr-1", principal="bob"),
            approval=approval,
        )


def test_ai_orchestrator_requires_approval_when_policy_says_so(tmp_path):
    policy = AIShellPolicy(
        autonomy=AutonomyMode.PROPOSE,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    ai = orchestrator(tmp_path, policy=policy)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    with pytest.raises(RuntimeError):
        ai.execute(
            session,
            review,
            context=ExecutionContext("corr-1", principal="jeeves"),
        )
    assert session.phase is AISessionPhase.REVIEW


def test_ai_orchestrator_low_confidence_denied(tmp_path):
    ai = orchestrator(
        tmp_path,
        model=model_port(confidence=0.1),
        policy=AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            min_confidence=0.8,
        ),
    )
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    assert review.compiled is None
    with pytest.raises(RuntimeError):
        ai.execute(
            session,
            review,
            context=ExecutionContext("corr-1", principal="jeeves"),
        )
    assert session.phase is AISessionPhase.DENIED


def test_ai_orchestrator_unknown_effect_contract_denied(tmp_path):
    ai = orchestrator(
        tmp_path,
        effects=EffectRegistry(),
        policy=AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            deny_unknown_effects=True,
        ),
    )
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    assert not review.critique.accepted_for_execution
    assert review.compiled is None


def test_ai_orchestrator_input_tool_guard_blocks_before_execution(tmp_path):
    guards = AIToolGuardRegistry()
    guards.register_input(
        "python",
        lambda action: ToolGuardDecision(False, "blocked", "test tripwire"),
    )
    ai = orchestrator(tmp_path, guards=guards)
    session = AIShellSession("session-1", intent())
    with pytest.raises(ToolGuardTripwire):
        ai.review(session)
    assert len(ai.shell_service.receipts.snapshot()) == 0


def test_ai_orchestrator_output_tool_guard_marks_session_failed(tmp_path):
    guards = AIToolGuardRegistry()
    guards.register_output(
        "python",
        lambda action, observation: ToolGuardDecision(
            False,
            "output_blocked",
            "test output tripwire",
        ),
    )
    ai = orchestrator(tmp_path, guards=guards)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    with pytest.raises(ToolGuardTripwire):
        ai.execute(
            session,
            review,
            context=ExecutionContext("corr-1", principal="jeeves"),
        )
    assert session.phase is AISessionPhase.FAILED
    assert any(event.kind == "ai.plan.failed" for event in ai.journal.snapshot())


def test_ai_orchestrator_model_never_receives_executable_path(tmp_path):
    observed = {}

    def propose(request):
        observed["request"] = request.to_dict()
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "proposal-1",
                request.intent.intent_id,
                (AIAction("step-1", "python", ("-V",)),),
                confidence=0.95,
                uncertainty=0.05,
                model_id="observer",
            ),
        )

    ai = orchestrator(tmp_path, model=CallableAIModelPort("observer", propose))
    session = AIShellSession("session-1", intent())
    ai.review(session)
    assert sys.executable not in str(observed["request"])


def test_ai_orchestrator_journal_has_no_child_output(tmp_path):
    ai = orchestrator(tmp_path)
    session = AIShellSession("session-1", intent())
    review = ai.review(session)
    ai.execute(
        session,
        review,
        context=ExecutionContext("corr-1", principal="jeeves"),
    )
    assert "AI_SHELL_OK" not in str([event.to_dict() for event in ai.journal.snapshot()])

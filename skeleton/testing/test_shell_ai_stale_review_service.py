"""Stale-plan, human review view, and AI shell service tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.review import AIReviewBuilder
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.session import AISessionPhase
from skeleton.shells.ai.stale_guard import AIPlanStaleGuard, StalenessKind
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def catalog(description="python"):
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable, tags=frozenset({"inspect"})),
                ArgumentPolicy.allow_any(),
                description=description,
            ),
        )
    )


def effects(extra=False):
    items = [
        EffectContract(
            "python",
            frozenset({EffectKind.READ_FILESYSTEM}),
            idempotent=True,
            reversible=True,
        )
    ]
    if extra:
        items.append(
            EffectContract(
                "unused",
                frozenset({EffectKind.NETWORK}),
                reversible=False,
            )
        )
    return EffectRegistry(tuple(items))


def intent():
    return AIIntent("i", "print safe marker")


def proposal():
    return AIPlanProposal(
        "p",
        "i",
        (AIAction("a", "python", ("-c", "print('OK')")),),
        confidence=0.95,
        uncertainty=0.05,
        model_id="m",
    )


def model():
    from skeleton.shells.ai.protocol import AIModelResponse
    return CallableAIModelPort(
        "m",
        lambda request: AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "p",
                request.intent.intent_id,
                (AIAction("a", "python", ("-c", "print('OK')")),),
                confidence=0.95,
                uncertainty=0.05,
                model_id="m",
            ),
        ),
    )


def shell(tmp_path):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
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
    service = ShellService(ShellExecutor(runner))
    service.start()
    return service


def build_ai_service(tmp_path, *, policy=None):
    policy = policy or AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    command_catalog = catalog()
    tool_catalog = AIToolCatalog(command_catalog)
    effect_registry = effects()
    planner = AIPlanner(
        model(),
        tool_catalog,
        AIToolRouter(tool_catalog, effect_registry),
        policy_fingerprint=policy.fingerprint,
    )
    orchestrator = AIShellOrchestrator(
        planner=planner,
        critic=AIPlanCritic(effect_registry, policy),
        compiler=AIPlanCompiler(effect_registry),
        shell_service=shell(tmp_path),
    )
    governance = AIShellGovernance(AIPolicyStore(policy))
    diagnostics = AIShellDiagnostics(tool_catalog, effect_registry, policy, model())
    service = AIShellService(orchestrator, diagnostics, governance)
    service.start()
    return service


def test_review_view_has_effects_and_no_executable_path():
    registry = effects()
    critique = AIPlanCritic(
        registry,
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    ).critique(intent(), proposal())
    view = AIReviewBuilder(registry).build(intent(), proposal(), critique)
    assert view.actions[0].effects == ("read_filesystem",)
    assert sys.executable not in str(view.to_dict())


def test_review_view_exposes_exact_argv():
    registry = effects()
    critique = AIPlanCritic(
        registry,
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
    ).critique(intent(), proposal())
    view = AIReviewBuilder(registry).build(intent(), proposal(), critique)
    assert view.actions[0].args == ("-c", "print('OK')")


def test_stale_guard_clean_when_unchanged(tmp_path):
    policy = AIPolicyStore(
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    ).current()
    compiled = AIPlanCompiler(effects()).compile(intent(), proposal())
    tools = AIToolCatalog(catalog())
    registry = effects()
    pin = AIPlanStaleGuard.pin(
        intent(),
        proposal(),
        compiled,
        tools,
        registry,
        policy,
    )
    report = AIPlanStaleGuard.inspect(
        pin,
        intent=intent(),
        proposal=proposal(),
        compiled=compiled,
        catalog=tools,
        effects=registry,
        policy=policy,
    )
    assert report.ok


def test_stale_guard_detects_effect_drift():
    store = AIPolicyStore()
    compiled = AIPlanCompiler(effects()).compile(intent(), proposal())
    tools = AIToolCatalog(catalog())
    pin = AIPlanStaleGuard.pin(
        intent(),
        proposal(),
        compiled,
        tools,
        effects(),
        store.current(),
    )
    report = AIPlanStaleGuard.inspect(
        pin,
        intent=intent(),
        proposal=proposal(),
        compiled=compiled,
        catalog=tools,
        effects=effects(extra=True),
        policy=store.current(),
    )
    assert report.stale
    assert any(item.kind is StalenessKind.EFFECTS for item in report.findings)


def test_stale_guard_detects_tool_catalog_drift():
    store = AIPolicyStore()
    compiled = AIPlanCompiler(effects()).compile(intent(), proposal())
    original = AIToolCatalog(catalog("old"))
    pin = AIPlanStaleGuard.pin(
        intent(),
        proposal(),
        compiled,
        original,
        effects(),
        store.current(),
    )
    report = AIPlanStaleGuard.inspect(
        pin,
        intent=intent(),
        proposal=proposal(),
        compiled=compiled,
        catalog=AIToolCatalog(catalog("new")),
        effects=effects(),
        policy=store.current(),
    )
    assert any(item.kind is StalenessKind.TOOL_CATALOG for item in report.findings)


def test_stale_guard_detects_policy_drift():
    store = AIPolicyStore()
    compiled = AIPlanCompiler(effects()).compile(intent(), proposal())
    tools = AIToolCatalog(catalog())
    pin = AIPlanStaleGuard.pin(
        intent(),
        proposal(),
        compiled,
        tools,
        effects(),
        store.current(),
    )
    new = store.replace(
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    )
    report = AIPlanStaleGuard.inspect(
        pin,
        intent=intent(),
        proposal=proposal(),
        compiled=compiled,
        catalog=tools,
        effects=effects(),
        policy=new,
    )
    assert any(item.kind is StalenessKind.POLICY for item in report.findings)


def test_ai_service_happy_path_executes_real_process(tmp_path):
    service = build_ai_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, view = service.review(session)
    assert view.proposal_id == "p"
    result = service.execute(
        session,
        review,
        context=ExecutionContext("c", principal="jeeves"),
    )
    assert result.ok
    assert session.phase is AISessionPhase.COMPLETE


def test_ai_service_rejects_policy_drift_after_review(tmp_path):
    service = build_ai_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    service.governance.policy_store.replace(
        AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            max_actions=31,
            min_confidence=0.5,
            max_uncertainty=0.5,
        )
    )
    with pytest.raises(RuntimeError, match="stale"):
        service.execute(
            session,
            review,
            context=ExecutionContext("c", principal="jeeves"),
        )


def test_ai_service_quarantined_model_blocked(tmp_path):
    from skeleton.shells.ai.quarantine import QuarantineTarget

    service = build_ai_service(tmp_path)
    service.governance.quarantine.quarantine(
        QuarantineTarget.MODEL,
        "m",
        reason="incident",
        actor="operator",
    )
    session = service.new_session(intent(), session_id="s")
    with pytest.raises(RuntimeError, match="quarantined"):
        service.review(session)


def test_ai_service_not_started_rejects_session(tmp_path):
    policy = AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    command_catalog = catalog()
    tool_catalog = AIToolCatalog(command_catalog)
    effect_registry = effects()
    planner = AIPlanner(
        model(),
        tool_catalog,
        AIToolRouter(tool_catalog, effect_registry),
        policy_fingerprint=policy.fingerprint,
    )
    orchestrator = AIShellOrchestrator(
        planner=planner,
        critic=AIPlanCritic(effect_registry, policy),
        compiler=AIPlanCompiler(effect_registry),
        shell_service=shell(tmp_path),
    )
    service = AIShellService(
        orchestrator,
        AIShellDiagnostics(tool_catalog, effect_registry, policy, model()),
        AIShellGovernance(AIPolicyStore(policy)),
    )
    with pytest.raises(RuntimeError):
        service.new_session(intent())


def test_ai_service_status_reports_shell_ready(tmp_path):
    service = build_ai_service(tmp_path)
    status = service.status()
    assert status.phase.value == "ready"
    assert status.shell_phase == "ready"

"""High-assurance sealed execution integration over the real shell service."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority, ExecutionSealError
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.preconditions import (
    Preconditions,
    PreconditionChecker,
    ResourcePrecondition,
)
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry, SealReplay
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentConstraint
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(char):
    return char * 64


def command_catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
                description="python",
            ),
        )
    )


def effects():
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


def model():
    def propose(request):
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "p",
                request.intent.intent_id,
                (
                    AIAction(
                        "a",
                        "python",
                        ("-c", "print('SEALED_OK')"),
                        timeout_seconds=1,
                    ),
                ),
                confidence=0.95,
                uncertainty=0.05,
                model_id="m",
            ),
        )
    return CallableAIModelPort("m", propose)


def intent():
    return AIIntent(
        "i",
        "print a sealed marker",
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            max_steps=2,
            max_timeout_seconds=2,
            require_reversible=True,
        ),
    )


def build_service(tmp_path, *, autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS):
    policy = AIShellPolicy(
        autonomy=autonomy,
        min_confidence=0.5,
        max_uncertainty=0.5,
    )
    commands = command_catalog()
    tool_catalog = AIToolCatalog(commands)
    effect_registry = effects()
    root = tmp_path / "root"
    root.mkdir()
    shell = ShellService(
        ShellExecutor(
            ShellRunner(
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
        )
    )
    shell.start()
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
        shell_service=shell,
    )
    service = AIShellService(
        orchestrator,
        AIShellDiagnostics(
            tool_catalog,
            effect_registry,
            policy,
            model(),
        ),
        AIShellGovernance(AIPolicyStore(policy)),
    )
    service.start()
    return service


def test_sealed_execution_happy_path(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    conditions = Preconditions(
        (ResourcePrecondition("repo", fp("a")),)
    )
    checker = PreconditionChecker(lambda resource: fp("a"))
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        preconditions=conditions,
    )
    result, report, use = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        preconditions=conditions,
        precondition_checker=checker,
    )
    assert result.ok
    assert report is not None and report.ok
    assert registry.used(seal.seal_id)
    assert use.principal == "alice"
    assert result.report.steps[0].dispatch.outcome.result.stdout.strip() == b"SEALED_OK"


def test_precondition_drift_blocks_before_child_execution(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    conditions = Preconditions(
        (ResourcePrecondition("repo", fp("a")),)
    )
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        preconditions=conditions,
    )
    with pytest.raises(RuntimeError, match="precondition drift"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            preconditions=conditions,
            precondition_checker=PreconditionChecker(lambda resource: fp("b")),
        )
    assert len(service.orchestrator.shell_service.receipts.snapshot()) == 0
    assert not registry.used(seal.seal_id)


def test_seal_principal_mismatch_blocks_before_execution(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    with pytest.raises(ExecutionSealError, match="principal"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="bob"),
            seal=seal,
            seal_registry=registry,
        )
    assert len(service.orchestrator.shell_service.receipts.snapshot()) == 0


def test_seal_precondition_binding_cannot_be_added_later(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    conditions = Preconditions(
        (ResourcePrecondition("repo", fp("a")),)
    )
    with pytest.raises(ExecutionSealError, match="preconditions"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            preconditions=conditions,
            precondition_checker=PreconditionChecker(lambda resource: fp("a")),
        )


def test_seal_expiry_blocks_execution(tmp_path):
    now = [0.0]
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32, clock=lambda: now[0])
    registry = ExecutionSealRegistry(authority, clock=lambda: now[0])
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        ttl_seconds=1,
    )
    now[0] = 1
    with pytest.raises(ExecutionSealError, match="expired"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert len(service.orchestrator.shell_service.receipts.snapshot()) == 0


def test_sealed_approval_path_binds_approval_id(tmp_path):
    service = build_service(tmp_path, autonomy=AutonomyMode.PROPOSE)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    approval = service.orchestrator.approve(
        session,
        review,
        principal="alice",
        approved_by="operator",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        approval=approval,
    )
    assert seal.approval_id == approval.approval_id
    result, _, _ = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        approval=approval,
    )
    assert result.ok


def test_seal_review_requires_approval_when_policy_requires_it(tmp_path):
    service = build_service(tmp_path, autonomy=AutonomyMode.PROPOSE)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    with pytest.raises(RuntimeError, match="approval"):
        service.seal_review(
            session,
            review,
            principal="alice",
            authority=ExecutionSealAuthority(b"k" * 32),
        )


def test_seal_cannot_bind_foreign_approval(tmp_path):
    service = build_service(tmp_path, autonomy=AutonomyMode.PROPOSE)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    approval = service.orchestrator.approve(
        session,
        review,
        principal="alice",
        approved_by="operator",
    )
    with pytest.raises(Exception):
        service.seal_review(
            session,
            review,
            principal="bob",
            authority=ExecutionSealAuthority(b"k" * 32),
            approval=approval,
        )


def test_consumed_seal_replay_is_rejected(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    registry.consume(
        seal,
        principal="alice",
        session_id=session.session_id,
        plan_pin=service._pins[session.session_id],
    )
    with pytest.raises(SealReplay):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert len(service.orchestrator.shell_service.receipts.snapshot()) == 0


def test_policy_drift_invalidates_seal_before_issue_new_work(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    service.governance.policy_store.replace(
        AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            max_actions=31,
            min_confidence=0.5,
            max_uncertainty=0.5,
        )
    )
    with pytest.raises(RuntimeError, match="stale"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=ExecutionSealRegistry(authority),
        )


def test_missing_checker_for_bound_preconditions_is_error(tmp_path):
    service = build_service(tmp_path)
    session = service.new_session(intent(), session_id="s")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    conditions = Preconditions(
        (ResourcePrecondition("repo", fp("a")),)
    )
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        preconditions=conditions,
    )
    with pytest.raises(RuntimeError, match="precondition checker"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=ExecutionSealRegistry(authority),
            preconditions=conditions,
        )

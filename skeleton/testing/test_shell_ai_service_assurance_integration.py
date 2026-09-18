"""Service-level execution-assurance integration tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.assurance import AIExecutionAssuranceInspector
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.isolation_compiler import AIIsolationCompiler
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.resource_profile import AIResourceCompiler, AIResourceProfile
from skeleton.shells.ai.risk import RiskBand
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.sandbox_attestation import SandboxCapabilities
from skeleton.shells.ai.sandbox_backend import VerifiedSandboxExecutionBackend
from skeleton.shells.ai.sandbox_contract import AISandboxContractBuilder
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentConstraint
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.plan_executor import PlanExecutionReport, StepExecution, StepState
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def build_service(tmp_path, contract, *, auto_band):
    command_catalog = CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
                description="bounded python",
            ),
        )
    )
    tools = AIToolCatalog(command_catalog)
    effects = EffectRegistry((contract,))
    policy = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        min_confidence=0.5,
        max_uncertainty=0.5,
        auto_execute_bands=frozenset({RiskBand.LOW, auto_band}),
        approval_bands=frozenset(),
        require_reversible_for_autonomy=True,
    )

    def propose(request):
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "proposal",
                request.intent.intent_id,
                (
                    AIAction(
                        "action",
                        "python",
                        ("-c", "print('ASSURANCE_OK')"),
                        timeout_seconds=1,
                    ),
                ),
                confidence=0.95,
                uncertainty=0.05,
                model_id="model",
            ),
        )

    model = CallableAIModelPort("model", propose)
    planner = AIPlanner(
        model,
        tools,
        AIToolRouter(tools, effects),
        policy_fingerprint=policy.fingerprint,
    )
    shell = ShellService(
        ShellExecutor(
            ShellRunner(
                ShellPolicy(
                    executables={"python": sys.executable},
                    cwd_roots=(tmp_path,),
                    default_timeout=2,
                    max_timeout=4,
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
    orchestrator = AIShellOrchestrator(
        planner=planner,
        critic=AIPlanCritic(effects, policy),
        compiler=AIPlanCompiler(effects),
        shell_service=shell,
    )
    service = AIShellService(
        orchestrator,
        AIShellDiagnostics(tools, effects, policy, model),
        AIShellGovernance(AIPolicyStore(policy)),
        assurance=AIExecutionAssuranceInspector(),
    )
    service.start()
    return service, effects


def medium_contract():
    return EffectContract(
        "python",
        frozenset(
            {
                EffectKind.WRITE_FILESYSTEM,
                EffectKind.NETWORK,
            }
        ),
        idempotent=True,
        reversible=True,
    )


def high_contract():
    return EffectContract(
        "python",
        frozenset(
            {
                EffectKind.WRITE_FILESYSTEM,
                EffectKind.DELETE_FILESYSTEM,
                EffectKind.NETWORK,
            }
        ),
        idempotent=False,
        reversible=True,
    )


def intent():
    return AIIntent(
        "intent",
        "execute assurance test",
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            max_steps=2,
            max_timeout_seconds=2,
            allow_network=True,
            allow_writes=True,
            allow_destructive=True,
        ),
    )


def test_medium_risk_normal_execution_is_blocked_before_child(tmp_path):
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
    )
    session = service.new_session(intent(), session_id="medium")
    review, _ = service.review(session)
    assert review.critique.risk.band is RiskBand.MEDIUM
    with pytest.raises(RuntimeError, match="sealed execution"):
        service.execute(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
        )
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_medium_risk_sealed_execution_succeeds_on_host_backend(tmp_path):
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
    )
    session = service.new_session(intent(), session_id="medium")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    result, _, use = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
    )
    assert result.ok
    assert use.seal_id == seal.seal_id
    assert registry.used(seal.seal_id)
    assert result.provenance.execution_backend_id == "shell-service-host"


class FakeSandbox:
    def __init__(self):
        self.calls = []
        self._capabilities = SandboxCapabilities(
            backend_id="fake",
            backend_version="1",
            max_level="sandboxed",
            private_tmp=True,
            clean_environment=True,
            readonly_source=True,
            network_namespace=True,
            home_hiding=True,
            process_group=True,
            no_new_privileges=True,
            syscall_filter=True,
            resource_limits=True,
            max_profile=AIResourceProfile(
                wall_seconds=120,
                cpu_seconds=60,
                memory_bytes=1024 * 1024 * 1024,
                process_count=64,
                file_bytes=1024 * 1024 * 1024,
                open_files=1024,
                output_bytes=16 * 1024 * 1024,
            ),
        )

    @property
    def backend_id(self):
        return "fake"

    @property
    def capabilities(self):
        return self._capabilities

    def execute_plan(self, plan, *, context, contract):
        self.calls.append((plan, context, contract))
        return PlanExecutionReport(
            plan.plan_id,
            plan.fingerprint,
            (
                StepExecution(
                    plan.steps[0].step_id,
                    StepState.SUCCEEDED,
                    None,
                    "",
                    1.0,
                    2.0,
                ),
            ),
            1.0,
            2.0,
        )

    def receipt_root(self):
        return "a" * 64


def verified_backend(review, intent_value, effects):
    isolation = AIIsolationCompiler(effects).compile(
        intent_value,
        review.planning.response.proposal,
        review.critique.risk,
    )
    resources = AIResourceCompiler().compile(
        intent_value,
        review.planning.response.proposal,
        review.critique.risk,
    )
    contract = AISandboxContractBuilder().build(isolation, resources)
    fake = FakeSandbox()
    backend = VerifiedSandboxExecutionBackend(
        fake,
        contract,
        plan_fingerprint=review.compiled.plan.fingerprint,
    )
    return backend, fake


def test_high_risk_sealed_host_execution_is_blocked_without_consuming_seal(tmp_path):
    service, _ = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
    )
    session = service.new_session(intent(), session_id="high")
    review, _ = service.review(session)
    assert review.critique.risk.band is RiskBand.HIGH
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    with pytest.raises(RuntimeError, match="verified sandbox"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_high_risk_sealed_verified_sandbox_execution_succeeds(tmp_path):
    service, effects = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
    )
    intent_value = intent()
    session = service.new_session(intent_value, session_id="high")
    review, _ = service.review(session)
    backend, fake = verified_backend(review, intent_value, effects)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    result, _, _ = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        execution_backend=backend,
    )
    assert result.ok
    assert len(fake.calls) == 1
    assert result.provenance.execution_backend_id == "sandbox:fake"
    assert len(result.provenance.sandbox_binding_digest) == 64
    assert registry.used(seal.seal_id)


def test_high_risk_backend_name_spoof_does_not_satisfy_service_assurance(tmp_path):
    service, _ = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
    )
    session = service.new_session(intent(), session_id="high")
    review, _ = service.review(session)

    class SpoofBackend:
        backend_id = "sandbox:spoof"

        def execute_plan(self, plan, *, context):
            raise AssertionError("spoof backend must not execute")

        def receipt_root(self):
            return "b" * 64

    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    with pytest.raises(RuntimeError, match="verified sandbox"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_backend=SpoofBackend(),
        )
    assert not registry.used(seal.seal_id)


def test_critical_assurance_policy_denies_even_sealed_verified_backend():
    inspector = AIExecutionAssuranceInspector()
    with pytest.raises(RuntimeError, match="denied"):
        inspector.require(
            RiskBand.CRITICAL,
            sealed=True,
            sandbox_verified=True,
            backend_id="sandbox:fake",
        )

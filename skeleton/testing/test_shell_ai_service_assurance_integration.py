"""Service-level execution-assurance integration tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.approval import AIApprovalError
from skeleton.shells.ai.assurance import AIExecutionAssuranceInspector, AIExecutionAssurancePolicy, AssuranceLevel
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptRecovery,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority, ExecutionSealError
from skeleton.shells.ai.execution_fence import (
    AIExecutionFenceError,
    AIExecutionFenceManager,
    AIExecutionFencePolicy,
)
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


def build_service(
    tmp_path,
    contract,
    *,
    auto_band,
    runtime_trust=None,
    authority_health=None,
    execution_fences=None,
    execution_attempts=None,
    worker_id="",
):
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
        runtime_trust=runtime_trust,
        authority_health=authority_health,
        execution_fences=execution_fences,
        execution_attempts=execution_attempts,
        worker_id=worker_id,
    )
    service.start()
    return service, effects




class _ToggleReport:
    def __init__(self, kind):
        self.kind = kind

    @property
    def epoch_digest(self):
        return "t" * 64

    @property
    def policy_digest(self):
        return "h" * 64

    def to_dict(self):
        return {
            "ok": True,
            "kind": self.kind,
            "epoch_digest": self.epoch_digest,
            "policy_digest": self.policy_digest,
        }


class _ToggleRuntimeTrust:
    def __init__(self, *, allowed=True):
        self.allowed = allowed
        self.pin_calls = 0
        self.require_calls = 0

    def pin(self):
        self.pin_calls += 1
        if not self.allowed:
            raise RuntimeError("runtime trust unavailable")
        return _ToggleReport("runtime-trust")

    def require_current(self):
        self.require_calls += 1
        if not self.allowed:
            raise RuntimeError("runtime trust drift")
        return _ToggleReport("runtime-trust")


class _ToggleAuthorityHealth:
    def __init__(self, *, allowed=True):
        self.allowed = allowed
        self.require_calls = 0

    def require(self):
        self.require_calls += 1
        if not self.allowed:
            raise RuntimeError("authority health failed")
        return _ToggleReport("authority-health")


def low_contract():
    return EffectContract(
        "python",
        frozenset({EffectKind.READ_FILESYSTEM}),
        idempotent=True,
        reversible=True,
    )

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
        execution_backend=backend,
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


def test_high_risk_seal_binds_exact_verified_sandbox_backend(tmp_path):
    service, effects = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
    )
    intent_value = intent()
    session = service.new_session(intent_value, session_id="high-binding")
    review, _ = service.review(session)
    first_backend, first_fake = verified_backend(review, intent_value, effects)
    second_backend, second_fake = verified_backend(review, intent_value, effects)
    # Distinguish the second backend capability identity without making it
    # incompatible with the contract.
    second_fake._capabilities = SandboxCapabilities(
        backend_id="fake-two",
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
        max_profile=second_fake._capabilities.max_profile,
    )
    second_backend = VerifiedSandboxExecutionBackend(
        second_fake,
        second_backend.contract,
        plan_fingerprint=review.compiled.plan.fingerprint,
    )

    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_backend=first_backend,
    )
    with pytest.raises(ExecutionSealError, match="assurance"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_backend=second_backend,
        )
    assert not registry.used(seal.seal_id)
    assert first_fake.calls == []
    assert second_fake.calls == []


def test_assurance_policy_change_after_sealing_invalidates_seal(tmp_path):
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
    )
    session = service.new_session(intent(), session_id="policy-binding")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    # Change a policy field that does not alter the medium band's immediate
    # requirement. Execution would still be sealed/allowed, but the assurance
    # policy identity changed and therefore the old seal must be rejected.
    service.assurance = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy(
            low=AssuranceLevel.SEALED,
            medium=AssuranceLevel.SEALED,
            high=AssuranceLevel.SANDBOXED,
            critical=AssuranceLevel.DENIED,
        )
    )
    with pytest.raises(ExecutionSealError, match="assurance"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_assurance_only_approval_not_burned_by_unsealed_denial(tmp_path):
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
    )
    service.assurance = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy(
            require_human_approval_bands=frozenset({RiskBand.MEDIUM})
        )
    )
    session = service.new_session(intent(), session_id="approval-ordering")
    review, _ = service.review(session)
    proposal = review.planning.response.proposal
    approval = service.orchestrator.approvals.approve(
        principal="alice",
        intent_fingerprint=session.intent.fingerprint,
        proposal_fingerprint=proposal.fingerprint,
        approved_by="operator",
    )

    with pytest.raises(RuntimeError, match="sealed execution"):
        service.execute(
            session,
            review,
            context=ExecutionContext("c1", principal="alice"),
            approval=approval,
        )

    # The denied pre-dispatch attempt must not burn one-use authority.
    service.orchestrator.approvals.require(
        approval,
        principal="alice",
        intent_fingerprint=session.intent.fingerprint,
        proposal_fingerprint=proposal.fingerprint,
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
    result, _, _ = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("c2", principal="alice"),
        seal=seal,
        seal_registry=registry,
        approval=approval,
    )
    assert result.ok

    with pytest.raises(AIApprovalError):
        service.orchestrator.approvals.require(
            approval,
            principal="alice",
            intent_fingerprint=session.intent.fingerprint,
            proposal_fingerprint=proposal.fingerprint,
        )



def test_runtime_trust_failure_at_start_is_fail_closed(tmp_path):
    trust = _ToggleRuntimeTrust(allowed=False)
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        runtime_trust=trust,
    )
    assert service.state.phase.value == "failed"
    assert trust.pin_calls == 1
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_authority_health_failure_at_start_is_fail_closed(tmp_path):
    health = _ToggleAuthorityHealth(allowed=False)
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        authority_health=health,
    )
    assert service.state.phase.value == "failed"
    assert health.require_calls == 1
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_runtime_trust_drift_degrades_service_before_new_session(tmp_path):
    trust = _ToggleRuntimeTrust()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        runtime_trust=trust,
    )
    assert service.state.phase.value == "ready"
    trust.allowed = False
    with pytest.raises(RuntimeError, match="runtime trust"):
        service.new_session(intent(), session_id="trust-drift")
    assert service.state.phase.value == "degraded"
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_authority_health_failure_blocks_unsealed_low_risk_child(tmp_path):
    health = _ToggleAuthorityHealth()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        authority_health=health,
    )
    session = service.new_session(intent(), session_id="health-low")
    review, _ = service.review(session)
    assert review.critique.risk.band is RiskBand.LOW
    health.allowed = False
    with pytest.raises(RuntimeError, match="authority dependency health"):
        service.execute(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
        )
    assert service.state.phase.value == "degraded"
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_authority_health_failure_blocks_seal_issuance(tmp_path):
    health = _ToggleAuthorityHealth()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        authority_health=health,
    )
    session = service.new_session(intent(), session_id="health-seal")
    review, _ = service.review(session)
    health.allowed = False
    with pytest.raises(RuntimeError, match="authority dependency health"):
        service.seal_review(
            session,
            review,
            principal="alice",
            authority=ExecutionSealAuthority(b"k" * 32),
        )
    assert service.state.phase.value == "degraded"
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_authority_health_failure_does_not_consume_existing_seal(tmp_path):
    health = _ToggleAuthorityHealth()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        authority_health=health,
    )
    session = service.new_session(intent(), session_id="health-consume")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    health.allowed = False
    with pytest.raises(RuntimeError, match="authority dependency health"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_runtime_trust_drift_does_not_consume_existing_seal(tmp_path):
    trust = _ToggleRuntimeTrust()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        runtime_trust=trust,
    )
    session = service.new_session(intent(), session_id="trust-consume")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    trust.allowed = False
    with pytest.raises(RuntimeError, match="runtime trust"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_service_status_reports_runtime_trust_and_authority_health(tmp_path):
    trust = _ToggleRuntimeTrust()
    health = _ToggleAuthorityHealth()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        runtime_trust=trust,
        authority_health=health,
    )
    data = service.status().to_dict()
    assert data["runtime_trust"] == {
        "ok": True,
        "kind": "runtime-trust",
        "epoch_digest": "t" * 64,
        "policy_digest": "h" * 64,
    }
    assert data["authority_health"] == {
        "ok": True,
        "kind": "authority-health",
        "epoch_digest": "t" * 64,
        "policy_digest": "h" * 64,
    }


def test_authority_health_is_rechecked_at_execution_boundary(tmp_path):
    health = _ToggleAuthorityHealth()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        authority_health=health,
    )
    startup_calls = health.require_calls
    session = service.new_session(intent(), session_id="health-recheck")
    review, _ = service.review(session)
    service.execute(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
    )
    assert health.require_calls > startup_calls
    assert service.orchestrator.shell_service.receipts.snapshot()


def test_runtime_trust_is_rechecked_across_session_review_and_execution(tmp_path):
    trust = _ToggleRuntimeTrust()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        runtime_trust=trust,
    )
    session = service.new_session(intent(), session_id="trust-recheck")
    after_session = trust.require_calls
    review, _ = service.review(session)
    after_review = trust.require_calls
    service.execute(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
    )
    assert after_session >= 1
    assert after_review > after_session
    assert trust.require_calls > after_review


def _fence_manager(
    *,
    backend=None,
    default_timeout=2.0,
    maximum_ttl=30.0,
):
    return AIExecutionFenceManager(
        backend or InMemoryFencedStore(),
        policy=AIExecutionFencePolicy(
            default_step_timeout_seconds=default_timeout,
            per_step_overhead_seconds=0.1,
            safety_margin_seconds=0.5,
            minimum_ttl_seconds=1.0,
            maximum_ttl_seconds=maximum_ttl,
            max_plan_steps=16,
        ),
    )


def test_execution_fencing_requires_assurance_inspector(tmp_path):
    base, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
    )
    with pytest.raises(ValueError, match="assurance"):
        AIShellService(
            base.orchestrator,
            base.diagnostics,
            base.governance,
            execution_fences=_fence_manager(),
            worker_id="worker-1",
        )


def test_execution_fencing_requires_worker_identity(tmp_path):
    base, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
    )
    with pytest.raises(ValueError, match="worker_id"):
        AIShellService(
            base.orchestrator,
            base.diagnostics,
            base.governance,
            assurance=AIExecutionAssuranceInspector(),
            execution_fences=_fence_manager(),
        )


def test_fenced_medium_risk_real_child_execution_succeeds(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-success")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    result, _, use = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("fenced", principal="alice"),
        seal=seal,
        seal_registry=registry,
        execution_fence=fence,
    )
    assert result.ok
    assert use.seal_id == seal.seal_id
    assert registry.used(seal.seal_id)
    assert fences.backend.leases() == ()
    receipts = service.orchestrator.shell_service.receipts.snapshot()
    assert len(receipts) == 1


def test_configured_fencing_blocks_direct_execute(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-direct")
    review, _ = service.review(session)
    with pytest.raises(RuntimeError, match="requires execute_sealed"):
        service.execute(
            session,
            review,
            context=ExecutionContext("direct", principal="alice"),
        )
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_configured_fencing_blocks_seal_without_fence(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-seal")
    review, _ = service.review(session)
    with pytest.raises(RuntimeError, match="execution fence"):
        service.seal_review(
            session,
            review,
            principal="alice",
            authority=ExecutionSealAuthority(b"k" * 32),
        )
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_configured_fencing_blocks_execute_without_fence_before_seal_consumption(
    tmp_path,
):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-missing")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    with pytest.raises(RuntimeError, match="execution fence"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("missing", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()
    # The valid fence remains owned because it was never passed into an
    # execution attempt and therefore must not be silently released.
    assert len(fences.backend.leases()) == 1
    assert fences.release(fence)


def test_fence_principal_substitution_rejected_before_seal_consumption(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-principal")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    with pytest.raises(AIExecutionFenceError, match="binding"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("wrong", principal="bob"),
            seal=seal,
            seal_registry=registry,
            execution_fence=fence,
        )
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()
    assert fences.release(fence)


def test_fence_reacquire_invalidates_sealed_old_fence(tmp_path):
    backend = InMemoryFencedStore()
    fences = _fence_manager(backend=backend)
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-stale")
    review, _ = service.review(session)
    first = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=first,
    )
    assert fences.release(first)
    second = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    with pytest.raises(AIExecutionFenceError, match="stale"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("stale", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_fence=first,
        )
    assert not registry.used(seal.seal_id)
    assert fences.release(second)


def test_fence_substitution_after_sealing_invalidates_assurance_digest(tmp_path):
    backend = InMemoryFencedStore()
    fences = _fence_manager(backend=backend)
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-substitute")
    review, _ = service.review(session)
    first = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=first,
    )
    assert fences.release(first)
    second = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    with pytest.raises(ExecutionSealError, match="assurance"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("substitute", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_fence=second,
        )
    assert not registry.used(seal.seal_id)
    # execute_sealed owns a supplied fence for the duration of its attempt and
    # releases it even when seal verification rejects the substituted fence.
    assert fences.backend.leases() == ()


def test_authority_health_failure_blocks_fenced_execute_before_seal_consumption(
    tmp_path,
):
    health = _ToggleAuthorityHealth()
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        authority_health=health,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-health")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    health.allowed = False
    with pytest.raises(RuntimeError, match="authority dependency health"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("health", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_fence=fence,
        )
    assert not registry.used(seal.seal_id)
    # Health failure occurs before the execution-attempt ownership block, so
    # the caller still owns and can explicitly release its valid fence.
    assert len(fences.backend.leases()) == 1
    assert fences.release(fence)


def test_runtime_trust_drift_blocks_fenced_execute_before_seal_consumption(
    tmp_path,
):
    trust = _ToggleRuntimeTrust()
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        runtime_trust=trust,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-trust")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    trust.allowed = False
    with pytest.raises(RuntimeError, match="runtime trust"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("trust", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_fence=fence,
        )
    assert not registry.used(seal.seal_id)
    assert len(fences.backend.leases()) == 1
    assert fences.release(fence)


def test_fenced_plan_failure_releases_execution_fence(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-failure")
    review, _ = service.review(session)

    class FailingBackend:
        backend_id = "failing"

        def execute_plan(self, plan, *, context):
            raise RuntimeError("synthetic backend failure")

        def receipt_root(self):
            return "a" * 64

    backend = FailingBackend()
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_backend=backend,
        execution_fence=fence,
    )
    with pytest.raises(RuntimeError, match="synthetic backend"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("fail", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_backend=backend,
            execution_fence=fence,
        )
    assert registry.used(seal.seal_id)
    assert fences.backend.leases() == ()


def test_execution_fence_is_bound_into_assurance_seal(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="fenced-assurance")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    first = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    assert first.assurance_digest
    assert len(first.assurance_digest) == 64
    assert fences.release(fence)


def _attempt_store(backend=None, *, max_retries=8):
    return AIExecutionAttemptStore(
        backend or InMemoryFencedStore(),
        max_retries=max_retries,
    )


def test_execution_attempt_ledger_requires_worker_identity(tmp_path):
    attempts = _attempt_store()
    base, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
    )
    with pytest.raises(ValueError, match="worker_id"):
        AIShellService(
            base.orchestrator,
            base.diagnostics,
            base.governance,
            assurance=AIExecutionAssuranceInspector(),
            execution_attempts=attempts,
        )


def test_configured_attempt_ledger_blocks_direct_execute(tmp_path):
    attempts = _attempt_store()
    service, _ = build_service(
        tmp_path,
        low_contract(),
        auto_band=RiskBand.LOW,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-direct")
    review, _ = service.review(session)
    with pytest.raises(RuntimeError, match="attempt ledger requires execute_sealed"):
        service.execute(
            session,
            review,
            context=ExecutionContext("direct", principal="alice"),
        )
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_attempt_ledger_records_successful_real_child(tmp_path):
    attempts = _attempt_store()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-success")
    review, _ = service.review(session)
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
        context=ExecutionContext("attempt", principal="alice"),
        seal=seal,
        seal_registry=registry,
    )
    assert result.ok
    stored = attempts.current(seal.seal_id)
    assert stored is not None
    assert stored.attempt.state is ExecutionAttemptState.SUCCEEDED
    assert stored.attempt.terminal_evidence_digest == result.provenance.digest
    assert (
        stored.attempt.recovery
        is ExecutionAttemptRecovery.TERMINAL_SUCCESS
    )
    assert stored.attempt.execution_backend_id == "shell-service-host"
    assert registry.used(seal.seal_id)
    assert len(service.orchestrator.shell_service.receipts.snapshot()) == 1


def test_attempt_ledger_binds_runtime_trust_and_release_identity(tmp_path):
    trust = _ToggleRuntimeTrust()
    attempts = _attempt_store()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        runtime_trust=trust,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-trust")
    review, _ = service.review(session)
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
        context=ExecutionContext("attempt", principal="alice"),
        seal=seal,
        seal_registry=registry,
    )
    stored = attempts.current(seal.seal_id)
    assert stored.attempt.runtime_trust_digest == "t" * 64
    assert stored.attempt.release_evidence_digest == ""
    assert result.provenance.runtime_trust_digest == "t" * 64


def test_attempt_ledger_binds_execution_fence_token(tmp_path):
    backend = InMemoryFencedStore()
    fences = _fence_manager(backend=backend)
    attempts = _attempt_store(backend)
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_fences=fences,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-fence")
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )
    result, _, _ = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("attempt", principal="alice"),
        seal=seal,
        seal_registry=registry,
        execution_fence=fence,
    )
    assert result.ok
    stored = attempts.current(seal.seal_id)
    assert stored.attempt.execution_fence_digest
    assert stored.attempt.fencing_token == fence.lease.fencing_token
    assert stored.attempt.state is ExecutionAttemptState.SUCCEEDED
    assert fences.backend.leases() == ()


def test_attempt_ledger_backend_crash_records_failed_terminal(tmp_path):
    attempts = _attempt_store()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-crash")
    review, _ = service.review(session)

    class CrashingBackend:
        backend_id = "crash-backend"

        def __init__(self):
            self.calls = 0

        def execute_plan(self, plan, *, context):
            self.calls += 1
            raise RuntimeError("synthetic child boundary crash")

        def receipt_root(self):
            return "c" * 64

    backend = CrashingBackend()
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_backend=backend,
    )
    with pytest.raises(RuntimeError, match="synthetic child boundary crash"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("attempt", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_backend=backend,
        )
    assert backend.calls == 1
    stored = attempts.current(seal.seal_id)
    assert stored.attempt.state is ExecutionAttemptState.FAILED
    assert stored.attempt.error_type == "RuntimeError"
    assert stored.attempt.terminal_evidence_digest == ""
    assert registry.used(seal.seal_id)


def test_invalid_seal_creates_no_execution_attempt(tmp_path):
    attempts = _attempt_store()
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-invalid-seal")
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    with pytest.raises(Exception):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("attempt", principal="bob"),
            seal=seal,
            seal_registry=registry,
        )
    assert attempts.current(seal.seal_id) is None
    assert not registry.used(seal.seal_id)
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


def test_assurance_denial_creates_no_execution_attempt(tmp_path):
    attempts = _attempt_store()
    service, _ = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-assurance")
    review, _ = service.review(session)
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
            context=ExecutionContext("attempt", principal="alice"),
            seal=seal,
            seal_registry=registry,
        )
    assert attempts.current(seal.seal_id) is None
    assert not registry.used(seal.seal_id)


def test_attempt_ledger_preserves_verified_sandbox_provenance(tmp_path):
    attempts = _attempt_store()
    service, effects = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    intent_value = intent()
    session = service.new_session(
        intent_value,
        session_id="attempt-sandbox",
    )
    review, _ = service.review(session)
    backend, fake = verified_backend(review, intent_value, effects)
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_backend=backend,
    )
    result, _, _ = service.execute_sealed(
        session,
        review,
        context=ExecutionContext("attempt", principal="alice"),
        seal=seal,
        seal_registry=registry,
        execution_backend=backend,
    )
    assert result.ok
    assert len(fake.calls) == 1
    assert result.provenance.execution_backend_id == "sandbox:fake"
    assert result.provenance.sandbox_binding_digest == backend.binding.digest
    stored = attempts.current(seal.seal_id)
    assert stored.attempt.state is ExecutionAttemptState.SUCCEEDED
    assert stored.attempt.execution_backend_id == "sandbox:fake"


class _ReserveOutageBackend:
    def get(self, namespace, key):
        return None

    def put_if_absent(self, namespace, key, value):
        raise OSError("attempt store unavailable")

    def compare_and_swap(self, namespace, key, *, expected_revision, value):
        raise OSError("attempt store unavailable")

    def delete(self, namespace, key, *, expected_revision):
        raise OSError("attempt store unavailable")


def test_attempt_store_outage_after_seal_consumption_never_spawns_child(tmp_path):
    attempts = _attempt_store(_ReserveOutageBackend())
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-outage")
    review, _ = service.review(session)

    class NeverBackend:
        backend_id = "never"

        def __init__(self):
            self.calls = 0

        def execute_plan(self, plan, *, context):
            self.calls += 1
            raise AssertionError("child must not spawn")

        def receipt_root(self):
            return "n" * 64

    backend = NeverBackend()
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_backend=backend,
    )
    with pytest.raises(OSError, match="unavailable"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("attempt", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_backend=backend,
        )
    assert registry.used(seal.seal_id)
    assert backend.calls == 0
    assert service.orchestrator.shell_service.receipts.snapshot() == ()


class _BoundaryConflictBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(namespace, key, value)

    def compare_and_swap(self, namespace, key, *, expected_revision, value):
        raise DistributedStateConflict("boundary CAS unavailable")

    def delete(self, namespace, key, *, expected_revision):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_boundary_ledger_failure_blocks_delegate_before_child(tmp_path):
    attempts = _attempt_store(
        _BoundaryConflictBackend(),
        max_retries=1,
    )
    service, _ = build_service(
        tmp_path,
        medium_contract(),
        auto_band=RiskBand.MEDIUM,
        execution_attempts=attempts,
        worker_id="worker-1",
    )
    session = service.new_session(intent(), session_id="attempt-boundary-cas")
    review, _ = service.review(session)

    class NeverBackend:
        backend_id = "never-boundary"

        def __init__(self):
            self.calls = 0

        def execute_plan(self, plan, *, context):
            self.calls += 1
            raise AssertionError("child must not spawn")

        def receipt_root(self):
            return "n" * 64

    backend = NeverBackend()
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_backend=backend,
    )
    with pytest.raises(RuntimeError, match="ledger terminal write failed"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext("attempt", principal="alice"),
            seal=seal,
            seal_registry=registry,
            execution_backend=backend,
        )
    assert backend.calls == 0
    assert registry.used(seal.seal_id)
    current = attempts.current(seal.seal_id)
    assert current is not None
    assert current.attempt.state is ExecutionAttemptState.AUTHORIZED


def test_assurance_rejection_releases_submitted_execution_fence(tmp_path):
    fences = _fence_manager()
    service, _ = build_service(
        tmp_path,
        high_contract(),
        auto_band=RiskBand.HIGH,
        execution_fences=fences,
        worker_id="worker-1",
    )
    session = service.new_session(
        intent(),
        session_id="fenced-assurance-reject",
    )
    review, _ = service.review(session)
    fence = service.acquire_execution_fence(
        session,
        review,
        principal="alice",
    )
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
        execution_fence=fence,
    )

    with pytest.raises(RuntimeError, match="sandbox"):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext(
                "assurance-reject",
                principal="alice",
            ),
            seal=seal,
            seal_registry=registry,
            execution_fence=fence,
        )

    assert not registry.used(seal.seal_id)
    assert fences.backend.leases() == ()
    assert service.orchestrator.shell_service.receipts.snapshot() == ()

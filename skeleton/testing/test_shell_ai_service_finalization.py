"""End-to-end sealed execution plus automatic evidence finalization tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore
from skeleton.shells.ai.audit_witness import AIAuditWitnessStore
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptState,
    StoredExecutionAttempt,
)
from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceStore
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalizationStore,
    FinalizationPhase,
)
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.lifecycle import AIServicePhase
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.recovery_store import AIRecoveryCheckpointStore
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.session_evidence import SessionEvidenceStore
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.types import (
    AIAction,
    AIIntent,
    AIPlanProposal,
    IntentConstraint,
)
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(char: str) -> str:
    return char * 64


def intent() -> AIIntent:
    return AIIntent(
        "intent",
        "run one evidence-finalized command",
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            max_steps=1,
            max_timeout_seconds=2,
            require_reversible=True,
        ),
    )


def effects() -> EffectRegistry:
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


def command_catalog() -> CommandCatalog:
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
                description="python",
            ),
        )
    )


def model(script: str = "print('FINALIZED_OK')"):
    def propose(request):
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                "proposal",
                request.intent.intent_id,
                (
                    AIAction(
                        "step",
                        "python",
                        ("-c", script),
                        timeout_seconds=1,
                    ),
                ),
                confidence=0.95,
                uncertainty=0.05,
                model_id="model",
            ),
        )

    return CallableAIModelPort("model", propose)


class EvidenceEnvironment:
    def __init__(
        self,
        tmp_path,
        *,
        script="print('FINALIZED_OK')",
        attempt_store_class=AIExecutionAttemptStore,
        anchor_class=AIAuditAnchorStore,
    ):
        self.backend = InMemoryFencedStore()
        self.attempts = attempt_store_class(
            self.backend,
            namespace="attempts",
        )
        policy = AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            min_confidence=0.5,
            max_uncertainty=0.5,
        )
        commands = command_catalog()
        tool_catalog = AIToolCatalog(commands)
        registry = effects()
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
        model_port = model(script)
        planner = AIPlanner(
            model_port,
            tool_catalog,
            AIToolRouter(tool_catalog, registry),
            policy_fingerprint=policy.fingerprint,
        )
        self.orchestrator = AIShellOrchestrator(
            planner=planner,
            critic=AIPlanCritic(registry, policy),
            compiler=AIPlanCompiler(registry),
            shell_service=shell,
        )
        self.service = AIShellService(
            self.orchestrator,
            AIShellDiagnostics(
                tool_catalog,
                registry,
                policy,
                model_port,
            ),
            AIShellGovernance(AIPolicyStore(policy)),
            execution_attempts=self.attempts,
            worker_id="worker-1",
        )
        self.service.start()
        self.session_evidence = SessionEvidenceStore(
            self.backend,
            namespace="session-evidence",
        )
        self.anchors = anchor_class(
            self.backend,
            ArtifactSigner(
                "audit",
                b"a" * 32,
                clock=lambda: 10.0,
            ),
            namespace="anchors",
            clock=lambda: 10.0,
        )
        self.witnesses = AIAuditWitnessStore(
            self.backend,
            ArtifactSigner(
                "witness",
                b"w" * 32,
                clock=lambda: 10.0,
            ),
            namespace="witnesses",
            clock=lambda: 10.0,
        )
        self.execution_evidence = AIExecutionEvidenceStore(
            self.backend,
            ArtifactSigner(
                "execution",
                b"e" * 32,
                clock=lambda: 10.0,
            ),
            namespace="execution-evidence",
        )
        self.finalizations = AIExecutionFinalizationStore(
            self.backend,
            namespace="finalizations",
            clock=lambda: 10.0,
        )
        self.recovery_checkpoints = AIRecoveryCheckpointStore(
            self.backend,
            namespace="recovery-checkpoints",
            clock=lambda: 10.0,
        )
        self.finalizer = AIExecutionEvidenceFinalizer(
            journal=self.orchestrator.journal,
            receipt_chain=self.orchestrator.shell_service.receipts,
            session_evidence=self.session_evidence,
            audit_anchors=self.anchors,
            audit_witnesses=self.witnesses,
            execution_evidence=self.execution_evidence,
            finalizations=self.finalizations,
            recovery_checkpoints=self.recovery_checkpoints,
        )

    def reviewed(self, session_id="session"):
        session = self.service.new_session(
            intent(),
            session_id=session_id,
        )
        review, _ = self.service.review(session)
        authority = ExecutionSealAuthority(b"k" * 32)
        registry = ExecutionSealRegistry(authority)
        seal = self.service.seal_review(
            session,
            review,
            principal="alice",
            authority=authority,
        )
        return session, review, authority, registry, seal


def test_execute_sealed_and_finalize_happy_path(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()

    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )

    assert result.execution.ok
    assert result.ok
    assert result.execution_attempt is not None
    assert result.execution_attempt.state is ExecutionAttemptState.SUCCEEDED
    assert result.finalized.finalization is not None
    assert (
        result.finalized.finalization.phase
        is FinalizationPhase.COMPLETE
    )
    assert registry.used(seal.seal_id)
    assert env.service.state.phase is AIServicePhase.READY
    assert len(env.anchors.snapshot()) == 1
    assert env.witnesses.current_head()[1].sequence == 1
    assert len(env.execution_evidence.snapshot()) == 1
    assert (
        result.execution.report.steps[0]
        .dispatch.outcome.result.stdout.strip()
        == b"FINALIZED_OK"
    )


def test_finalized_result_binds_one_attempt_across_all_layers(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )

    attempt = result.execution_attempt
    finalized = result.finalized
    assert finalized.recovery_checkpoint.execution_attempt_id == attempt.attempt_id
    assert (
        finalized.recovery_checkpoint.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert finalized.audit_anchor.anchor.execution_attempt_id == attempt.attempt_id
    assert (
        finalized.audit_anchor.anchor.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert finalized.execution_evidence is not None
    assert (
        finalized.execution_evidence.evidence.execution_attempt_id
        == attempt.attempt_id
    )
    assert (
        finalized.execution_evidence.evidence.execution_attempt_authority_digest
        == attempt.authority_digest
    )
    assert (
        finalized.execution_evidence.evidence.execution_attempt_state
        == "succeeded"
    )
    assert finalized.finalization.execution_attempt_id == attempt.attempt_id
    assert (
        finalized.finalization.execution_attempt_authority_digest
        == attempt.authority_digest
    )


def test_finalized_result_binds_execution_seal(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    evidence = result.finalized.execution_evidence.evidence
    assert evidence.execution_seal_id == seal.seal_id
    assert result.execution_attempt.execution_seal_id == seal.seal_id
    assert result.seal_use.seal_id == seal.seal_id


def test_finalized_result_serializes_complete_bundle(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    data = result.to_dict()
    assert data["ok"] is True
    assert data["seal_use"]["seal_id"] == seal.seal_id
    assert data["execution_attempt"]["state"] == "succeeded"
    assert data["finalized"]["finalization"]["phase"] == "complete"
    assert data["finalized"]["audit_witness"] is not None
    assert data["finalized"]["execution_evidence"] is not None


def test_child_failure_is_still_finalized_as_failed_terminal(tmp_path):
    env = EvidenceEnvironment(
        tmp_path,
        script="import sys; sys.exit(3)",
    )
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )

    assert not result.execution.ok
    assert not result.ok
    assert result.execution_attempt.state is ExecutionAttemptState.FAILED
    assert result.execution_attempt.terminal_evidence_digest
    assert result.finalized.finalization.phase is FinalizationPhase.COMPLETE
    assert (
        result.finalized.execution_evidence.evidence.execution_attempt_state
        == "failed"
    )
    assert env.service.state.phase is AIServicePhase.READY


class BrokenAnchorStore(AIAuditAnchorStore):
    def verify(self) -> bool:
        if self._chain.length() > 0:
            return False
        return super().verify()


def test_finalization_failure_after_child_degrades_service(tmp_path):
    env = EvidenceEnvironment(
        tmp_path,
        anchor_class=BrokenAnchorStore,
    )
    session, review, _, registry, seal = env.reviewed()

    with pytest.raises(RuntimeError, match="audit anchor chain"):
        env.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            finalizer=env.finalizer,
        )

    assert registry.used(seal.seal_id)
    stored = env.attempts.current(seal.seal_id)
    assert stored is not None
    assert stored.attempt.state is ExecutionAttemptState.SUCCEEDED
    assert len(env.orchestrator.shell_service.receipts.snapshot()) == 1
    assert env.service.state.phase is AIServicePhase.DEGRADED
    with pytest.raises(RuntimeError, match="not ready"):
        env.service.new_session(intent(), session_id="blocked")


def test_finalization_failure_preserves_partial_progress_for_repair(tmp_path):
    env = EvidenceEnvironment(
        tmp_path,
        anchor_class=BrokenAnchorStore,
    )
    session, review, _, registry, seal = env.reviewed()

    with pytest.raises(RuntimeError):
        env.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            finalizer=env.finalizer,
        )

    anchors = env.anchors.snapshot()
    assert len(anchors) == 1
    finalization_id = anchors[0].anchor.finalization_id
    stored = env.finalizations.current(finalization_id)
    assert stored is not None
    assert stored.finalization.phase is FinalizationPhase.CHECKPOINTED
    assert stored.finalization.session_evidence_digest
    assert stored.finalization.recovery_checkpoint_digest


def test_wrong_finalizer_type_blocks_before_seal_consumption(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    with pytest.raises(TypeError, match="finalizer"):
        env.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            finalizer=object(),
        )
    assert not registry.used(seal.seal_id)
    assert env.attempts.current(seal.seal_id) is None
    assert env.orchestrator.shell_service.receipts.snapshot() == ()


class VanishingAttemptStore(AIExecutionAttemptStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hide_current = False

    def current(self, attempt_id):
        if self.hide_current:
            return None
        return super().current(attempt_id)

    def succeed(self, attempt, *, terminal_evidence_digest):
        result = super().succeed(
            attempt,
            terminal_evidence_digest=terminal_evidence_digest,
        )
        self.hide_current = True
        return result


def test_missing_terminal_attempt_after_execution_degrades_service(tmp_path):
    env = EvidenceEnvironment(
        tmp_path,
        attempt_store_class=VanishingAttemptStore,
    )
    session, review, _, registry, seal = env.reviewed()
    with pytest.raises(RuntimeError, match="attempt evidence is missing"):
        env.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            finalizer=env.finalizer,
        )
    assert registry.used(seal.seal_id)
    assert env.service.state.phase is AIServicePhase.DEGRADED
    assert len(env.orchestrator.shell_service.receipts.snapshot()) == 1


class NonTerminalAttemptStore(AIExecutionAttemptStore):
    def succeed(self, attempt, *, terminal_evidence_digest):
        # Deliberately preserve BOUNDARY_ENTERED to simulate a lost terminal
        # ledger write after the delegate returned.
        current = self.current(attempt.attempt_id)
        return StoredExecutionAttempt(current.revision, current.attempt)


def test_nonterminal_attempt_after_execution_degrades_service(tmp_path):
    env = EvidenceEnvironment(
        tmp_path,
        attempt_store_class=NonTerminalAttemptStore,
    )
    session, review, _, registry, seal = env.reviewed()
    with pytest.raises(RuntimeError, match="did not reach terminal"):
        env.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext("c", principal="alice"),
            seal=seal,
            seal_registry=registry,
            finalizer=env.finalizer,
        )
    assert registry.used(seal.seal_id)
    current = env.attempts.current(seal.seal_id)
    assert current.attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_finalized_service_path_keeps_signed_chains_verifiable(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert env.anchors.verify()
    assert env.witnesses.verify().ok
    assert env.execution_evidence.verify()


def test_second_independent_execution_advances_all_global_evidence_chains(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    first_session, first_review, _, first_registry, first_seal = env.reviewed(
        "session-1"
    )
    first = env.service.execute_sealed_and_finalize(
        first_session,
        first_review,
        context=ExecutionContext("one", principal="alice"),
        seal=first_seal,
        seal_registry=first_registry,
        finalizer=env.finalizer,
    )
    # The model uses fixed intent/proposal IDs. A second independent session is
    # still safe because finalization identity also includes provenance and the
    # unique execution attempt ID.
    second_session, second_review, _, second_registry, second_seal = env.reviewed(
        "session-2"
    )
    second = env.service.execute_sealed_and_finalize(
        second_session,
        second_review,
        context=ExecutionContext("two", principal="alice"),
        seal=second_seal,
        seal_registry=second_registry,
        finalizer=env.finalizer,
    )
    assert first.finalized.finalization.finalization_id != (
        second.finalized.finalization.finalization_id
    )
    assert len(env.anchors.snapshot()) == 2
    assert env.witnesses.current_head()[1].sequence == 2
    assert len(env.execution_evidence.snapshot()) == 2
    assert env.anchors.verify()
    assert env.witnesses.verify().ok
    assert env.execution_evidence.verify()


def test_model_attestation_digest_is_bound_when_supplied(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
        model_attestation_digest=fp("m"),
    )
    assert (
        result.finalized.execution_evidence.evidence.model_attestation_digest
        == fp("m")
    )


def test_service_remains_ready_after_successful_evidence_commit(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert env.service.state.ready()
    next_session = env.service.new_session(
        intent(),
        session_id="next",
    )
    assert next_session.session_id == "next"


def test_finalized_attempt_terminal_digest_matches_provenance(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert (
        result.execution_attempt.terminal_evidence_digest
        == result.execution.provenance.digest
    )


def test_finalization_checkpoint_binds_terminal_session_phase(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert result.finalized.checkpoint.phase == "complete"
    assert result.finalized.recovery_checkpoint.session.phase == "complete"


def test_failed_execution_checkpoint_binds_failed_session_phase(tmp_path):
    env = EvidenceEnvironment(
        tmp_path,
        script="import sys; sys.exit(2)",
    )
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert result.finalized.checkpoint.phase == "failed"
    assert result.finalized.recovery_checkpoint.session.phase == "failed"


def test_finalization_id_is_stable_for_returned_terminal_execution(tmp_path):
    env = EvidenceEnvironment(tmp_path)
    session, review, _, registry, seal = env.reviewed()
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext("c", principal="alice"),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    expected = result.finalized.finalization.derive_id(
        session_id=session.session_id,
        provenance_digest=result.execution.provenance.digest,
        execution_attempt_id=seal.seal_id,
    )
    assert result.finalized.finalization.finalization_id == expected

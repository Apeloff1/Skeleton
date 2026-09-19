"""Post-finalization durable readiness and no-unsafe-retry integration tests."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.ai.audit_anchor import AIAuditAnchorStore
from skeleton.shells.ai.audit_witness import AIAuditWitnessStore
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_operations import DurableEvidenceOperationsInspector
from skeleton.shells.ai.durable_readiness import (
    DurableEvidenceReadinessGuard,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexOperator,
)
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
)
from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperator,
)
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptState,
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
from skeleton.shells.ai.recovery_store import AIRecoveryCheckpointStore
from skeleton.shells.ai.router import AIToolRouter
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
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


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


def intent(
    *,
    intent_id="intent",
) -> AIIntent:
    return AIIntent(
        intent_id,
        "run one terminal command with durable readiness",
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            max_steps=1,
            max_timeout_seconds=2,
            require_reversible=True,
        ),
    )


def model(script: str):
    counter = {"value": 0}

    def propose(request):
        counter["value"] += 1
        suffix = counter["value"]
        return AIModelResponse(
            request.request_id,
            AIPlanProposal(
                f"proposal-{suffix}",
                request.intent.intent_id,
                (
                    AIAction(
                        f"step-{suffix}",
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


class ToggleFailureReadinessGuard(DurableEvidenceReadinessGuard):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_reconcile = False
        self.reconcile_calls = 0

    def reconcile(self, *args, **kwargs):
        self.reconcile_calls += 1
        if self.fail_reconcile:
            raise RuntimeError(
                "synthetic post-finalization maintenance failure"
            )
        return super().reconcile(*args, **kwargs)


class Environment:
    def __init__(
        self,
        tmp_path,
        *,
        script="print('POST_FINALIZE_OK')",
        post_finalize=True,
        internal_writes=False,
        toggle_guard=False,
        retention_policy=None,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=100,
            clock=lambda: 10.0,
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
            max_receipts=100,
        )
        self.attempts = AIExecutionAttemptStore(
            self.backend,
            namespace="attempts",
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            ArtifactSigner(
                "checkpoint",
                b"c" * 32,
                clock=lambda: 100.0,
            ),
            namespace="chain-checkpoints",
            clock=lambda: 100.0,
        )
        self.retention = DurableRetentionPlanner(
            self.checkpoints,
            retention_policy
            or DurableRetentionPolicy(
                minimum_live_tail=1,
                minimum_archive_batch=1,
                target_utilization=0.60,
                warning_utilization=0.80,
                critical_utilization=0.95,
            ),
        )
        self.operations = DurableEvidenceOperationsInspector(
            self.checkpoints,
            self.retention,
        )
        self.cursor_store = DurableVerificationCursorStore(
            self.backend,
            ArtifactSigner(
                "cursor",
                b"v" * 32,
                clock=lambda: 100.0,
            ),
            namespace="cursors",
        )
        self.incremental = DurableIncrementalVerifier(
            self.cursor_store,
            clock=lambda: 100.0,
        )
        self.verification = DurableVerificationOperator(
            self.cursor_store,
            self.incremental,
        )
        self.sequence = DurableSequenceIndexOperator()
        guard_type = (
            ToggleFailureReadinessGuard
            if toggle_guard
            else DurableEvidenceReadinessGuard
        )
        self.readiness = guard_type(
            self.operations,
            self.sequence,
            self.verification,
        )
        self.entries = (
            ("journal", self.journal),
            ("receipts", self.receipts),
        )

        catalog_value = command_catalog()
        effects_value = effects()
        policy = AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            min_confidence=0.5,
            max_uncertainty=0.5,
        )
        model_value = model(script)
        root = tmp_path / "root"
        root.mkdir()
        shell = ShellService(
            ShellExecutor(
                ShellRunner(
                    ShellPolicy(
                        executables={
                            "python": sys.executable,
                        },
                        cwd_roots=(root,),
                        default_timeout=2,
                        max_timeout=4,
                        max_output_bytes=4096,
                        max_input_bytes=4096,
                        max_env_bytes=4096,
                        max_args=32,
                        max_arg_bytes=4096,
                    )
                ),
                receipts=self.receipts,
            ),
            receipts=self.receipts,
        )
        shell.start()
        tools = AIToolCatalog(catalog_value)
        planner = AIPlanner(
            model_value,
            tools,
            AIToolRouter(
                tools,
                effects_value,
            ),
            policy_fingerprint=policy.fingerprint,
        )
        self.orchestrator = AIShellOrchestrator(
            planner=planner,
            critic=AIPlanCritic(
                effects_value,
                policy,
            ),
            compiler=AIPlanCompiler(effects_value),
            shell_service=shell,
            journal=self.journal,
        )
        self.service = AIShellService(
            self.orchestrator,
            AIShellDiagnostics(
                tools,
                effects_value,
                policy,
                model_value,
            ),
            AIShellGovernance(AIPolicyStore(policy)),
            execution_attempts=self.attempts,
            worker_id="worker-post-finalize",
            durable_operations_inspector=self.operations,
            durable_operations_chains=self.entries,
            durable_readiness_guard=self.readiness,
            durable_readiness_reconcile_on_start=True,
            durable_readiness_reconcile_after_internal_writes=(
                internal_writes
            ),
            durable_readiness_reconcile_after_finalization=(
                post_finalize
            ),
        )
        self.service.start()
        if self.service.state.phase is not AIServicePhase.READY:
            raise AssertionError(
                "test environment failed readiness bootstrap"
            )

        self.session_evidence = SessionEvidenceStore(
            self.backend,
            namespace="session-evidence",
        )
        self.recovery = AIRecoveryCheckpointStore(
            self.backend,
            namespace="recovery",
            clock=lambda: 10.0,
        )
        self.anchors = AIAuditAnchorStore(
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
        self.finalizer = AIExecutionEvidenceFinalizer(
            journal=self.journal,
            receipt_chain=self.receipts,
            session_evidence=self.session_evidence,
            audit_anchors=self.anchors,
            audit_witnesses=self.witnesses,
            execution_evidence=self.execution_evidence,
            finalizations=self.finalizations,
            recovery_checkpoints=self.recovery,
        )

    def prepare(
        self,
        *,
        session_id="session",
        intent_id="intent",
        manual_refresh=True,
    ):
        session = self.service.new_session(
            intent(intent_id=intent_id),
            session_id=session_id,
        )
        review, _ = self.service.review(session)
        if (
            manual_refresh
            and not self.service
            .durable_readiness_reconcile_after_internal_writes
        ):
            self.service.reconcile_durable_readiness()
        authority = ExecutionSealAuthority(b"k" * 32)
        registry = ExecutionSealRegistry(authority)
        seal = self.service.seal_review(
            session,
            review,
            principal="alice",
            authority=authority,
        )
        return session, review, seal, registry

    def execute(
        self,
        *,
        session_id="session",
        intent_id="intent",
        before_execute=None,
    ):
        session, review, seal, registry = self.prepare(
            session_id=session_id,
            intent_id=intent_id,
        )
        if before_execute is not None:
            before_execute()
        result = self.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext(
                f"context-{session_id}",
                principal="alice",
            ),
            seal=seal,
            seal_registry=registry,
            finalizer=self.finalizer,
        )
        return session, review, seal, registry, result


def test_successful_post_finalize_readiness_is_reported(tmp_path):
    env = Environment(
        tmp_path,
        post_finalize=True,
        internal_writes=False,
    )
    _, _, seal, registry, result = env.execute()
    assert result.ok
    assert result.post_execution_maintenance_attempted
    assert result.post_execution_maintenance_ok
    assert result.post_execution_maintenance_error == ""
    assert result.durable_readiness is not None
    assert result.durable_readiness.ready
    assert env.service.state.phase is AIServicePhase.READY
    assert registry.used(seal.seal_id)


def test_post_finalize_result_serializes_maintenance_state(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    data = result.to_dict()
    assert data["ok"] is True
    assert data["post_execution_maintenance_attempted"] is True
    assert data["post_execution_maintenance_ok"] is True
    assert data["post_execution_maintenance_error"] == ""
    assert data["durable_readiness"]["ready"] is True


def test_successful_post_finalize_refresh_keeps_next_session_admissible(tmp_path):
    env = Environment(tmp_path)
    env.execute()
    next_session = env.service.new_session(
        intent(intent_id="next")
    )
    assert next_session.intent.intent_id == "next"
    assert env.service.state.phase is AIServicePhase.READY


def test_post_finalize_refresh_tracks_terminal_journal_head(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    verification = result.durable_readiness.verification
    by_id = {
        item.chain_id: item
        for item in verification.chains
    }
    assert (
        by_id["journal"].live_root
        == env.journal.root_hash()
    )
    assert (
        by_id["receipts"].live_root
        == env.receipts.root_hash()
    )


def test_post_finalize_refresh_does_not_change_execution_truth(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    assert result.ok == result.execution.ok
    assert (
        result.finalized.finalization.phase
        is FinalizationPhase.COMPLETE
    )
    assert (
        result.execution_attempt.state
        is ExecutionAttemptState.SUCCEEDED
    )


def test_failed_child_is_finalized_and_readiness_is_refreshed(tmp_path):
    env = Environment(
        tmp_path,
        script="import sys; sys.exit(7)",
    )
    _, _, _, _, result = env.execute()
    assert not result.execution.ok
    assert not result.ok
    assert result.post_execution_maintenance_attempted
    assert result.post_execution_maintenance_ok
    assert result.durable_readiness.ready
    assert (
        result.execution_attempt.state
        is ExecutionAttemptState.FAILED
    )
    assert (
        result.finalized.finalization.phase
        is FinalizationPhase.COMPLETE
    )
    assert env.service.state.phase is AIServicePhase.READY


def test_disabled_post_finalize_maintenance_is_explicit(tmp_path):
    env = Environment(
        tmp_path,
        post_finalize=False,
        internal_writes=False,
    )
    _, _, _, _, result = env.execute()
    assert result.ok
    assert not result.post_execution_maintenance_attempted
    assert result.post_execution_maintenance_ok
    assert result.durable_readiness is None
    assert result.post_execution_maintenance_error == ""


def test_disabled_post_finalize_maintenance_leaves_expected_drift(tmp_path):
    env = Environment(
        tmp_path,
        post_finalize=False,
        internal_writes=False,
    )
    env.execute()
    with pytest.raises(
        RuntimeError,
        match="readiness",
    ):
        env.service.new_session(
            intent(intent_id="after-disabled")
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_maintenance_exception_does_not_raise_after_terminal_execution(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
        post_finalize=True,
    )

    def fail():
        env.readiness.fail_reconcile = True

    _, _, seal, registry, result = env.execute(
        before_execute=fail,
    )
    assert result.ok
    assert result.post_execution_maintenance_attempted
    assert not result.post_execution_maintenance_ok
    assert result.durable_readiness is None
    assert (
        result.post_execution_maintenance_error
        == "durable_readiness_maintenance_RuntimeError"
    )
    assert registry.used(seal.seal_id)
    assert env.service.state.phase is AIServicePhase.DEGRADED
    assert len(env.receipts.snapshot()) == 1
    assert len(env.execution_evidence.snapshot()) == 1
    assert len(env.anchors.snapshot()) == 1


def test_maintenance_exception_preserves_complete_finalization(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
        post_finalize=True,
    )

    def fail():
        env.readiness.fail_reconcile = True

    _, _, seal, _, result = env.execute(
        before_execute=fail,
    )
    finalization = env.finalizations.current(
        result.finalized.finalization.finalization_id
    ).finalization
    assert finalization.phase is FinalizationPhase.COMPLETE
    assert (
        finalization.execution_attempt_id
        == seal.seal_id
    )
    assert (
        finalization.execution_evidence_digest
        == result.finalized.execution_evidence.evidence.digest
    )


def test_maintenance_exception_blocks_new_work(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    env.execute(before_execute=fail)
    with pytest.raises(
        RuntimeError,
        match="not ready",
    ):
        env.service.new_session(
            intent(intent_id="blocked")
        )


def test_operator_recovery_after_maintenance_exception(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    env.execute(before_execute=fail)
    assert env.service.state.phase is AIServicePhase.DEGRADED
    env.readiness.fail_reconcile = False
    report = env.service.reconcile_durable_readiness()
    assert report.ready
    assert env.service.state.phase is AIServicePhase.READY
    assert env.service.new_session(
        intent(intent_id="recovered")
    ).intent.intent_id == "recovered"


def test_retry_same_seal_after_maintenance_failure_cannot_respawn_child(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )
    session, review, seal, registry = env.prepare()
    env.readiness.fail_reconcile = True
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext(
            "context",
            principal="alice",
        ),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert result.ok
    assert len(env.receipts.snapshot()) == 1

    env.readiness.fail_reconcile = False
    env.service.reconcile_durable_readiness()
    with pytest.raises(RuntimeError):
        env.service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext(
                "context-retry",
                principal="alice",
            ),
            seal=seal,
            seal_registry=registry,
            finalizer=env.finalizer,
        )
    assert len(env.receipts.snapshot()) == 1
    assert len(env.execution_evidence.snapshot()) == 1


def test_maintenance_failure_does_not_change_terminal_attempt(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    _, _, seal, _, result = env.execute(
        before_execute=fail,
    )
    stored = env.attempts.current(seal.seal_id)
    assert stored is not None
    assert stored.attempt.state is ExecutionAttemptState.SUCCEEDED
    assert (
        stored.attempt.terminal_evidence_digest
        == result.execution.provenance.digest
    )


def test_maintenance_exception_error_does_not_include_exception_message(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    _, _, _, _, result = env.execute(
        before_execute=fail,
    )
    assert "synthetic" not in (
        result.post_execution_maintenance_error
    )
    assert (
        result.post_execution_maintenance_error
        == "durable_readiness_maintenance_RuntimeError"
    )


def test_post_finalize_capacity_denial_returns_terminal_result(tmp_path):
    retention = DurableRetentionPolicy(
        minimum_live_tail=1,
        minimum_archive_batch=1,
        target_utilization=0.01,
        warning_utilization=0.02,
        critical_utilization=0.025,
    )
    env = Environment(
        tmp_path,
        internal_writes=False,
        post_finalize=True,
        retention_policy=retention,
    )
    # Review writes two journal events. Manual refresh still allows warnings.
    session, review, seal, registry = env.prepare()
    assert env.service.state.phase is AIServicePhase.READY

    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext(
            "capacity-context",
            principal="alice",
        ),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert result.ok
    assert result.post_execution_maintenance_attempted
    assert not result.post_execution_maintenance_ok
    assert result.durable_readiness is not None
    assert not result.durable_readiness.ready
    assert (
        result.post_execution_maintenance_error
        == "durable_readiness_not_ready"
    )
    assert env.service.state.phase is AIServicePhase.DEGRADED
    assert len(env.receipts.snapshot()) == 1


def test_capacity_denial_still_signs_execution_evidence(tmp_path):
    retention = DurableRetentionPolicy(
        minimum_live_tail=1,
        minimum_archive_batch=1,
        target_utilization=0.01,
        warning_utilization=0.02,
        critical_utilization=0.025,
    )
    env = Environment(
        tmp_path,
        internal_writes=False,
        post_finalize=True,
        retention_policy=retention,
    )
    _, _, _, _, result = env.execute()
    assert result.finalized.execution_evidence is not None
    assert env.execution_evidence.verify()
    assert (
        result.finalized.execution_evidence.evidence.digest
        == result.finalized.finalization.execution_evidence_digest
    )


def test_post_finalize_success_report_matches_service_status(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    status = env.service.status()
    assert status.durable_readiness is not None
    assert (
        status.durable_readiness["digest"]
        == result.durable_readiness.digest
    )


def test_post_finalize_failure_keeps_previous_status_proof_and_degrades(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )
    before = env.service.status().durable_readiness

    def fail():
        env.readiness.fail_reconcile = True

    _, _, _, _, result = env.execute(
        before_execute=fail,
    )
    assert result.durable_readiness is None
    assert env.service.status().durable_readiness == before
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_internal_write_and_post_finalize_reconciliation_coexist(tmp_path):
    env = Environment(
        tmp_path,
        internal_writes=True,
        post_finalize=True,
    )
    _, _, _, _, result = env.execute(
        before_execute=None,
    )
    assert result.ok
    assert result.post_execution_maintenance_attempted
    assert result.post_execution_maintenance_ok
    assert env.service.state.phase is AIServicePhase.READY
    assert env.service.new_session(
        intent(intent_id="after-both")
    ).intent.intent_id == "after-both"


def test_internal_write_reconciliation_avoids_manual_prepare_refresh(tmp_path):
    env = Environment(
        tmp_path,
        internal_writes=True,
        post_finalize=True,
    )
    session, review, seal, registry = env.prepare(
        manual_refresh=False,
    )
    result = env.service.execute_sealed_and_finalize(
        session,
        review,
        context=ExecutionContext(
            "auto-context",
            principal="alice",
        ),
        seal=seal,
        seal_registry=registry,
        finalizer=env.finalizer,
    )
    assert result.ok
    assert env.service.state.phase is AIServicePhase.READY


def test_result_maintenance_attempted_validation(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    with pytest.raises(
        ValueError,
        match="attempted",
    ):
        type(result)(
            result.execution,
            result.preconditions,
            result.seal_use,
            result.finalized,
            result.execution_attempt,
            result.durable_readiness,
            "yes",
            "",
        )


def test_result_maintenance_error_length_validation(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    with pytest.raises(
        ValueError,
        match="too long",
    ):
        type(result)(
            result.execution,
            result.preconditions,
            result.seal_use,
            result.finalized,
            result.execution_attempt,
            result.durable_readiness,
            True,
            "x" * 513,
        )


def test_result_ok_is_independent_of_maintenance_failure(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    _, _, _, _, result = env.execute(
        before_execute=fail,
    )
    assert result.ok
    assert not result.post_execution_maintenance_ok


def test_failed_execution_ok_remains_false_even_when_maintenance_succeeds(tmp_path):
    env = Environment(
        tmp_path,
        script="import sys; sys.exit(2)",
    )
    _, _, _, _, result = env.execute()
    assert not result.ok
    assert result.post_execution_maintenance_ok


def test_post_finalize_readiness_policy_digest_is_returned(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    assert (
        result.durable_readiness.policy_digest
        == env.readiness.policy.digest
    )


def test_post_finalize_maintenance_is_idempotent_after_success(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    before = result.durable_readiness.digest
    again = env.service.reconcile_durable_readiness()
    assert again.ready
    assert again.mutations == ()
    assert env.service.state.phase is AIServicePhase.READY
    assert again.digest != ""


def test_post_finalize_cursor_heads_match_chain_heads(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    verification = result.durable_readiness.verification
    for chain_id, chain in env.entries:
        item = next(
            entry
            for entry in verification.chains
            if entry.chain_id == chain_id
        )
        assert item.live_sequence == chain.head().sequence
        assert item.live_root == chain.head().root_hash


def test_post_finalize_sequence_indexes_remain_healthy(tmp_path):
    env = Environment(tmp_path)
    _, _, _, _, result = env.execute()
    assert result.durable_readiness.sequence_indexes.ok
    assert env.journal.inspect_sequence_indexes().healthy
    assert env.receipts.inspect_sequence_indexes().healthy


def test_post_finalize_does_not_add_second_process_receipt(tmp_path):
    env = Environment(tmp_path)
    before = env.receipts.length()
    _, _, _, _, result = env.execute()
    assert result.ok
    assert env.receipts.length() == before + 1
    assert len(result.execution.report.steps) == 1


def test_post_finalize_maintenance_failure_reason_is_specific(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    env.execute(before_execute=fail)
    transition = env.service.state.history()[-1]
    assert transition.current is AIServicePhase.DEGRADED
    assert (
        transition.reason
        == "AI durable evidence readiness post-execution maintenance failed"
    )


def test_post_finalize_failure_can_be_recovered_without_execution_retry(tmp_path):
    env = Environment(
        tmp_path,
        toggle_guard=True,
        internal_writes=False,
    )

    def fail():
        env.readiness.fail_reconcile = True

    _, _, _, _, result = env.execute(
        before_execute=fail,
    )
    receipt_root = env.receipts.root_hash()
    evidence_root = env.execution_evidence.root_hash()
    env.readiness.fail_reconcile = False
    env.service.reconcile_durable_readiness()
    assert env.receipts.root_hash() == receipt_root
    assert env.execution_evidence.root_hash() == evidence_root
    assert result.ok
    assert env.service.state.phase is AIServicePhase.READY

"""AIShellService integration for unified durable evidence readiness."""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIShellDiagnostics
from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_operations import (
    DurableEvidenceOperationsInspector,
)
from skeleton.shells.ai.durable_readiness import (
    DurableEvidenceReadinessGuard,
    DurableEvidenceReadinessPolicy,
    DurableEvidenceReadinessState,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexOperator,
    DurableSequenceIndexPolicy,
)
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
)
from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperator,
)
from skeleton.shells.ai.effects import (
    EffectContract,
    EffectKind,
    EffectRegistry,
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
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.types import (
    AIAction,
    AIIntent,
    AIPlanProposal,
)
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(f"receipt:{index}"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def commands() -> CommandCatalog:
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec(
                    "python",
                    sys.executable,
                ),
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
                frozenset(
                    {EffectKind.READ_FILESYSTEM}
                ),
                idempotent=True,
                reversible=True,
            ),
        )
    )


def model() -> CallableAIModelPort:
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
                        ("-V",),
                    ),
                ),
                confidence=0.95,
                uncertainty=0.05,
                model_id="model",
            ),
        )

    return CallableAIModelPort(
        "model",
        propose,
    )


class ServiceEnvironment:
    def __init__(
        self,
        tmp_path,
        *,
        reconcile_on_start=False,
        reconcile_after_internal_writes=False,
        reconcile_after_finalization=False,
        readiness_policy=None,
        journal_capacity=100,
        receipt_capacity=100,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=journal_capacity,
            clock=lambda: 10.0,
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
            max_receipts=receipt_capacity,
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            ArtifactSigner(
                "checkpoint",
                b"c" * 32,
                clock=lambda: 100.0,
            ),
            namespace="checkpoints",
            clock=lambda: 100.0,
        )
        self.retention = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
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
        self.sequence = DurableSequenceIndexOperator(
            DurableSequenceIndexPolicy(
                max_items_per_chain=1000,
                max_chains=8,
                sample_window_items=4,
            )
        )
        self.readiness = DurableEvidenceReadinessGuard(
            self.operations,
            self.sequence,
            self.verification,
            readiness_policy,
        )
        self.entries = (
            ("journal", self.journal),
            ("receipts", self.receipts),
        )

        catalog_value = commands()
        effects_value = effects()
        policy = AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        )
        model_value = model()
        tools = AIToolCatalog(catalog_value)
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
                    )
                ),
                receipts=self.receipts,
            ),
            receipts=self.receipts,
        )
        shell.start()
        planner = AIPlanner(
            model_value,
            tools,
            AIToolRouter(
                tools,
                effects_value,
            ),
            policy_fingerprint=policy.fingerprint,
        )
        orchestrator = AIShellOrchestrator(
            planner=planner,
            critic=AIPlanCritic(
                effects_value,
                policy,
            ),
            compiler=AIPlanCompiler(
                effects_value,
            ),
            shell_service=shell,
            journal=self.journal,
        )
        self.service = AIShellService(
            orchestrator,
            AIShellDiagnostics(
                tools,
                effects_value,
                policy,
                model_value,
            ),
            AIShellGovernance(
                AIPolicyStore(policy)
            ),
            durable_operations_inspector=self.operations,
            durable_operations_chains=self.entries,
            durable_readiness_guard=self.readiness,
            durable_readiness_reconcile_on_start=(
                reconcile_on_start
            ),
            durable_readiness_reconcile_after_internal_writes=(
                reconcile_after_internal_writes
            ),
            durable_readiness_reconcile_after_finalization=(
                reconcile_after_finalization
            ),
        )

    def append(self, count=1):
        start = self.journal.length() + 1
        for offset in range(count):
            index = start + offset
            self.journal.append(
                "service.readiness",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
            )
            self.receipts.append(
                receipt(index)
            )


def test_start_fails_closed_without_cursor_bootstrap(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=False,
    )
    env.append(2)
    diagnostics = env.service.start()
    assert diagnostics.ok
    assert env.service.state.phase is AIServicePhase.FAILED
    status = env.service.status()
    assert status.durable_readiness is None
    assert env.cursor_store.latest("journal") is None
    assert env.cursor_store.latest("receipts") is None


def test_start_reconcile_bootstraps_readiness(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    diagnostics = env.service.start()
    assert diagnostics.ok
    assert env.service.state.phase is AIServicePhase.READY
    status = env.service.status()
    assert status.durable_readiness is not None
    assert status.durable_readiness["state"] == "ready"
    assert status.durable_readiness["ready"] is True
    assert (
        "verification_full_refresh"
        in status.durable_readiness["mutations"]
    )
    assert env.cursor_store.latest("journal") is not None
    assert env.cursor_store.latest("receipts") is not None


def test_status_to_dict_includes_readiness(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(1)
    env.service.start()
    data = env.service.status().to_dict()
    assert data["durable_readiness"]["ready"] is True
    assert data["durable_readiness"]["policy_digest"] == (
        env.readiness.policy.digest
    )
    assert len(
        data["durable_readiness"]["digest"]
    ) == 64


def test_start_reconciles_missing_sequence_index_and_cursors(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    key = env.journal._sequence_key(2)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    env.service.start()
    assert env.service.state.phase is AIServicePhase.READY
    readiness = env.service.status().durable_readiness
    assert readiness["ready"] is True
    assert readiness["mutations"] == [
        "sequence_index_repair",
        "verification_full_refresh",
    ]
    assert env.journal.inspect_sequence_indexes().healthy


def test_start_reconciles_missing_receipt_index_and_cursors(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    key = env.receipts._sequence_key(2)
    record = env.backend.get(
        "receipts",
        key,
    )
    env.backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    env.service.start()
    assert env.service.state.phase is AIServicePhase.READY
    assert env.receipts.inspect_sequence_indexes().healthy


def test_start_refuses_corrupt_journal_sequence_index(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    events = env.journal.snapshot()
    key = env.journal._sequence_key(1)
    record = env.backend.get("journal", key)
    env.backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    env.service.start()
    assert env.service.state.phase is AIServicePhase.FAILED
    status = env.service.status()
    assert status.durable_readiness is None


def test_start_refuses_corrupt_receipt_sequence_index(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    items = env.receipts.snapshot()
    key = env.receipts._sequence_key(1)
    record = env.backend.get("receipts", key)
    env.backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            items[1].receipt_hash,
        ),
    )
    env.service.start()
    assert env.service.state.phase is AIServicePhase.FAILED


def test_runtime_chain_growth_degrades_before_new_session(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    assert env.service.state.phase is AIServicePhase.READY

    env.append(1)
    with pytest.raises(
        RuntimeError,
        match="readiness",
    ):
        env.service.new_session(
            AIIntent(
                "runtime",
                "run after durable drift",
            )
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED
    status = env.service.status()
    assert status.durable_readiness is not None
    assert status.durable_readiness["blocked"] is True


def test_operator_reconcile_restores_ready_after_readiness_drift(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    env.append(1)
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "runtime",
                "trigger readiness drift",
            )
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED

    report = env.service.reconcile_durable_readiness()
    assert report.ready
    assert (
        "verification_full_refresh"
        in report.mutations
    )
    assert env.service.state.phase is AIServicePhase.READY
    session = env.service.new_session(
        AIIntent(
            "recovered",
            "work after readiness recovery",
        )
    )
    assert session.intent.intent_id == "recovered"


def test_reconcile_repairs_runtime_missing_index_and_restores_ready(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    env.service.start()
    key = env.journal._sequence_key(2)
    record = env.backend.get("journal", key)
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "missing-index",
                "detect missing sequence index",
            )
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED
    report = env.service.reconcile_durable_readiness()
    assert report.ready
    assert "sequence_index_repair" in report.mutations
    assert env.service.state.phase is AIServicePhase.READY


def test_reconcile_does_not_restore_unrelated_degradation(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    env.service.state.transition(
        AIServicePhase.DEGRADED,
        reason="unrelated subsystem failure",
    )
    report = env.service.reconcile_durable_readiness()
    assert report.ready
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_runtime_corrupt_index_degrades_and_reconcile_refuses(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    env.service.start()

    events = env.journal.snapshot()
    key = env.journal._sequence_key(1)
    record = env.backend.get("journal", key)
    env.backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "corruption",
                "detect corrupted index",
            )
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED
    with pytest.raises(
        RuntimeError,
        match="incomplete",
    ):
        env.service.reconcile_durable_readiness()
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_reconcile_method_requires_guard(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(1)
    service = env.service
    service.durable_readiness_guard = None
    with pytest.raises(
        RuntimeError,
        match="not configured",
    ):
        service.reconcile_durable_readiness()


def test_readiness_constructor_requires_operations_inspector(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    with pytest.raises(
        ValueError,
        match="operations inspector",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_readiness_guard=env.readiness,
        )


def test_readiness_constructor_requires_operations_chains(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    with pytest.raises(
        ValueError,
        match="operations chains",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_operations_inspector=env.operations,
            durable_readiness_guard=env.readiness,
        )


def test_readiness_constructor_rejects_wrong_guard_type(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    with pytest.raises(
        TypeError,
        match="durable_readiness_guard",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_operations_inspector=env.operations,
            durable_operations_chains=env.entries,
            durable_readiness_guard=object(),
        )


def test_readiness_constructor_rejects_wrong_operations_identity(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    other = DurableEvidenceOperationsInspector(
        env.checkpoints,
        env.retention,
    )
    with pytest.raises(
        ValueError,
        match="must use configured",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_operations_inspector=other,
            durable_operations_chains=env.entries,
            durable_readiness_guard=env.readiness,
        )


def test_reconcile_on_start_must_be_bool(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    with pytest.raises(
        ValueError,
        match="must be bool",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_operations_inspector=env.operations,
            durable_operations_chains=env.entries,
            durable_readiness_guard=env.readiness,
            durable_readiness_reconcile_on_start="yes",
        )


def test_status_omits_readiness_when_not_configured(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    bare = AIShellService(
        env.service.orchestrator,
        env.service.diagnostics,
        env.service.governance,
    )
    bare.start()
    assert bare.status().durable_readiness is None
    assert (
        "durable_readiness"
        not in bare.status().to_dict()
    )


def test_status_tracks_latest_runtime_readiness_report(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    startup_digest = (
        env.service.status()
        .durable_readiness["digest"]
    )

    env.append(1)
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "drift",
                "trigger drift",
            )
        )
    drift_status = env.service.status()
    assert (
        drift_status.durable_readiness["digest"]
        != startup_digest
    )
    assert drift_status.durable_readiness["blocked"] is True

    repaired = env.service.reconcile_durable_readiness()
    final_status = env.service.status()
    assert final_status.durable_readiness["ready"] is True
    assert (
        final_status.durable_readiness["digest"]
        == repaired.digest
    )


def test_start_readiness_report_is_stable_across_status_calls(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    first = env.service.status().durable_readiness
    second = env.service.status().durable_readiness
    assert first == second


def test_reconcile_after_missing_receipt_index_records_mutation(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(3)
    env.service.start()
    key = env.receipts._sequence_key(1)
    record = env.backend.get("receipts", key)
    env.backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "receipt-index",
                "trigger receipt index drift",
            )
        )
    report = env.service.reconcile_durable_readiness()
    assert report.ready
    assert report.mutations == (
        "sequence_index_repair",
    )


def test_runtime_readiness_is_checked_before_review(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "review-intent",
            "review after startup",
        )
    )
    env.append(1)
    with pytest.raises(
        RuntimeError,
        match="readiness",
    ):
        env.service.review(session)
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_runtime_readiness_reconcile_then_review_succeeds(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "review-intent",
            "review after recovery",
        )
    )
    env.append(1)
    with pytest.raises(RuntimeError):
        env.service.review(session)
    env.service.reconcile_durable_readiness()
    review, _ = env.service.review(session)
    assert review.planning.response.proposal.proposal_id == "proposal"


def test_operations_capacity_drift_precedes_readiness(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        journal_capacity=5,
        receipt_capacity=5,
    )
    env.append(2)
    env.service.start()
    env.append(3)
    with pytest.raises(
        RuntimeError,
        match="durable evidence operations",
    ):
        env.service.new_session(
            AIIntent(
                "capacity",
                "trigger critical capacity",
            )
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_reconcile_cannot_mask_operations_capacity_failure(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        journal_capacity=5,
        receipt_capacity=5,
    )
    env.append(2)
    env.service.start()
    env.append(3)
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "capacity",
                "trigger capacity",
            )
        )
    # Readiness reconciliation also composes operations health and therefore
    # cannot clear an independent retention/capacity denial.
    with pytest.raises(
        RuntimeError,
        match="incomplete",
    ):
        env.service.reconcile_durable_readiness()
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_readiness_service_uses_canonical_chain_order(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    assert tuple(
        chain_id
        for chain_id, _
        in env.service.durable_operations_chains
    ) == ("journal", "receipts")


def test_readiness_reconcile_is_idempotent_when_current(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    first = env.service.reconcile_durable_readiness()
    second = env.service.reconcile_durable_readiness()
    assert first.ready
    assert second.ready
    assert first.mutations == ()
    assert second.mutations == ()


def test_service_readiness_policy_digest_visible(tmp_path):
    policy = DurableEvidenceReadinessPolicy(
        max_findings=99,
    )
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        readiness_policy=policy,
    )
    env.append(1)
    env.service.start()
    assert (
        env.service.status()
        .durable_readiness["policy_digest"]
        == policy.digest
    )


def test_failed_start_does_not_transition_back_from_failed(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=False,
    )
    env.append(1)
    env.service.start()
    assert env.service.state.phase is AIServicePhase.FAILED
    with pytest.raises(RuntimeError):
        env.service.reconcile_durable_readiness()
    assert env.service.state.phase is AIServicePhase.FAILED


def test_reconcile_ready_service_does_not_create_lifecycle_transition(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(1)
    env.service.start()
    before = len(env.service.state.history())
    report = env.service.reconcile_durable_readiness()
    after = len(env.service.state.history())
    assert report.ready
    assert before == after


def test_recovery_transition_reason_is_specific(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    env.append(1)
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "transition",
                "trigger transition",
            )
        )
    env.service.reconcile_durable_readiness()
    history = env.service.state.history()
    assert history[-2].current is AIServicePhase.DEGRADED
    assert history[-1].current is AIServicePhase.READY
    assert (
        history[-1].reason
        == "AI durable evidence readiness reconciliation restored service"
    )


def test_failed_start_status_does_not_claim_ready_proof(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=False,
    )
    env.append(1)
    env.service.start()
    status = env.service.status()
    assert status.phase is AIServicePhase.FAILED
    assert status.durable_readiness is None


def test_reconcile_updates_status_mutations(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    env.append(1)
    with pytest.raises(RuntimeError):
        env.service.new_session(
            AIIntent(
                "mutation",
                "trigger drift",
            )
        )
    report = env.service.reconcile_durable_readiness()
    status = env.service.status()
    assert status.durable_readiness["mutations"] == list(
        report.mutations
    )


def test_readiness_reconcile_does_not_mutate_healthy_sequence_indexes(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(2)
    env.service.start()
    before = tuple(
        env.backend.get(
            "journal",
            env.journal._sequence_key(sequence),
        ).revision
        for sequence in range(1, 3)
    )
    env.service.reconcile_durable_readiness()
    after = tuple(
        env.backend.get(
            "journal",
            env.journal._sequence_key(sequence),
        ).revision
        for sequence in range(1, 3)
    )
    assert before == after


def test_multiple_drift_recovery_cycles_are_supported(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    env.append(1)
    env.service.start()
    for cycle in range(3):
        env.append(1)
        with pytest.raises(RuntimeError):
            env.service.new_session(
                AIIntent(
                    f"cycle-{cycle}",
                    "detect verification drift",
                )
            )
        assert env.service.state.phase is AIServicePhase.DEGRADED
        report = env.service.reconcile_durable_readiness()
        assert report.ready
        assert env.service.state.phase is AIServicePhase.READY

def test_review_self_drift_blocks_later_seal_without_internal_refresh(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=False,
    )
    env.append(1)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "self-drift",
            "review creates journal evidence",
        )
    )
    review, _ = env.service.review(session)
    assert env.service.state.phase is AIServicePhase.READY
    assert (
        env.service.status()
        .durable_readiness["ready"]
        is True
    )
    from skeleton.shells.ai.execution_seal import ExecutionSealAuthority

    with pytest.raises(
        RuntimeError,
        match="readiness",
    ):
        env.service.seal_review(
            session,
            review,
            principal="alice",
            authority=ExecutionSealAuthority(
                b"k" * 32
            ),
        )
    assert env.service.state.phase is AIServicePhase.DEGRADED


def test_review_internal_refresh_keeps_seal_path_ready(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=True,
    )
    env.append(1)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "self-refresh",
            "review refreshes durable evidence",
        )
    )
    before_root = env.journal.root_hash()
    review, _ = env.service.review(session)
    assert env.journal.root_hash() != before_root
    assert env.service.state.phase is AIServicePhase.READY
    assert (
        env.service.status()
        .durable_readiness["ready"]
        is True
    )

    from skeleton.shells.ai.execution_seal import ExecutionSealAuthority

    seal = env.service.seal_review(
        session,
        review,
        principal="alice",
        authority=ExecutionSealAuthority(
            b"k" * 32
        ),
    )
    assert seal.session_id == session.session_id
    assert env.service.state.phase is AIServicePhase.READY


def test_internal_review_refresh_records_verification_mutation(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=True,
    )
    env.append(1)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "review-refresh",
            "capture readiness mutation",
        )
    )
    env.service.review(session)
    readiness = env.service.status().durable_readiness
    assert readiness["ready"] is True
    assert (
        "verification_full_refresh"
        in readiness["mutations"]
    )


def test_unsealed_execution_internal_refresh_keeps_next_session_ready(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=True,
    )
    env.append(1)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "execute-refresh",
            "run command with durable refresh",
        )
    )
    review, _ = env.service.review(session)
    result = env.service.execute(
        session,
        review,
        context=__import__(
            "skeleton.shells.execution_context",
            fromlist=["ExecutionContext"],
        ).ExecutionContext(
            "ctx",
            principal="alice",
        ),
    )
    assert result.ok
    assert env.service.state.phase is AIServicePhase.READY
    assert env.receipts.length() >= 2
    next_session = env.service.new_session(
        AIIntent(
            "next-after-execute",
            "service remains ready",
        )
    )
    assert next_session.intent.intent_id == "next-after-execute"


def test_internal_execution_refresh_tracks_latest_chain_heads(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=True,
    )
    env.append(1)
    env.service.start()
    session = env.service.new_session(
        AIIntent(
            "head-refresh",
            "bind latest durable heads",
        )
    )
    review, _ = env.service.review(session)
    from skeleton.shells.execution_context import ExecutionContext

    env.service.execute(
        session,
        review,
        context=ExecutionContext(
            "ctx",
            principal="alice",
        ),
    )
    verification = (
        env.service.status()
        .durable_readiness["verification"]
    )
    by_id = {
        item["chain_id"]: item
        for item in verification["chains"]
    }
    assert (
        by_id["journal"]["current_root"]
        == env.journal.root_hash()
    )
    assert (
        by_id["receipts"]["current_root"]
        == env.receipts.root_hash()
    )


def test_internal_write_reconcile_flag_must_be_bool(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    with pytest.raises(
        ValueError,
        match="internal_writes",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_operations_inspector=env.operations,
            durable_operations_chains=env.entries,
            durable_readiness_guard=env.readiness,
            durable_readiness_reconcile_after_internal_writes="yes",
        )


def test_post_finalization_reconcile_flag_must_be_bool(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
    )
    with pytest.raises(
        ValueError,
        match="after_finalization",
    ):
        AIShellService(
            env.service.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            durable_operations_inspector=env.operations,
            durable_operations_chains=env.entries,
            durable_readiness_guard=env.readiness,
            durable_readiness_reconcile_after_finalization="yes",
        )


def test_internal_refresh_does_not_repair_preexisting_external_drift(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=True,
    )
    env.append(2)
    env.service.start()

    # Drift exists before the review stage begins, so the pre-stage readiness
    # check must block before the model is called. Internal write maintenance
    # is not a general-purpose external auto-healer.
    key = env.journal._sequence_key(1)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    session = env.service.new_session(
        AIIntent(
            "preexisting-drift",
            "must not auto-heal external drift",
        )
    )
    with pytest.raises(RuntimeError):
        env.service.review(session)
    assert env.service.state.phase is AIServicePhase.DEGRADED
    assert env.journal._sequence_index(1) is None


def test_internal_refresh_supports_multiple_review_execute_cycles(tmp_path):
    env = ServiceEnvironment(
        tmp_path,
        reconcile_on_start=True,
        reconcile_after_internal_writes=True,
    )
    env.append(1)
    env.service.start()
    from skeleton.shells.execution_context import ExecutionContext

    for index in range(3):
        session = env.service.new_session(
            AIIntent(
                f"cycle-{index}",
                "review and execute with write-aware refresh",
            )
        )
        review, _ = env.service.review(session)
        result = env.service.execute(
            session,
            review,
            context=ExecutionContext(
                f"ctx-{index}",
                principal="alice",
            ),
        )
        assert result.ok
        assert env.service.state.phase is AIServicePhase.READY
        assert (
            env.service.status()
            .durable_readiness["ready"]
            is True
        )


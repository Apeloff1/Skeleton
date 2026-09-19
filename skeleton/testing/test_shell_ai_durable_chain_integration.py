"""End-to-end durable journal/receipt chain integration for AI shell execution."""

from __future__ import annotations

import hashlib
from dataclasses import replace
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
from skeleton.shells.ai.durable_archive import (
    DurableArchiveManifestBuilder,
)
from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveRepository,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_health import (
    DurableRecoveryHealthGuard,
    DurableRecoveryHealthPolicy,
)
from skeleton.shells.ai.durable_proof_window import (
    DurableHistoricalProofAuthority,
    DurableHistoricalProofStore,
)
from skeleton.shells.ai.durable_proof_window_operator import (
    DurableProofWindowOperator,
    DurableProofWindowPolicy,
    DurableProofWindowTarget,
)
from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalStore,
)
from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryStatus,
    DurableRecoveryVerificationError,
    DurableSessionRecoveryVerifier,
)
from skeleton.shells.ai.effects import (
    EffectContract,
    EffectKind,
    EffectRegistry,
)
from skeleton.shells.ai.evidence_finalizer import AIExecutionEvidenceFinalizer
from skeleton.shells.ai.execution_attempt import (
    AIExecutionAttemptStore,
    ExecutionAttemptState,
)
from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceStore
from skeleton.shells.ai.execution_obligation import (
    AIExecutionObligationStore,
    ExecutionObligationState,
)
from skeleton.shells.ai.execution_obligation_recovery import (
    AIExecutionObligationRecoveryInspector,
    ExecutionObligationRecoveryDisposition,
)
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority
from skeleton.shells.ai.finalization_reconciler import (
    AIExecutionFinalizationReconciler,
    FinalizationReconcileAction,
)
from skeleton.shells.ai.finalization_state import AIExecutionFinalizationStore
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.lifecycle import AIServicePhase
from skeleton.shells.ai.model_port import CallableAIModelPort
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.protocol import AIModelResponse
from skeleton.shells.ai.recovery_requirement_operator import (
    DurableRecoveryRequirementOperator,
    RecoveryRequirementOperatorError,
)
from skeleton.shells.ai.recovery_requirements import (
    DurableRecoveryRequirementStore,
)
from skeleton.shells.ai.recovery_store import AIRecoveryCheckpointStore
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.session_evidence import SessionEvidenceStore
from skeleton.shells.ai.session_integrity import SessionEvidenceIntegrityVerifier
from skeleton.shells.ai.session_journal import SessionJournalEvidence
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
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def make_intent(
    *,
    intent_id="intent",
) -> AIIntent:
    return AIIntent(
        intent_id,
        "run one durable finalized command",
        constraint=IntentConstraint(
            allowed_commands=frozenset({"python"}),
            max_steps=1,
            max_timeout_seconds=2,
            require_reversible=True,
        ),
    )


def make_effects() -> EffectRegistry:
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


def make_commands() -> CommandCatalog:
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


def make_model(
    script="print('DURABLE_OK')",
):
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

    return CallableAIModelPort(
        "model",
        propose,
    )


class DurableEnvironment:
    def __init__(
        self,
        tmp_path,
        *,
        script="print('DURABLE_OK')",
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="decision-journal",
            clock=lambda: 10.0,
        )
        self.receipts = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
        )
        self.attempts = AIExecutionAttemptStore(
            self.backend,
            namespace="attempts",
        )

        policy = AIShellPolicy(
            autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
            min_confidence=0.5,
            max_uncertainty=0.5,
        )
        commands = make_commands()
        effects = make_effects()
        catalog = AIToolCatalog(commands)
        model = make_model(script)

        root = tmp_path / "root"
        root.mkdir()
        executor = ShellExecutor(
            ShellRunner(
                ShellPolicy(
                    executables={
                        "python": sys.executable
                    },
                    cwd_roots=(root,),
                    default_timeout=2,
                    max_timeout=5,
                    max_output_bytes=4096,
                    max_input_bytes=4096,
                    max_env_bytes=4096,
                    max_args=32,
                    max_arg_bytes=4096,
                )
            ),
            receipts=self.receipts,
        )
        shell = ShellService(
            executor,
            receipts=self.receipts,
        )
        shell.start()

        planner = AIPlanner(
            model,
            catalog,
            AIToolRouter(
                catalog,
                effects,
            ),
            policy_fingerprint=policy.fingerprint,
        )
        self.orchestrator = AIShellOrchestrator(
            planner=planner,
            critic=AIPlanCritic(
                effects,
                policy,
            ),
            compiler=AIPlanCompiler(
                effects,
            ),
            shell_service=shell,
            journal=self.journal,
        )
        self.service = AIShellService(
            self.orchestrator,
            AIShellDiagnostics(
                catalog,
                effects,
                policy,
                model,
            ),
            AIShellGovernance(
                AIPolicyStore(policy)
            ),
            execution_attempts=self.attempts,
            worker_id="worker-durable",
        )
        self.service.start()

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
            namespace="witness",
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
        self.session_journals = DurableSessionJournalStore(
            self.backend,
            namespace="session-journals",
            clock=lambda: 10.0,
        )
        self.finalizer = AIExecutionEvidenceFinalizer(
            journal=self.journal,
            receipt_chain=self.receipts,
            session_evidence=self.session_evidence,
            audit_anchors=self.anchors,
            audit_witnesses=self.witnesses,
            execution_evidence=(
                self.execution_evidence
            ),
            finalizations=self.finalizations,
            recovery_checkpoints=self.recovery,
            session_journals=self.session_journals,
        )

    def execute(
        self,
        *,
        session_id="session",
        intent_id="intent",
    ):
        session = self.service.new_session(
            make_intent(
                intent_id=intent_id,
            ),
            session_id=session_id,
        )
        review, _ = self.service.review(
            session
        )
        authority = ExecutionSealAuthority(
            b"k" * 32
        )
        registry = ExecutionSealRegistry(
            authority
        )
        seal = self.service.seal_review(
            session,
            review,
            principal="alice",
            authority=authority,
        )
        result = (
            self.service
            .execute_sealed_and_finalize(
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
        )
        return (
            session,
            review,
            seal,
            registry,
            result,
        )


def test_real_execution_writes_durable_journal_and_receipt(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, seal, _, result = env.execute()

    assert result.ok
    assert env.journal.verify()
    assert env.receipts.verify()
    assert env.journal.length() >= 3
    assert env.receipts.length() == 1
    assert (
        env.receipts.snapshot()[0]
        .receipt.receipt_id
        == result.execution.report.steps[0]
        .dispatch.outcome.receipts[0].receipt_id
    )
    assert (
        result.execution_attempt.execution_seal_id
        == seal.seal_id
    )
    assert (
        result.finalized.checkpoint.session_id
        == session.session_id
    )


def test_finalization_returns_verified_session_integrity(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    integrity = result.finalized.session_integrity
    assert integrity is not None
    assert integrity.ok
    assert len(integrity.journal_inclusions) >= 3
    assert len(integrity.receipt_inclusions) == 1
    assert (
        integrity.journal_root
        == result.finalized.checkpoint.journal_root
    )
    assert (
        integrity.receipt_root
        == result.finalized.checkpoint.receipt_root
    )


def test_integrity_digest_is_bound_into_recovery_checkpoint(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    integrity = result.finalized.session_integrity
    recovery = result.finalized.recovery_checkpoint
    assert (
        recovery.session_integrity_digest
        == integrity.digest
    )


def test_integrity_digest_is_bound_into_signed_execution_evidence(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    signed = result.finalized.execution_evidence
    assert signed is not None
    assert (
        signed.evidence.session_integrity_digest
        == result.finalized.session_integrity.digest
    )


def test_recovery_and_signed_bundle_bind_same_integrity_digest(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    assert (
        result.finalized.recovery_checkpoint
        .session_integrity_digest
        == result.finalized.execution_evidence
        .evidence.session_integrity_digest
    )


def test_fresh_readers_reconstruct_finalized_integrity(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()

    journal = DistributedAIDecisionJournal(
        env.backend,
        namespace="decision-journal",
    )
    receipts = DistributedReceiptChain(
        env.backend,
        namespace="receipts",
    )
    session_journal = (
        SessionJournalEvidence.from_journal(
            journal,
            session.session_id,
        )
    )
    session_evidence = (
        env.session_evidence
        .current(session.session_id)
        .evidence
    )
    verifier = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    )
    reconstructed = verifier.require(
        session_journal,
        session_evidence,
        expected_journal_root=(
            result.finalized.checkpoint
            .journal_root
        ),
        expected_receipt_root=(
            result.finalized.checkpoint
            .receipt_root
        ),
    )
    assert (
        reconstructed.digest
        == result.finalized.session_integrity.digest
    )


def test_unrelated_later_work_can_advance_both_chains(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    first_journal_root = (
        first.finalized.checkpoint.journal_root
    )
    first_receipt_root = (
        first.finalized.checkpoint.receipt_root
    )

    env.execute(
        session_id="second",
        intent_id="intent-second",
    )

    assert (
        env.journal.root_hash()
        != first_journal_root
    )
    assert (
        env.receipts.root_hash()
        != first_receipt_root
    )
    assert env.journal.root_is_ancestor(
        first_journal_root
    )
    assert env.receipts.root_is_ancestor(
        first_receipt_root
    )


def test_restart_verifies_first_execution_at_historical_roots(tmp_path):
    env = DurableEnvironment(tmp_path)
    first_session, _, _, _, first = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    env.execute(
        session_id="second",
        intent_id="intent-second",
    )

    fresh_journal = DistributedAIDecisionJournal(
        env.backend,
        namespace="decision-journal",
    )
    fresh_receipts = DistributedReceiptChain(
        env.backend,
        namespace="receipts",
    )
    journal_evidence = (
        SessionJournalEvidence.from_journal(
            fresh_journal,
            first_session.session_id,
        )
    )
    execution_evidence = (
        env.session_evidence
        .current(first_session.session_id)
        .evidence
    )
    reconstructed = SessionEvidenceIntegrityVerifier(
        fresh_journal,
        fresh_receipts,
    ).require(
        journal_evidence,
        execution_evidence,
        expected_journal_root=(
            first.finalized.checkpoint
            .journal_root
        ),
        expected_receipt_root=(
            first.finalized.checkpoint
            .receipt_root
        ),
    )
    assert reconstructed.ok
    assert (
        reconstructed.digest
        == first.finalized.session_integrity.digest
    )


def test_historical_journal_snapshot_excludes_later_session(tmp_path):
    env = DurableEnvironment(tmp_path)
    first_session, _, _, _, first = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    first_root = (
        first.finalized.checkpoint.journal_root
    )
    env.execute(
        session_id="second",
        intent_id="intent-second",
    )

    historical = env.journal.snapshot_at(
        first_root
    )
    assert historical
    assert all(
        event.session_id != "second"
        for event in historical
    )
    assert any(
        event.session_id == first_session.session_id
        for event in historical
    )


def test_historical_receipt_snapshot_excludes_later_receipt(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    first_root = (
        first.finalized.checkpoint.receipt_root
    )
    env.execute(
        session_id="second",
        intent_id="intent-second",
    )
    historical = env.receipts.snapshot_at(
        first_root
    )
    assert len(historical) == 1
    assert env.receipts.length() == 2


def test_fresh_finalization_reconciler_accepts_durable_evidence(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    reconciler = AIExecutionFinalizationReconciler(
        finalizations=env.finalizations,
        session_evidence=env.session_evidence,
        audit_anchors=env.anchors,
        recovery_checkpoints=env.recovery,
        audit_witnesses=env.witnesses,
        execution_evidence=env.execution_evidence,
    )
    report = reconciler.inspect(
        result.finalized.finalization.finalization_id
    )
    assert report.action is FinalizationReconcileAction.COMPLETE
    assert report.ok


def test_fresh_reader_can_require_all_receipts_from_session(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, _ = env.execute()
    evidence = env.session_evidence.current(
        session.session_id
    ).evidence
    receipt_ids = tuple(
        receipt_id
        for step in evidence.steps
        for receipt_id in step.receipt_ids
    )
    fresh = DistributedReceiptChain(
        env.backend,
        namespace="receipts",
    )
    inclusions = fresh.require_receipts(
        receipt_ids
    )
    assert len(inclusions) == len(receipt_ids)
    assert all(
        item.committed
        for item in inclusions
    )


def test_fresh_reader_can_filter_session_journal(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    fresh = DistributedAIDecisionJournal(
        env.backend,
        namespace="decision-journal",
    )
    items = fresh.events_for_session(
        session.session_id,
        root_hash=(
            result.finalized.checkpoint
            .journal_root
        ),
    )
    assert items
    assert all(
        item.session_id == session.session_id
        for item in items
    )


def test_failed_child_still_produces_durable_integrity_proof(tmp_path):
    env = DurableEnvironment(
        tmp_path,
        script="import sys; sys.exit(9)",
    )
    _, _, _, _, result = env.execute()
    assert not result.execution.ok
    assert result.finalized.session_integrity.ok
    assert env.receipts.length() == 1
    assert env.journal.verify()
    assert env.receipts.verify()
    assert (
        result.finalized.recovery_checkpoint
        .session_integrity_digest
        == result.finalized.session_integrity.digest
    )


def test_receipt_index_matches_execution_report_fingerprint(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    receipt_value = (
        result.execution.report.steps[0]
        .dispatch.outcome.receipts[0]
    )
    inclusion = env.receipts.require_receipt(
        receipt_value.receipt_id,
        fingerprint=receipt_value.fingerprint,
    )
    assert inclusion.committed
    assert (
        inclusion.node.receipt.correlation_id
        == receipt_value.correlation_id
    )


def test_signed_bundle_serialization_contains_integrity_digest(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    data = result.finalized.to_dict()
    assert data["session_integrity"]["ok"] is True
    assert (
        data["session_integrity"]["digest"]
        == result.finalized.session_integrity.digest
    )
    assert (
        data["recovery_checkpoint"]
        ["session_integrity_digest"]
        == result.finalized.session_integrity.digest
    )
    assert (
        data["execution_evidence"]
        ["evidence"]["session_integrity_digest"]
        == result.finalized.session_integrity.digest
    )


def test_current_root_mismatch_is_expected_after_later_execution(tmp_path):
    env = DurableEnvironment(tmp_path)
    first_session, _, _, _, first = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    env.execute(
        session_id="second",
        intent_id="intent-second",
    )
    fresh_journal = DistributedAIDecisionJournal(
        env.backend,
        namespace="decision-journal",
    )
    fresh_receipts = DistributedReceiptChain(
        env.backend,
        namespace="receipts",
    )
    assert (
        fresh_journal.root_hash()
        != first.finalized.checkpoint.journal_root
    )
    assert (
        fresh_receipts.root_hash()
        != first.finalized.checkpoint.receipt_root
    )
    reconstructed = SessionEvidenceIntegrityVerifier(
        fresh_journal,
        fresh_receipts,
    ).require(
        SessionJournalEvidence.from_journal(
            fresh_journal,
            first_session.session_id,
        ),
        env.session_evidence.current(
            first_session.session_id
        ).evidence,
        expected_journal_root=(
            first.finalized.checkpoint.journal_root
        ),
        expected_receipt_root=(
            first.finalized.checkpoint.receipt_root
        ),
    )
    assert reconstructed.ok


def test_uncommitted_receipt_node_cannot_satisfy_historical_root(tmp_path):
    env = DurableEnvironment(tmp_path)
    env.execute()
    fake = ExecutionReceipt.now_failure(
        command="python",
        correlation_id="fake",
        fingerprint=fp("f"),
    )
    current = env.receipts.head()
    fake_hash = ReceiptChain._hash(
        current.root_hash,
        current.sequence + 1,
        fake,
    )
    # Put a self-consistent immutable node without advancing the committed head.
    from skeleton.shells.receipts import ChainedReceipt

    env.backend.put_if_absent(
        "receipts",
        f"node:{fake_hash}",
        ChainedReceipt(
            current.sequence + 1,
            current.root_hash,
            fake_hash,
            fake,
        ),
    )
    assert env.receipts.verify_root(
        fake_hash
    )
    assert not env.receipts.root_is_ancestor(
        fake_hash
    )


def test_uncommitted_journal_event_cannot_satisfy_historical_root(tmp_path):
    env = DurableEnvironment(tmp_path)
    env.execute()
    current = env.journal.head()
    from types import MappingProxyType
    from skeleton.shells.ai.journal import (
        AIDecisionEvent,
        AIDecisionJournal,
    )

    payload = MappingProxyType({})
    fake_hash = AIDecisionJournal._hash(
        current.root_hash,
        current.sequence + 1,
        "fake",
        20.0,
        "fake-session",
        "fake-intent",
        "",
        "",
        payload,
    )
    env.backend.put_if_absent(
        "decision-journal",
        f"event:{fake_hash}",
        AIDecisionEvent(
            current.sequence + 1,
            current.root_hash,
            fake_hash,
            "fake",
            20.0,
            "fake-session",
            "fake-intent",
            "",
            "",
            payload,
        ),
    )
    assert env.journal.verify_root(
        fake_hash
    )
    assert not env.journal.root_is_ancestor(
        fake_hash
    )


def test_session_integrity_digest_changes_if_receipt_chain_root_changes(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    before = result.finalized.session_integrity

    extra = ExecutionReceipt.now_failure(
        command="python",
        correlation_id="unrelated",
        fingerprint=fp("f"),
    )
    env.receipts.append(extra)

    current = SessionEvidenceIntegrityVerifier(
        env.journal,
        env.receipts,
    ).require(
        SessionJournalEvidence.from_journal(
            env.journal,
            session.session_id,
        ),
        env.session_evidence.current(
            session.session_id
        ).evidence,
    )
    assert current.ok
    assert current.receipt_root != before.receipt_root
    assert current.digest != before.digest


def test_historical_integrity_digest_remains_stable_after_receipt_advance(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    before = result.finalized.session_integrity
    env.receipts.append(
        ExecutionReceipt.now_failure(
            command="python",
            correlation_id="unrelated",
            fingerprint=fp("f"),
        )
    )

    historical = SessionEvidenceIntegrityVerifier(
        env.journal,
        env.receipts,
    ).require(
        SessionJournalEvidence.from_journal(
            env.journal,
            session.session_id,
        ),
        env.session_evidence.current(
            session.session_id
        ).evidence,
        expected_journal_root=(
            result.finalized.checkpoint.journal_root
        ),
        expected_receipt_root=(
            result.finalized.checkpoint.receipt_root
        ),
    )
    assert historical.digest == before.digest


def test_historical_integrity_digest_remains_stable_after_journal_advance(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    before = result.finalized.session_integrity
    env.journal.append(
        "unrelated",
        session_id="other",
        intent_id="other",
    )

    historical = SessionEvidenceIntegrityVerifier(
        env.journal,
        env.receipts,
    ).require(
        SessionJournalEvidence.from_journal(
            env.journal,
            session.session_id,
        ),
        env.session_evidence.current(
            session.session_id
        ).evidence,
        expected_journal_root=(
            result.finalized.checkpoint.journal_root
        ),
        expected_receipt_root=(
            result.finalized.checkpoint.receipt_root
        ),
    )
    assert historical.digest == before.digest

def durable_verifier(env):
    return DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=DistributedAIDecisionJournal(
            env.backend,
            namespace="decision-journal",
        ),
        receipt_chain=DistributedReceiptChain(
            env.backend,
            namespace="receipts",
        ),
        execution_evidence=env.execution_evidence,
    )


def test_durable_recovery_verifier_accepts_complete_execution(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    report = durable_verifier(env).require_verified(
        result.finalized.finalization.finalization_id
    )
    assert report.ok
    assert report.status is DurableRecoveryStatus.VERIFIED
    assert report.findings == ()
    assert report.integrity is not None
    assert report.integrity.ok
    assert (
        report.session_integrity_digest
        == result.finalized.session_integrity.digest
    )


def test_durable_recovery_verifier_survives_later_chain_growth(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    env.execute(
        session_id="second",
        intent_id="intent-second",
    )
    report = durable_verifier(env).require_verified(
        first.finalized.finalization.finalization_id
    )
    assert report.ok
    assert report.journal_root == first.finalized.checkpoint.journal_root
    assert report.receipt_root == first.finalized.checkpoint.receipt_root
    assert (
        report.session_integrity_digest
        == first.finalized.session_integrity.digest
    )


def test_unknown_finalization_is_incomplete(tmp_path):
    env = DurableEnvironment(tmp_path)
    report = durable_verifier(env).verify(
        "unknown-finalization"
    )
    assert report.status is DurableRecoveryStatus.INCOMPLETE
    assert report.safe_to_resume
    assert not report.ok
    assert report.findings[0].code == "finalization.missing"


def test_missing_recovery_checkpoint_is_incomplete(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    key = env.recovery._item_key(finalization_id)
    record = env.backend.get(
        env.recovery.namespace,
        key,
    )
    env.backend.delete(
        env.recovery.namespace,
        key,
        expected_revision=record.revision,
    )

    report = durable_verifier(env).verify(
        finalization_id
    )
    assert report.status is DurableRecoveryStatus.INCOMPLETE
    assert report.safe_to_resume
    assert any(
        item.code == "recovery.missing"
        for item in report.findings
    )


def test_missing_session_evidence_is_incomplete(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    record = env.backend.get(
        env.session_evidence.namespace,
        session.session_id,
    )
    env.backend.delete(
        env.session_evidence.namespace,
        session.session_id,
        expected_revision=record.revision,
    )
    report = durable_verifier(env).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.status is DurableRecoveryStatus.INCOMPLETE
    assert any(
        item.code == "session_evidence.missing"
        for item in report.findings
    )


def test_substituted_session_evidence_is_manual_review(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    record = env.backend.get(
        env.session_evidence.namespace,
        session.session_id,
    )
    substituted = replace(
        record.value,
        plan_fingerprint=fp("x"),
    )
    env.backend.compare_and_swap(
        env.session_evidence.namespace,
        session.session_id,
        expected_revision=record.revision,
        value=substituted,
    )
    report = durable_verifier(env).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.status is DurableRecoveryStatus.MANUAL_REVIEW
    assert report.requires_manual_review
    assert any(
        "session_evidence" in item.code
        for item in report.findings
    )


def test_substituted_recovery_checkpoint_is_manual_review(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    key = env.recovery._item_key(finalization_id)
    record = env.backend.get(
        env.recovery.namespace,
        key,
    )
    substituted_checkpoint = replace(
        record.value.checkpoint,
        session_integrity_digest=fp("x"),
    )
    substituted_record = replace(
        record.value,
        checkpoint=substituted_checkpoint,
    )
    env.backend.compare_and_swap(
        env.recovery.namespace,
        key,
        expected_revision=record.revision,
        value=substituted_record,
    )
    report = durable_verifier(env).verify(
        finalization_id
    )
    assert report.status is DurableRecoveryStatus.MANUAL_REVIEW
    assert any(
        item.code == "recovery.digest_conflict"
        for item in report.findings
    )


def test_corrupted_historical_journal_is_manual_review(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    root = result.finalized.checkpoint.journal_root
    root_event = env.journal.get_event(root)
    key = env.journal._event_key(root)
    record = env.backend.get(
        env.journal.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.journal.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            root_event,
            summary="tampered",
        ),
    )
    report = durable_verifier(env).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.status is DurableRecoveryStatus.MANUAL_REVIEW
    assert any(
        item.severity.value == "corruption"
        for item in report.findings
    )


def test_corrupted_historical_receipt_is_manual_review(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    root = result.finalized.checkpoint.receipt_root
    item = env.receipts.get_node(root)
    key = env.receipts._node_key(root)
    record = env.backend.get(
        env.receipts.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.receipts.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            item,
            receipt=replace(
                item.receipt,
                stdout_bytes=item.receipt.stdout_bytes + 1,
            ),
        ),
    )
    report = durable_verifier(env).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.status is DurableRecoveryStatus.MANUAL_REVIEW
    assert any(
        item.code.startswith("session_integrity")
        for item in report.findings
    )


def test_required_signed_evidence_store_unavailable_is_incomplete(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    verifier = DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=env.journal,
        receipt_chain=env.receipts,
        execution_evidence=None,
    )
    report = verifier.verify(
        result.finalized.finalization.finalization_id
    )
    assert report.status is DurableRecoveryStatus.INCOMPLETE
    assert any(
        item.code == "signed_evidence.store_missing"
        for item in report.findings
    )


def test_missing_required_signed_evidence_is_incomplete(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    # Use a separate empty signed evidence namespace to model lost durable state.
    empty = AIExecutionEvidenceStore(
        env.backend,
        ArtifactSigner(
            "other-execution",
            b"q" * 32,
            clock=lambda: 10.0,
        ),
        namespace="missing-execution-evidence",
    )
    verifier = DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=env.journal,
        receipt_chain=env.receipts,
        execution_evidence=empty,
    )
    report = verifier.verify(
        result.finalized.finalization.finalization_id
    )
    assert report.status is DurableRecoveryStatus.INCOMPLETE
    assert any(
        item.code == "signed_evidence.missing"
        for item in report.findings
    )


def test_signed_evidence_digest_substitution_is_manual_review(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    stored = env.finalizations.current(
        finalization_id
    )
    substituted = replace(
        stored.finalization,
        execution_evidence_digest=fp("x"),
    )
    key = env.finalizations.key(finalization_id)
    record = env.backend.get(
        env.finalizations.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.finalizations.namespace,
        key,
        expected_revision=record.revision,
        value=substituted,
    )
    report = durable_verifier(env).verify(
        finalization_id
    )
    assert report.status is DurableRecoveryStatus.MANUAL_REVIEW
    assert any(
        item.code == "signed_evidence.finalization_digest"
        for item in report.findings
    )


def test_require_verified_raises_for_incomplete_state(tmp_path):
    env = DurableEnvironment(tmp_path)
    with pytest.raises(
        DurableRecoveryVerificationError,
        match="missing",
    ):
        durable_verifier(env).require_verified(
            "missing"
        )


def test_require_verified_raises_for_conflicting_state(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    record = env.backend.get(
        env.session_evidence.namespace,
        session.session_id,
    )
    env.backend.compare_and_swap(
        env.session_evidence.namespace,
        session.session_id,
        expected_revision=record.revision,
        value=replace(
            record.value,
            plan_fingerprint=fp("x"),
        ),
    )
    with pytest.raises(
        DurableRecoveryVerificationError,
    ):
        durable_verifier(env).require_verified(
            result.finalized.finalization.finalization_id
        )


def test_durable_recovery_report_serializes_full_proof(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    report = durable_verifier(env).require_verified(
        result.finalized.finalization.finalization_id
    )
    data = report.to_dict()
    assert data["status"] == "verified"
    assert data["ok"] is True
    assert data["safe_to_resume"] is False
    assert data["requires_manual_review"] is False
    assert data["integrity"]["ok"] is True
    assert data["digest"] == report.digest
    assert len(data["finalization_digest"]) == 64
    assert len(data["recovery_checkpoint_digest"]) == 64
    assert len(data["signed_execution_evidence_digest"]) == 64


def test_durable_recovery_report_digest_is_stable(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    verifier = durable_verifier(env)
    first = verifier.require_verified(
        result.finalized.finalization.finalization_id
    )
    second = verifier.require_verified(
        result.finalized.finalization.finalization_id
    )
    assert first.digest == second.digest
    assert first == second


def test_durable_recovery_report_digest_survives_unrelated_later_work(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first_result = env.execute(
        session_id="first",
        intent_id="intent-first",
    )
    verifier = durable_verifier(env)
    first = verifier.require_verified(
        first_result.finalized.finalization.finalization_id
    )
    env.execute(
        session_id="second",
        intent_id="intent-second",
    )
    second = verifier.require_verified(
        first_result.finalized.finalization.finalization_id
    )
    assert second.digest == first.digest
    assert second.session_integrity_digest == first.session_integrity_digest

def recovery_requirement_guard(env, *, policy=None):
    verifier = DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=DistributedAIDecisionJournal(
            env.backend,
            namespace="decision-journal",
        ),
        receipt_chain=DistributedReceiptChain(
            env.backend,
            namespace="receipts",
        ),
        execution_evidence=env.execution_evidence,
    )
    return DurableRecoveryHealthGuard(
        verifier,
        policy or DurableRecoveryHealthPolicy(),
    )


def recovery_requirement_store(env, *, scope="prod", ids=()):
    requirements = DurableRecoveryRequirementStore(
        env.backend,
        ArtifactSigner(
            "recovery-requirements",
            b"m" * 32,
            clock=lambda: 20.0,
        ),
        namespace="recovery-requirements",
        clock=lambda: 20.0,
    )
    requirements.initialize(scope, ids)
    return requirements


def restart_service_with_requirements(
    env,
    requirements,
    *,
    scope="prod",
    policy=None,
):
    return AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        worker_id="worker-restart",
        durable_recovery_guard=recovery_requirement_guard(
            env,
            policy=policy,
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope=scope,
    )


def test_service_restart_uses_signed_recovery_requirement_manifest(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )

    restarted.start()
    assert restarted.state.phase is AIServicePhase.READY
    assert restarted.durable_recovery_ids == (finalization_id,)
    status = restarted.status().to_dict()
    manifest = status["durable_recovery_requirements"]["manifest"]
    assert manifest["generation"] == 1
    assert manifest["finalization_ids"] == [finalization_id]
    assert status["durable_recovery"]["allowed"] is True


def test_live_manifest_addition_of_missing_proof_degrades_service(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.ready()

    requirements.add(
        "prod",
        ("missing-finalization",),
        expected_generation=1,
        change_id="require-missing",
        reason="operator requires additional proof",
    )
    with pytest.raises(
        RuntimeError,
        match="durable recovery verification failed",
    ):
        restarted.new_session(
            make_intent(intent_id="blocked"),
            session_id="blocked",
        )
    assert restarted.state.phase is AIServicePhase.DEGRADED
    assert restarted.durable_recovery_ids == (
        finalization_id,
        "missing-finalization",
    )


def test_live_manifest_addition_of_verified_proof_is_adopted(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="first",
        intent_id="first-intent",
    )
    first_id = first.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(first_id,),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.ready()

    _, _, _, _, second = env.execute(
        session_id="second",
        intent_id="second-intent",
    )
    second_id = second.finalized.finalization.finalization_id
    requirements.add(
        "prod",
        (second_id,),
        expected_generation=1,
        change_id="require-second",
        reason="second terminal execution joined recovery set",
    )

    session = restarted.new_session(
        make_intent(intent_id="after-add"),
        session_id="after-add",
    )
    assert session.session_id == "after-add"
    assert restarted.state.phase is AIServicePhase.READY
    assert restarted.durable_recovery_ids == tuple(
        sorted((first_id, second_id))
    )
    assert (
        restarted.status()
        .durable_recovery_requirements["manifest"]["generation"]
        == 2
    )


def test_tampered_manifest_head_degrades_live_service(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.ready()

    key = requirements._head_key("prod")
    record = env.backend.get(
        requirements.namespace,
        key,
    )
    raw = dict(record.value)
    signature = dict(raw["signature"])
    signature["signature"] = "0" * 64
    raw["signature"] = signature
    env.backend.compare_and_swap(
        requirements.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )

    with pytest.raises(
        RuntimeError,
        match="requirement verification failed",
    ):
        restarted.new_session(
            make_intent(intent_id="tampered"),
            session_id="tampered",
        )
    assert restarted.state.phase is AIServicePhase.DEGRADED


def test_signed_old_manifest_replay_degrades_live_service(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    first = requirements.require("prod")
    requirements.add(
        "prod",
        ("missing-finalization",),
        expected_generation=1,
        change_id="generation-two",
        reason="advance manifest",
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.phase is AIServicePhase.FAILED

    # Restore a clean worker setup at generation two, then replace the head
    # value with the correctly signed generation-one artifact. CAS revision
    # fencing must reject this rollback even though the signature is valid.
    requirements.remove(
        "prod",
        ("missing-finalization",),
        expected_generation=2,
        change_id="generation-three",
        reason="remove missing proof after archive decision",
    )
    clean = restart_service_with_requirements(
        env,
        requirements,
    )
    clean.start()
    assert clean.state.ready()

    key = requirements._head_key("prod")
    record = env.backend.get(
        requirements.namespace,
        key,
    )
    env.backend.compare_and_swap(
        requirements.namespace,
        key,
        expected_revision=record.revision,
        value=first.to_dict(),
    )
    with pytest.raises(RuntimeError):
        clean.new_session(
            make_intent(intent_id="rollback"),
            session_id="rollback",
        )
    assert clean.state.phase is AIServicePhase.DEGRADED


def test_explicit_signed_removal_allows_clean_restart(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    requirements.add(
        "prod",
        ("missing-finalization",),
        expected_generation=1,
        change_id="temporary-proof",
        reason="require temporary proof",
    )
    failed = restart_service_with_requirements(
        env,
        requirements,
    )
    failed.start()
    assert failed.state.phase is AIServicePhase.FAILED

    requirements.remove(
        "prod",
        ("missing-finalization",),
        expected_generation=2,
        change_id="retire-temporary-proof",
        reason="explicit operator retirement after investigation",
    )
    clean = restart_service_with_requirements(
        env,
        requirements,
    )
    clean.start()
    assert clean.state.phase is AIServicePhase.READY
    assert clean.durable_recovery_ids == (finalization_id,)
    status = clean.status().to_dict()
    assert (
        status["durable_recovery_requirements"]["manifest"]["generation"]
        == 3
    )


def test_requirement_manifest_bound_runtime_without_runtime_guard_fails_start(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = DurableRecoveryRequirementStore(
        env.backend,
        ArtifactSigner(
            "recovery-requirements",
            b"m" * 32,
            clock=lambda: 20.0,
        ),
        namespace="recovery-requirements",
        clock=lambda: 20.0,
    )
    requirements.initialize(
        "prod",
        (finalization_id,),
        runtime_trust_digest=fp("runtime-bound"),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.phase is AIServicePhase.FAILED


def test_requirement_manifest_bound_release_without_release_guard_fails_start(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = DurableRecoveryRequirementStore(
        env.backend,
        ArtifactSigner(
            "recovery-requirements",
            b"m" * 32,
            clock=lambda: 20.0,
        ),
        namespace="recovery-requirements",
        clock=lambda: 20.0,
    )
    requirements.initialize(
        "prod",
        (finalization_id,),
        release_evidence_digest=fp("release-bound"),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.phase is AIServicePhase.FAILED


def test_service_rejects_static_ids_plus_signed_requirement_store(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(env)
    with pytest.raises(
        ValueError,
        match="cannot be combined",
    ):
        AIShellService(
            env.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            execution_attempts=env.attempts,
            worker_id="worker-static-conflict",
            durable_recovery_guard=recovery_requirement_guard(env),
            durable_recovery_ids=("static",),
            durable_recovery_requirement_store=requirements,
            durable_recovery_requirement_scope="prod",
        )


def test_service_requires_guard_for_requirement_store(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(env)
    with pytest.raises(
        ValueError,
        match="requires a durable recovery guard",
    ):
        AIShellService(
            env.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            execution_attempts=env.attempts,
            worker_id="worker-no-guard",
            durable_recovery_requirement_store=requirements,
            durable_recovery_requirement_scope="prod",
        )


def test_service_requires_store_for_requirement_scope(tmp_path):
    env = DurableEnvironment(tmp_path)
    with pytest.raises(
        ValueError,
        match="scope requires a store",
    ):
        AIShellService(
            env.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            execution_attempts=env.attempts,
            worker_id="worker-no-store",
            durable_recovery_guard=recovery_requirement_guard(env),
            durable_recovery_requirement_scope="prod",
        )


def test_manifest_empty_set_obeys_health_policy(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(env, ids=())
    strict = DurableRecoveryHealthPolicy(
        require_nonempty=True,
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
        policy=strict,
    )
    restarted.start()
    assert restarted.state.phase is AIServicePhase.FAILED


def test_manifest_generation_is_live_in_status_after_adoption(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="first",
        intent_id="first",
    )
    first_id = first.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(first_id,),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()

    _, _, _, _, second = env.execute(
        session_id="second",
        intent_id="second",
    )
    second_id = second.finalized.finalization.finalization_id
    requirements.add(
        "prod",
        (second_id,),
        expected_generation=1,
        change_id="second",
        reason="second verified finalization",
    )
    restarted.new_session(
        make_intent(intent_id="refresh"),
        session_id="refresh",
    )
    status = restarted.status().to_dict()
    requirement_status = status["durable_recovery_requirements"]
    assert requirement_status["manifest"]["generation"] == 2
    assert requirement_status["manifest"]["finalization_ids"] == list(
        sorted((first_id, second_id))
    )
    assert requirement_status["manifest_digest"] == (
        requirements.require("prod").manifest.digest
    )

def recovery_requirement_operator(env, requirements):
    return DurableRecoveryRequirementOperator(
        requirements,
        DurableSessionRecoveryVerifier(
            finalizations=env.finalizations,
            recovery_checkpoints=env.recovery,
            session_evidence=env.session_evidence,
            journal=DistributedAIDecisionJournal(
                env.backend,
                namespace="decision-journal",
            ),
            receipt_chain=DistributedReceiptChain(
                env.backend,
                namespace="receipts",
            ),
            execution_evidence=env.execution_evidence,
        ),
    )


def test_requirement_operator_allows_addition_of_missing_proof(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )

    plan = operator.require_plan(
        "prod",
        (finalization_id, "missing-proof"),
    )
    assert plan.allowed
    assert plan.additions == ("missing-proof",)
    assert plan.removals == ()
    assert plan.removal_checks == ()

    applied = operator.apply(
        plan,
        change_id="discover-missing",
        reason="new terminal execution requires recovery proof",
    )
    assert applied.manifest.finalization_ids == tuple(
        sorted((finalization_id, "missing-proof"))
    )


def test_requirement_operator_refuses_removal_of_incomplete_proof(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(
        env,
        ids=("missing-proof",),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.plan("prod", ())
    assert not plan.allowed
    assert plan.removals == ("missing-proof",)
    assert len(plan.removal_checks) == 1
    check = plan.removal_checks[0]
    assert check.status is DurableRecoveryStatus.INCOMPLETE
    assert not check.removable
    with pytest.raises(
        RecoveryRequirementOperatorError,
        match="may not be retired",
    ):
        operator.require_plan("prod", ())


def test_requirement_operator_allows_verified_removal(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )

    plan = operator.require_plan("prod", ())
    assert plan.allowed
    assert plan.removals == (finalization_id,)
    assert plan.removal_checks[0].status is DurableRecoveryStatus.VERIFIED
    assert plan.removal_checks[0].removable

    applied = operator.apply(
        plan,
        change_id="archive-proof",
        reason="verified proof moved to governed long-term archive",
    )
    assert applied.manifest.finalization_ids == ()
    assert applied.manifest.generation == 2


def test_requirement_operator_rechecks_proof_before_removal(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.require_plan("prod", ())
    assert plan.allowed

    record = env.backend.get(
        env.session_evidence.namespace,
        session.session_id,
    )
    env.backend.compare_and_swap(
        env.session_evidence.namespace,
        session.session_id,
        expected_revision=record.revision,
        value=replace(
            record.value,
            plan_fingerprint=fp("corrupted-after-plan"),
        ),
    )

    with pytest.raises(
        RecoveryRequirementOperatorError,
        match="may not be retired",
    ):
        operator.apply(
            plan,
            change_id="unsafe-retire",
            reason="must fail after evidence corruption",
        )
    assert requirements.require(
        "prod"
    ).manifest.finalization_ids == (finalization_id,)


def test_requirement_operator_fences_concurrent_manifest_change(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.require_plan(
        "prod",
        (finalization_id, "new-proof"),
    )

    requirements.add(
        "prod",
        ("other-proof",),
        expected_generation=1,
        change_id="concurrent",
        reason="another operator updated requirements",
    )
    with pytest.raises(
        RecoveryRequirementOperatorError,
        match="generation is stale",
    ):
        operator.apply(
            plan,
            change_id="lost-race",
            reason="must not overwrite concurrent change",
        )


def test_requirement_operator_rejects_no_change_apply(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.require_plan(
        "prod",
        (finalization_id,),
    )
    assert plan.allowed
    assert not plan.changed
    with pytest.raises(
        RecoveryRequirementOperatorError,
        match="contains no change",
    ):
        operator.apply(
            plan,
            change_id="noop",
            reason="noop",
        )


def test_requirement_operator_plan_digest_is_stable(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    first = operator.plan(
        "prod",
        (finalization_id, "new-proof"),
    )
    second = operator.plan(
        "prod",
        ("new-proof", finalization_id),
    )
    assert first == second
    assert first.digest == second.digest


def test_requirement_operator_plan_serializes_removal_proof(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.require_plan("prod", ())
    data = plan.to_dict()
    assert data["allowed"] is True
    assert data["changed"] is True
    assert data["removals"] == [finalization_id]
    assert data["removal_checks"][0]["status"] == "verified"
    assert len(data["removal_checks"][0]["report_digest"]) == 64
    assert data["digest"] == plan.digest


def test_requirement_operator_missing_scope_is_explicit_error(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(
        env,
        scope="prod",
        ids=(),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    with pytest.raises(
        RecoveryRequirementOperatorError,
        match="not initialized",
    ):
        operator.plan("missing", ())


def test_requirement_operator_rejects_duplicate_desired_ids(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(env)
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    with pytest.raises(ValueError, match="duplicate"):
        operator.plan(
            "prod",
            ("same", "same"),
        )


def test_requirement_operator_add_then_service_adopts_new_requirement(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="first",
        intent_id="first",
    )
    first_id = first.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(first_id,),
    )
    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.ready()

    _, _, _, _, second = env.execute(
        session_id="second",
        intent_id="second",
    )
    second_id = second.finalized.finalization.finalization_id
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.require_plan(
        "prod",
        (first_id, second_id),
    )
    operator.apply(
        plan,
        change_id="require-second",
        reason="second execution is now governed",
    )

    restarted.new_session(
        make_intent(intent_id="after-operator"),
        session_id="after-operator",
    )
    assert restarted.state.ready()
    assert restarted.durable_recovery_ids == tuple(
        sorted((first_id, second_id))
    )


def test_requirement_operator_removal_then_clean_restart(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.require_plan("prod", ())
    operator.apply(
        plan,
        change_id="retire-finalization",
        reason="verified evidence retention lifecycle completed",
    )

    restarted = restart_service_with_requirements(
        env,
        requirements,
    )
    restarted.start()
    assert restarted.state.ready()
    assert restarted.durable_recovery_ids == ()


def test_requirement_operator_cannot_retire_manual_review_evidence(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    finalization_id = result.finalized.finalization.finalization_id
    requirements = recovery_requirement_store(
        env,
        ids=(finalization_id,),
    )

    record = env.backend.get(
        env.session_evidence.namespace,
        session.session_id,
    )
    env.backend.compare_and_swap(
        env.session_evidence.namespace,
        session.session_id,
        expected_revision=record.revision,
        value=replace(
            record.value,
            plan_fingerprint=fp("tampered"),
        ),
    )
    operator = recovery_requirement_operator(
        env,
        requirements,
    )
    plan = operator.plan("prod", ())
    assert not plan.allowed
    assert (
        plan.removal_checks[0].status
        is DurableRecoveryStatus.MANUAL_REVIEW
    )
    assert not plan.removal_checks[0].removable


def test_requirement_operator_constructor_types(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(env)
    verifier = durable_verifier(env)
    with pytest.raises(TypeError, match="store"):
        DurableRecoveryRequirementOperator(
            object(),
            verifier,
        )
    with pytest.raises(TypeError, match="verifier"):
        DurableRecoveryRequirementOperator(
            requirements,
            object(),
        )

class ForgetfulDurableChain:
    """Delegate current-chain operations while hiding selected historical roots."""

    def __init__(self, delegate, forgotten_roots):
        self.delegate = delegate
        self.forgotten_roots = set(forgotten_roots)

    def head(self):
        return self.delegate.head()

    def verify(self):
        return self.delegate.verify()

    def snapshot(self):
        return self.delegate.snapshot()

    def root_hash(self):
        return self.delegate.root_hash()

    def length(self):
        return self.delegate.length()

    def snapshot_at(self, root_hash):
        if root_hash in self.forgotten_roots:
            raise KeyError(root_hash)
        return self.delegate.snapshot_at(root_hash)

    def verify_root(self, root_hash):
        if root_hash in self.forgotten_roots:
            return False
        return self.delegate.verify_root(root_hash)

    def root_is_ancestor(self, root_hash):
        if root_hash in self.forgotten_roots:
            return False
        return self.delegate.root_is_ancestor(root_hash)


def durable_archive_repository(env):
    checkpoints = DurableChainCheckpointStore(
        env.backend,
        ArtifactSigner(
            "archive-checkpoint",
            b"c" * 32,
            clock=lambda: 100.0,
        ),
        namespace="archive-checkpoints",
        clock=lambda: 100.0,
    )
    signer = ArtifactSigner(
        "archive-payload",
        b"a" * 32,
        clock=lambda: 200.0,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        signer,
        clock=lambda: 200.0,
    )
    repository = DurableArchiveRepository(
        env.backend,
        checkpoints,
        signer,
        namespace="archive-payloads",
        clock=lambda: 300.0,
    )
    return checkpoints, builder, repository


def archive_current_durable_chains(env):
    checkpoints, builder, repository = (
        durable_archive_repository(env)
    )
    journal_checkpoint = checkpoints.publish(
        "decision-journal",
        env.journal,
    )
    journal_archive = builder.build(
        journal_checkpoint,
        env.journal,
    )
    repository.put(
        journal_archive,
        journal_checkpoint,
        env.journal,
    )

    receipt_checkpoint = checkpoints.publish(
        "receipts",
        env.receipts,
    )
    receipt_archive = builder.build(
        receipt_checkpoint,
        env.receipts,
    )
    repository.put(
        receipt_archive,
        receipt_checkpoint,
        env.receipts,
    )
    return (
        checkpoints,
        builder,
        repository,
        journal_archive,
        receipt_archive,
    )


def archive_backed_verifier(
    env,
    repository,
    *,
    journal_roots=(),
    receipt_roots=(),
):
    return DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=ForgetfulDurableChain(
            env.journal,
            journal_roots,
        ),
        receipt_chain=ForgetfulDurableChain(
            env.receipts,
            receipt_roots,
        ),
        execution_evidence=env.execution_evidence,
        journal_archive=repository,
        journal_chain_id="decision-journal",
        receipt_archive=repository,
        receipt_chain_id="receipts",
    )


def test_archive_backed_recovery_survives_forgotten_hot_roots(tmp_path):
    env = DurableEnvironment(tmp_path)
    first_session, _, _, _, first = env.execute(
        session_id="archive-first",
        intent_id="archive-first",
    )
    first_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root

    _, _, repository, _, _ = archive_current_durable_chains(env)

    env.execute(
        session_id="archive-second",
        intent_id="archive-second",
    )
    assert env.journal.root_hash() != journal_root
    assert env.receipts.root_hash() != receipt_root

    verifier = archive_backed_verifier(
        env,
        repository,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    )
    report = verifier.require_verified(first_id)
    assert report.ok
    assert report.session_id == first_session.session_id
    assert report.journal_root == journal_root
    assert report.receipt_root == receipt_root
    assert (
        report.session_integrity_digest
        == first.finalized.session_integrity.digest
    )


def test_recovery_without_archive_fails_when_hot_roots_are_forgotten(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="no-archive-first",
        intent_id="no-archive-first",
    )
    finalization_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    env.execute(
        session_id="no-archive-second",
        intent_id="no-archive-second",
    )

    verifier = DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=ForgetfulDurableChain(
            env.journal,
            (journal_root,),
        ),
        receipt_chain=ForgetfulDurableChain(
            env.receipts,
            (receipt_root,),
        ),
        execution_evidence=env.execution_evidence,
    )
    report = verifier.verify(finalization_id)
    assert (
        report.status
        is DurableRecoveryStatus.MANUAL_REVIEW
    )
    assert any(
        finding.code.startswith("session_journal")
        or finding.code.startswith("session_integrity")
        for finding in report.findings
    )


def test_archive_backed_health_guard_allows_verified_historical_execution(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="health-archive-first",
        intent_id="health-archive-first",
    )
    finalization_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    _, _, repository, _, _ = archive_current_durable_chains(env)
    env.execute(
        session_id="health-archive-second",
        intent_id="health-archive-second",
    )

    verifier = archive_backed_verifier(
        env,
        repository,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    )
    guard = DurableRecoveryHealthGuard(
        verifier,
        DurableRecoveryHealthPolicy(
            require_nonempty=True,
            minimum_verified=1,
            max_incomplete=0,
            max_finalizations=16,
        ),
    )
    health = guard.require((finalization_id,))
    assert health.allowed
    assert health.verified == 1
    assert health.manual_review == 0


def test_archive_backed_health_guard_denies_tampered_archived_journal(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="tamper-archive-first",
        intent_id="tamper-archive-first",
    )
    finalization_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    _, _, repository, _, _ = archive_current_durable_chains(env)
    env.execute(
        session_id="tamper-archive-second",
        intent_id="tamper-archive-second",
    )

    archived_event = repository.snapshot_at(
        "decision-journal",
        journal_root,
    )[-1]
    node_key = repository._node_key(
        "decision-journal",
        archived_event.event_hash,
    )
    record = env.backend.get(
        repository.namespace,
        node_key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered archive event"
    raw["payload"] = payload
    env.backend.compare_and_swap(
        repository.namespace,
        node_key,
        expected_revision=record.revision,
        value=raw,
    )

    verifier = archive_backed_verifier(
        env,
        repository,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    )
    report = verifier.verify(finalization_id)
    assert (
        report.status
        is DurableRecoveryStatus.MANUAL_REVIEW
    )


def test_archive_backed_health_guard_denies_tampered_archived_receipt(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="tamper-receipt-first",
        intent_id="tamper-receipt-first",
    )
    finalization_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    _, _, repository, _, _ = archive_current_durable_chains(env)
    env.execute(
        session_id="tamper-receipt-second",
        intent_id="tamper-receipt-second",
    )

    archived_receipt = repository.snapshot_at(
        "receipts",
        receipt_root,
    )[-1]
    node_key = repository._node_key(
        "receipts",
        archived_receipt.receipt_hash,
    )
    record = env.backend.get(
        repository.namespace,
        node_key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    receipt_payload = dict(payload["receipt"])
    receipt_payload["stdout_bytes"] += 1
    payload["receipt"] = receipt_payload
    raw["payload"] = payload
    env.backend.compare_and_swap(
        repository.namespace,
        node_key,
        expected_revision=record.revision,
        value=raw,
    )

    verifier = archive_backed_verifier(
        env,
        repository,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    )
    report = verifier.verify(finalization_id)
    assert (
        report.status
        is DurableRecoveryStatus.MANUAL_REVIEW
    )


def test_archive_backed_recovery_uses_fresh_repository_reader(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="fresh-archive-first",
        intent_id="fresh-archive-first",
    )
    finalization_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    checkpoints, _, repository, _, _ = archive_current_durable_chains(env)
    env.execute(
        session_id="fresh-archive-second",
        intent_id="fresh-archive-second",
    )

    fresh = DurableArchiveRepository(
        env.backend,
        checkpoints,
        ArtifactSigner(
            "archive-payload",
            b"a" * 32,
            clock=lambda: 999.0,
        ),
        namespace=repository.namespace,
        clock=lambda: 999.0,
    )
    report = archive_backed_verifier(
        env,
        fresh,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    ).require_verified(finalization_id)
    assert report.ok


def test_archive_backed_recovery_reconstructs_original_session_journal_only(tmp_path):
    env = DurableEnvironment(tmp_path)
    first_session, _, _, _, first = env.execute(
        session_id="journal-isolation-first",
        intent_id="journal-isolation-first",
    )
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    _, _, repository, _, _ = archive_current_durable_chains(env)
    env.execute(
        session_id="journal-isolation-second",
        intent_id="journal-isolation-second",
    )

    verifier = archive_backed_verifier(
        env,
        repository,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    )
    journal_evidence = verifier._session_journal(
        first_session.session_id,
        journal_root,
    )
    assert journal_evidence.events
    archived_prefix = repository.snapshot_at(
        "decision-journal",
        journal_root,
    )
    expected = tuple(
        event
        for event in archived_prefix
        if event.session_id == first_session.session_id
    )
    assert tuple(
        item.event_hash
        for item in journal_evidence.events
    ) == tuple(
        item.event_hash
        for item in expected
    )


def test_archive_backed_recovery_constructor_requires_chain_id_with_archive(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, repository, _, _ = archive_current_durable_chains(env)
    with pytest.raises(
        ValueError,
        match="journal_archive",
    ):
        DurableSessionRecoveryVerifier(
            finalizations=env.finalizations,
            recovery_checkpoints=env.recovery,
            session_evidence=env.session_evidence,
            journal=env.journal,
            receipt_chain=env.receipts,
            execution_evidence=env.execution_evidence,
            journal_archive=repository,
        )
    with pytest.raises(
        ValueError,
        match="receipt_archive",
    ):
        DurableSessionRecoveryVerifier(
            finalizations=env.finalizations,
            recovery_checkpoints=env.recovery,
            session_evidence=env.session_evidence,
            journal=env.journal,
            receipt_chain=env.receipts,
            execution_evidence=env.execution_evidence,
            receipt_chain_id="receipts",
        )


def test_archive_backed_recovery_constructor_validates_repository_type(tmp_path):
    env = DurableEnvironment(tmp_path)
    with pytest.raises(
        TypeError,
        match="journal_archive",
    ):
        DurableSessionRecoveryVerifier(
            finalizations=env.finalizations,
            recovery_checkpoints=env.recovery,
            session_evidence=env.session_evidence,
            journal=env.journal,
            receipt_chain=env.receipts,
            execution_evidence=env.execution_evidence,
            journal_archive=object(),
            journal_chain_id="decision-journal",
        )
    with pytest.raises(
        TypeError,
        match="receipt_archive",
    ):
        DurableSessionRecoveryVerifier(
            finalizations=env.finalizations,
            recovery_checkpoints=env.recovery,
            session_evidence=env.session_evidence,
            journal=env.journal,
            receipt_chain=env.receipts,
            execution_evidence=env.execution_evidence,
            receipt_archive=object(),
            receipt_chain_id="receipts",
        )


def test_archive_repository_keeps_first_finalization_verifiable_after_three_later_runs(
    tmp_path,
):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="long-lived-first",
        intent_id="long-lived-first",
    )
    finalization_id = first.finalized.finalization.finalization_id
    journal_root = first.finalized.checkpoint.journal_root
    receipt_root = first.finalized.checkpoint.receipt_root
    _, _, repository, _, _ = archive_current_durable_chains(env)

    for index in range(3):
        env.execute(
            session_id=f"long-lived-later-{index}",
            intent_id=f"long-lived-later-{index}",
        )

    report = archive_backed_verifier(
        env,
        repository,
        journal_roots=(journal_root,),
        receipt_roots=(receipt_root,),
    ).require_verified(finalization_id)
    assert report.ok
    assert report.journal_root == journal_root
    assert report.receipt_root == receipt_root


def test_archive_repository_can_add_later_prefix_without_breaking_first_recovery(
    tmp_path,
):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, first = env.execute(
        session_id="multi-archive-first",
        intent_id="multi-archive-first",
    )
    first_id = first.finalized.finalization.finalization_id
    first_journal_root = first.finalized.checkpoint.journal_root
    first_receipt_root = first.finalized.checkpoint.receipt_root
    checkpoints, builder, repository, _, _ = (
        archive_current_durable_chains(env)
    )

    _, _, _, _, second = env.execute(
        session_id="multi-archive-second",
        intent_id="multi-archive-second",
    )
    second_journal_checkpoint = checkpoints.publish(
        "decision-journal",
        env.journal,
    )
    second_journal_archive = builder.build(
        second_journal_checkpoint,
        env.journal,
    )
    repository.put(
        second_journal_archive,
        second_journal_checkpoint,
        env.journal,
    )
    second_receipt_checkpoint = checkpoints.publish(
        "receipts",
        env.receipts,
    )
    second_receipt_archive = builder.build(
        second_receipt_checkpoint,
        env.receipts,
    )
    repository.put(
        second_receipt_archive,
        second_receipt_checkpoint,
        env.receipts,
    )

    second_id = second.finalized.finalization.finalization_id
    second_journal_root = second.finalized.checkpoint.journal_root
    second_receipt_root = second.finalized.checkpoint.receipt_root

    first_report = archive_backed_verifier(
        env,
        repository,
        journal_roots=(first_journal_root,),
        receipt_roots=(first_receipt_root,),
    ).require_verified(first_id)
    second_report = archive_backed_verifier(
        env,
        repository,
        journal_roots=(second_journal_root,),
        receipt_roots=(second_receipt_root,),
    ).require_verified(second_id)
    assert first_report.ok
    assert second_report.ok

def obligation_runtime(env, *, namespace="execution-obligations"):
    requirements = DurableRecoveryRequirementStore(
        env.backend,
        ArtifactSigner(
            "obligation-requirements",
            b"o" * 32,
            clock=lambda: 30.0,
        ),
        namespace=f"{namespace}-requirements",
        clock=lambda: 30.0,
    )
    if requirements.current("prod") is None:
        requirements.initialize("prod", ())
    obligations = AIExecutionObligationStore(
        env.backend,
        namespace=namespace,
        clock=lambda: 30.0,
    )
    recovery = AIExecutionObligationRecoveryInspector(
        obligations,
        env.attempts,
        env.finalizations,
        DurableSessionRecoveryVerifier(
            finalizations=env.finalizations,
            recovery_checkpoints=env.recovery,
            session_evidence=env.session_evidence,
            journal=DistributedAIDecisionJournal(
                env.backend,
                namespace="decision-journal",
            ),
            receipt_chain=DistributedReceiptChain(
                env.backend,
                namespace="receipts",
            ),
            execution_evidence=env.execution_evidence,
        ),
    )
    service = AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        execution_obligation_recovery=recovery,
        worker_id="worker-obligation",
        durable_recovery_guard=DurableRecoveryHealthGuard(
            recovery.durable_recovery,
            DurableRecoveryHealthPolicy(),
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope="prod",
    )
    return service, obligations, recovery, requirements


def execute_with_obligation_service(
    env,
    service,
    *,
    session_id="obligation-session",
    intent_id="obligation-intent",
    finalize=True,
):
    session = service.new_session(
        make_intent(intent_id=intent_id),
        session_id=session_id,
    )
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"z" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    if finalize:
        result = service.execute_sealed_and_finalize(
            session,
            review,
            context=ExecutionContext(
                f"context-{session_id}",
                principal="alice",
            ),
            seal=seal,
            seal_registry=registry,
            finalizer=env.finalizer,
        )
    else:
        result = service.execute_sealed(
            session,
            review,
            context=ExecutionContext(
                f"context-{session_id}",
                principal="alice",
            ),
            seal=seal,
            seal_registry=registry,
        )
    return session, review, seal, registry, result


def test_obligation_service_registers_before_process_and_finalizes_after_evidence(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, obligations, recovery, requirements = obligation_runtime(env)
    service.start()
    assert service.state.ready()

    session, _, seal, _, result = execute_with_obligation_service(
        env,
        service,
    )
    assert result.ok

    stored = obligations.current(seal.seal_id)
    assert stored is not None
    obligation = stored.obligation
    assert obligation.state is ExecutionObligationState.FINALIZED
    assert obligation.session_id == session.session_id
    assert obligation.attempt_state == "succeeded"
    assert obligation.terminal_evidence_digest == result.execution.provenance.digest
    assert (
        obligation.finalization_id
        == result.finalized.finalization.finalization_id
    )
    assert recovery.inspect(seal.seal_id).disposition is (
        ExecutionObligationRecoveryDisposition.VERIFIED_FINALIZED
    )
    assert requirements.require("prod").manifest.finalization_ids == (
        result.finalized.finalization.finalization_id,
    )


def test_obligation_service_status_exposes_terminal_summary(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, _, _, _ = obligation_runtime(env)
    service.start()
    _, _, _, _, result = execute_with_obligation_service(
        env,
        service,
    )
    status = service.status().to_dict()
    summary = status["execution_obligations"]
    assert summary["allowed"] is True
    assert summary["verified_finalized"] == 1
    assert summary["retired"] == 0
    assert summary["unresolved"] == 0
    assert summary["finalization_ids"] == [
        result.finalized.finalization.finalization_id
    ]


def test_plain_sealed_execution_leaves_terminal_unfinalized_obligation(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, obligations, recovery, _ = obligation_runtime(env)
    service.start()
    _, _, seal, _, execution_tuple = execute_with_obligation_service(
        env,
        service,
        finalize=False,
    )
    execution = execution_tuple[0]
    assert execution.ok

    stored = obligations.current(seal.seal_id)
    assert stored.obligation.state is ExecutionObligationState.ATTEMPT_BOUND
    assert stored.obligation.attempt_state == "succeeded"
    report = recovery.inspect(seal.seal_id)
    assert report.disposition is (
        ExecutionObligationRecoveryDisposition.TERMINAL_UNFINALIZED
    )


def test_terminal_unfinalized_obligation_blocks_next_admission(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, _, _, _ = obligation_runtime(env)
    service.start()
    execute_with_obligation_service(
        env,
        service,
        finalize=False,
    )
    with pytest.raises(
        RuntimeError,
        match="execution obligation recovery failed",
    ):
        service.new_session(
            make_intent(intent_id="blocked"),
            session_id="blocked",
        )
    assert service.state.phase is AIServicePhase.DEGRADED


def test_restart_blocks_terminal_unfinalized_obligation(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, _, _, requirements = obligation_runtime(env)
    service.start()
    execute_with_obligation_service(
        env,
        service,
        finalize=False,
    )

    restarted, _, _, _ = obligation_runtime(env)
    # Reuse the exact signed requirement authority namespace produced above.
    restarted.durable_recovery_requirement_store = requirements
    restarted.start()
    assert restarted.state.phase is AIServicePhase.FAILED
    assert (
        "execution obligation"
        in restarted.state.reason.lower()
    )


def test_manual_finalization_after_terminal_execution_is_discovered_on_restart(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, obligations, recovery, requirements = obligation_runtime(env)
    service.start()
    session, review, seal, _, execution_tuple = execute_with_obligation_service(
        env,
        service,
        finalize=False,
    )
    execution = execution_tuple[0]
    terminal_attempt = env.attempts.current(seal.seal_id).attempt
    finalized = env.finalizer.finalize(
        session,
        execution,
        policy_fingerprint=service.governance.current_policy().fingerprint,
        tool_catalog_digest=service.orchestrator.planner.catalog.digest,
        effect_digest=service.orchestrator.compiler.effects.digest,
        execution_seal_id=seal.seal_id,
        execution_attempt=terminal_attempt,
    )
    assert finalized.finalization is not None
    assert obligations.current(
        seal.seal_id
    ).obligation.state is ExecutionObligationState.ATTEMPT_BOUND
    assert recovery.inspect(seal.seal_id).disposition is (
        ExecutionObligationRecoveryDisposition.FINALIZATION_DISCOVERED
    )

    restarted = AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        execution_obligation_recovery=recovery,
        worker_id="worker-obligation-restart",
        durable_recovery_guard=DurableRecoveryHealthGuard(
            recovery.durable_recovery,
            DurableRecoveryHealthPolicy(),
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope="prod",
    )
    restarted.start()
    assert restarted.state.ready()
    assert obligations.current(
        seal.seal_id
    ).obligation.state is ExecutionObligationState.FINALIZED
    assert (
        finalized.finalization.finalization_id
        in requirements.require("prod").manifest.finalization_ids
    )


def test_preboundary_catalog_only_crash_is_retired_on_restart(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, obligations, recovery, requirements = obligation_runtime(env)
    entry = obligations._append_catalog(
        obligation_id="catalog-only",
        session_id="catalog-session",
        principal="alice",
        plan_fingerprint=fp("catalog-plan"),
        execution_seal_id="catalog-only",
        runtime_trust_digest="",
        release_evidence_digest="",
    )
    assert entry.obligation_id == "catalog-only"
    assert env.backend.get(
        obligations.namespace,
        obligations._state_key("catalog-only"),
    ) is None

    restarted = AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        execution_obligation_recovery=recovery,
        worker_id="worker-catalog-restart",
        durable_recovery_guard=DurableRecoveryHealthGuard(
            recovery.durable_recovery,
            DurableRecoveryHealthPolicy(),
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope="prod",
    )
    restarted.start()
    assert restarted.state.ready()
    recovered = obligations.current("catalog-only")
    assert recovered.obligation.state is ExecutionObligationState.RETIRED
    assert recovered.obligation.retirement_proof_digest


def test_registered_before_attempt_is_retired_on_restart(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, obligations, recovery, requirements = obligation_runtime(env)
    obligations.register(
        obligation_id="registered-only",
        session_id="registered-session",
        principal="alice",
        plan_fingerprint=fp("registered-plan"),
        execution_seal_id="registered-only",
    )
    restarted = AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        execution_obligation_recovery=recovery,
        worker_id="worker-registered-restart",
        durable_recovery_guard=DurableRecoveryHealthGuard(
            recovery.durable_recovery,
            DurableRecoveryHealthPolicy(),
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope="prod",
    )
    restarted.start()
    assert restarted.state.ready()
    assert obligations.current(
        "registered-only"
    ).obligation.state is ExecutionObligationState.RETIRED


def test_authorized_attempt_is_abandoned_then_retired_on_restart(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, obligations, recovery, requirements = obligation_runtime(env)
    obligations.register(
        obligation_id="authorized-only",
        session_id="authorized-session",
        principal="alice",
        plan_fingerprint=fp("authorized-plan"),
        execution_seal_id="authorized-only",
    )
    stored_attempt = env.attempts.reserve(
        attempt_id="authorized-only",
        session_id="authorized-session",
        principal="alice",
        worker_id="worker-obligation",
        plan_fingerprint=fp("authorized-plan"),
        execution_seal_id="authorized-only",
    )
    obligations.sync_attempt(
        "authorized-only",
        stored_attempt.attempt,
    )

    restarted = AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        execution_obligation_recovery=recovery,
        worker_id="worker-authorized-restart",
        durable_recovery_guard=DurableRecoveryHealthGuard(
            recovery.durable_recovery,
            DurableRecoveryHealthPolicy(),
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope="prod",
    )
    restarted.start()
    assert restarted.state.ready()
    assert env.attempts.current(
        "authorized-only"
    ).attempt.state is ExecutionAttemptState.ABANDONED
    assert obligations.current(
        "authorized-only"
    ).obligation.state is ExecutionObligationState.RETIRED


def test_boundary_entered_attempt_blocks_restart_and_is_never_replayed(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, obligations, recovery, requirements = obligation_runtime(env)
    obligations.register(
        obligation_id="boundary",
        session_id="boundary-session",
        principal="alice",
        plan_fingerprint=fp("boundary-plan"),
        execution_seal_id="boundary",
    )
    reserved = env.attempts.reserve(
        attempt_id="boundary",
        session_id="boundary-session",
        principal="alice",
        worker_id="worker-obligation",
        plan_fingerprint=fp("boundary-plan"),
        execution_seal_id="boundary",
    )
    boundary = env.attempts.enter_boundary(
        reserved.attempt
    ).attempt
    obligations.sync_attempt("boundary", boundary)

    restarted = AIShellService(
        env.orchestrator,
        env.service.diagnostics,
        env.service.governance,
        execution_attempts=env.attempts,
        execution_obligation_recovery=recovery,
        worker_id="worker-boundary-restart",
        durable_recovery_guard=DurableRecoveryHealthGuard(
            recovery.durable_recovery,
            DurableRecoveryHealthPolicy(),
        ),
        durable_recovery_requirement_store=requirements,
        durable_recovery_requirement_scope="prod",
    )
    receipt_count = env.receipts.length()
    restarted.start()
    assert restarted.state.phase is AIServicePhase.FAILED
    assert env.attempts.current(
        "boundary"
    ).attempt.state is ExecutionAttemptState.BOUNDARY_ENTERED
    assert obligations.current(
        "boundary"
    ).obligation.state is ExecutionObligationState.ATTEMPT_BOUND
    assert env.receipts.length() == receipt_count


def test_consumed_seal_failure_leaves_safe_registered_obligation(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, obligations, recovery, _ = obligation_runtime(env)
    service.start()

    session = service.new_session(
        make_intent(intent_id="consume-failure"),
        session_id="consume-failure",
    )
    review, _ = service.review(session)
    authority = ExecutionSealAuthority(b"x" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = service.seal_review(
        session,
        review,
        principal="alice",
        authority=authority,
    )
    # Consume once before service execution. The service will catalog the
    # obligation, then its consume attempt must fail before any child starts.
    registry.consume(
        seal,
        principal="alice",
        session_id=session.session_id,
        plan_pin=service._pins[session.session_id],
    )
    before = env.receipts.length()
    with pytest.raises(Exception):
        service.execute_sealed(
            session,
            review,
            context=ExecutionContext(
                "consume-failure-context",
                principal="alice",
            ),
            seal=seal,
            seal_registry=registry,
        )
    assert env.receipts.length() == before
    obligation = obligations.current(seal.seal_id).obligation
    assert obligation.state is ExecutionObligationState.REGISTERED
    assert recovery.inspect(seal.seal_id).safe_to_replan


def test_safe_registered_obligation_is_retired_before_next_session(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, obligations, _, _ = obligation_runtime(env)
    service.start()
    obligations.register(
        obligation_id="safe-orphan",
        session_id="safe-orphan-session",
        principal="alice",
        plan_fingerprint=fp("safe-orphan-plan"),
        execution_seal_id="safe-orphan",
    )
    session = service.new_session(
        make_intent(intent_id="after-safe-orphan"),
        session_id="after-safe-orphan",
    )
    assert session.session_id == "after-safe-orphan"
    assert obligations.current(
        "safe-orphan"
    ).obligation.state is ExecutionObligationState.RETIRED
    assert service.state.ready()


def test_obligation_finalization_auto_enrolls_signed_requirement_manifest(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, _, _, requirements = obligation_runtime(env)
    service.start()
    _, _, _, _, result = execute_with_obligation_service(
        env,
        service,
    )
    finalization_id = result.finalized.finalization.finalization_id
    manifest = requirements.require("prod").manifest
    assert manifest.generation == 2
    assert manifest.finalization_ids == (finalization_id,)
    assert manifest.change_id.startswith("auto-finalization-")


def test_multiple_obligation_finalizations_accumulate_required_proofs(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, obligations, recovery, requirements = obligation_runtime(env)
    service.start()
    _, _, seal_one, _, first = execute_with_obligation_service(
        env,
        service,
        session_id="obligation-one",
        intent_id="obligation-one-intent",
    )
    _, _, seal_two, _, second = execute_with_obligation_service(
        env,
        service,
        session_id="obligation-two",
        intent_id="obligation-two-intent",
    )
    first_id = first.finalized.finalization.finalization_id
    second_id = second.finalized.finalization.finalization_id
    assert requirements.require("prod").manifest.finalization_ids == tuple(
        sorted((first_id, second_id))
    )
    assert obligations.current(
        seal_one.seal_id
    ).obligation.state is ExecutionObligationState.FINALIZED
    assert obligations.current(
        seal_two.seal_id
    ).obligation.state is ExecutionObligationState.FINALIZED
    summary = recovery.summary()
    assert summary.allowed
    assert summary.verified_finalized == 2
    assert summary.finalization_ids == tuple(
        sorted((first_id, second_id))
    )


def test_requirement_enrollment_is_idempotent_on_repeated_obligation_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    service, _, recovery, requirements = obligation_runtime(env)
    service.start()
    _, _, _, _, result = execute_with_obligation_service(
        env,
        service,
    )
    first_generation = requirements.require("prod").manifest.generation
    assert first_generation == 2
    service._recover_execution_obligations()
    service._recover_execution_obligations()
    assert requirements.require("prod").manifest.generation == first_generation
    assert recovery.summary().allowed


def test_obligation_constructor_requires_same_attempt_store(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, recovery, requirements = obligation_runtime(env)
    other_attempts = AIExecutionAttemptStore(
        env.backend,
        namespace="other-attempts",
    )
    with pytest.raises(
        ValueError,
        match="must use configured execution attempt store",
    ):
        AIShellService(
            env.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            execution_attempts=other_attempts,
            execution_obligation_recovery=recovery,
            worker_id="worker-mismatch",
            durable_recovery_guard=DurableRecoveryHealthGuard(
                recovery.durable_recovery,
                DurableRecoveryHealthPolicy(),
            ),
            durable_recovery_requirement_store=requirements,
            durable_recovery_requirement_scope="prod",
        )


def test_obligation_recovery_requires_attempt_store(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, recovery, requirements = obligation_runtime(env)
    with pytest.raises(
        ValueError,
        match="requires execution attempts",
    ):
        AIShellService(
            env.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            execution_obligation_recovery=recovery,
            worker_id="worker-no-attempts",
            durable_recovery_guard=DurableRecoveryHealthGuard(
                recovery.durable_recovery,
                DurableRecoveryHealthPolicy(),
            ),
            durable_recovery_requirement_store=requirements,
            durable_recovery_requirement_scope="prod",
        )


def test_obligation_recovery_type_validation(tmp_path):
    env = DurableEnvironment(tmp_path)
    requirements = recovery_requirement_store(env)
    with pytest.raises(TypeError, match="execution_obligation_recovery"):
        AIShellService(
            env.orchestrator,
            env.service.diagnostics,
            env.service.governance,
            execution_attempts=env.attempts,
            execution_obligation_recovery=object(),
            worker_id="worker-bad-obligation-recovery",
            durable_recovery_guard=recovery_requirement_guard(env),
            durable_recovery_requirement_store=requirements,
            durable_recovery_requirement_scope="prod",
        )

class NoFullScanJournal:
    """Expose exact lookup APIs while making any whole-chain scan fatal."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.snapshot_calls = 0
        self.snapshot_at_calls = 0
        self.verify_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        raise AssertionError(
            "full journal snapshot is forbidden in bounded recovery"
        )

    def snapshot_at(self, root_hash):
        self.snapshot_at_calls += 1
        raise AssertionError(
            "historical journal snapshot is forbidden in bounded recovery"
        )

    def verify(self):
        self.verify_calls += 1
        raise AssertionError(
            "whole journal verification is forbidden in bounded recovery"
        )

    def root_hash(self):
        return self.delegate.root_hash()

    def get_by_sequence(
        self,
        sequence,
        *,
        repair_missing=True,
    ):
        return self.delegate.get_by_sequence(
            sequence,
            repair_missing=repair_missing,
        )

    def sequence_for_root(self, root_hash):
        return self.delegate.sequence_for_root(
            root_hash
        )


class NoFullScanReceipts:
    """Expose exact receipt indexes while rejecting whole-chain traversal."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.snapshot_calls = 0
        self.snapshot_at_calls = 0
        self.verify_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        raise AssertionError(
            "full receipt snapshot is forbidden in bounded recovery"
        )

    def snapshot_at(self, root_hash):
        self.snapshot_at_calls += 1
        raise AssertionError(
            "historical receipt snapshot is forbidden in bounded recovery"
        )

    def verify(self):
        self.verify_calls += 1
        raise AssertionError(
            "whole receipt verification is forbidden in bounded recovery"
        )

    def root_hash(self):
        return self.delegate.root_hash()

    def get_by_sequence(
        self,
        sequence,
        *,
        repair_missing=True,
    ):
        return self.delegate.get_by_sequence(
            sequence,
            repair_missing=repair_missing,
        )

    def sequence_for_root(self, root_hash):
        return self.delegate.sequence_for_root(
            root_hash
        )

    def find_by_receipt_id(
        self,
        receipt_id,
        *,
        verify_chain=True,
    ):
        return self.delegate.find_by_receipt_id(
            receipt_id,
            verify_chain=verify_chain,
        )


def bounded_recovery_proof_runtime(env):
    checkpoints = DurableChainCheckpointStore(
        env.backend,
        ArtifactSigner(
            "bounded-checkpoints",
            b"c" * 32,
            clock=lambda: 100.0,
        ),
        namespace="bounded-checkpoints",
        max_checkpoints=1000,
        clock=lambda: 100.0,
    )
    proof_authority = DurableHistoricalProofAuthority(
        checkpoints,
        ArtifactSigner(
            "bounded-proofs",
            b"p" * 32,
            clock=lambda: 200.0,
        ),
        max_window_items=256,
        clock=lambda: 200.0,
    )
    proof_store = DurableHistoricalProofStore(
        env.backend,
        namespace="bounded-proofs",
    )
    proof_operator = DurableProofWindowOperator(
        proof_authority,
        proof_store,
        {
            "journal": env.journal,
            "receipts": env.receipts,
        },
        policy=DurableProofWindowPolicy(
            max_targets=32,
        ),
    )
    return (
        checkpoints,
        proof_authority,
        proof_store,
        proof_operator,
    )


def seed_and_checkpoint_durable_chains(env, checkpoints):
    env.journal.append(
        "seed.event",
        session_id="seed-session",
        intent_id="seed-intent",
        proposal_id="seed-proposal",
    )
    env.receipts.append(
        ExecutionReceipt.now_failure(
            command="python",
            correlation_id="seed-correlation",
            fingerprint=fp("seed-receipt"),
        )
    )
    journal_checkpoint = checkpoints.publish(
        "journal",
        env.journal,
    )
    receipt_checkpoint = checkpoints.publish(
        "receipts",
        env.receipts,
    )
    return (
        journal_checkpoint,
        receipt_checkpoint,
    )


def build_finalization_proofs(
    env,
    proof_operator,
    result,
):
    targets = (
        DurableProofWindowTarget(
            "journal",
            result.finalized.checkpoint.journal_root,
        ),
        DurableProofWindowTarget(
            "receipts",
            result.finalized.checkpoint.receipt_root,
        ),
    )
    report = proof_operator.ensure(
        targets
    )
    assert report.ok
    return report


def bounded_recovery_verifier(
    env,
    proof_operator,
    *,
    journal=None,
    receipts=None,
    session_journals=None,
):
    return DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=(
            journal
            if journal is not None
            else env.journal
        ),
        receipt_chain=(
            receipts
            if receipts is not None
            else env.receipts
        ),
        execution_evidence=env.execution_evidence,
        session_journals=(
            env.session_journals
            if session_journals is None
            else session_journals
        ),
        proof_windows=proof_operator,
        journal_proof_chain_id="journal",
        receipt_proof_chain_id="receipts",
    )


def test_finalization_persists_session_journal_manifest_commitment(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    finalized = result.finalized
    assert finalized.session_journal_commit is not None
    manifest = (
        finalized.session_journal_commit
        .stored.manifest
    )
    assert manifest.session_id == session.session_id
    assert (
        manifest.journal_root
        == finalized.checkpoint.journal_root
    )
    assert (
        manifest.journal_digest
        == finalized.session_journal.digest
    )
    assert (
        finalized.recovery_checkpoint
        .session_journal_manifest_digest
        == manifest.digest
    )
    assert (
        finalized.execution_evidence.evidence
        .session_journal_manifest_digest
        == manifest.digest
    )


def test_fresh_manifest_store_reads_finalization_projection(tmp_path):
    env = DurableEnvironment(tmp_path)
    session, _, _, _, result = env.execute()
    fresh = DurableSessionJournalStore(
        env.backend,
        namespace="session-journals",
    )
    stored = fresh.require(
        result.finalized.finalization.finalization_id,
        journal_digest=result.finalized.session_journal.digest,
        journal_root=result.finalized.checkpoint.journal_root,
    )
    assert stored.manifest.session_id == session.session_id
    assert (
        stored.manifest.digest
        == result.finalized.recovery_checkpoint
        .session_journal_manifest_digest
    )


def test_bounded_recovery_succeeds_without_any_full_chain_scan(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute(
        session_id="bounded",
        intent_id="bounded-intent",
    )
    proof_report = build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    assert all(
        item.checked_items > 0
        for item in proof_report.reports
    )

    journal = NoFullScanJournal(
        env.journal
    )
    receipts = NoFullScanReceipts(
        env.receipts
    )
    verifier = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=journal,
        receipts=receipts,
    )
    report = verifier.require_verified(
        result.finalized.finalization.finalization_id
    )
    assert report.ok
    assert report.integrity is not None
    assert report.integrity.ok
    assert journal.snapshot_calls == 0
    assert journal.snapshot_at_calls == 0
    assert journal.verify_calls == 0
    assert receipts.snapshot_calls == 0
    assert receipts.snapshot_at_calls == 0
    assert receipts.verify_calls == 0


def test_bounded_recovery_survives_later_unrelated_chain_growth_without_scan(
    tmp_path,
):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, first = env.execute(
        session_id="first-bounded",
        intent_id="first-bounded-intent",
    )
    build_finalization_proofs(
        env,
        proof_operator,
        first,
    )
    env.execute(
        session_id="later-bounded",
        intent_id="later-bounded-intent",
    )
    for index in range(10):
        env.journal.append(
            f"later.extra.{index}",
            session_id="later-extra",
            intent_id="later-extra-intent",
        )

    journal = NoFullScanJournal(
        env.journal
    )
    receipts = NoFullScanReceipts(
        env.receipts
    )
    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=journal,
        receipts=receipts,
    ).require_verified(
        first.finalized.finalization.finalization_id
    )
    assert report.ok
    assert (
        report.journal_root
        == first.finalized.checkpoint.journal_root
    )
    assert (
        report.receipt_root
        == first.finalized.checkpoint.receipt_root
    )
    assert journal.snapshot_calls == 0
    assert receipts.snapshot_calls == 0


def test_missing_cached_journal_proof_blocks_no_scan_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        proof_store,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    journal_root = (
        result.finalized.checkpoint.journal_root
    )
    proof = proof_store.find_target(
        "journal",
        journal_root,
    )
    target_key = proof_store._target_key(
        "journal",
        journal_root,
    )
    target_record = env.backend.get(
        "bounded-proofs",
        target_key,
    )
    env.backend.delete(
        "bounded-proofs",
        target_key,
        expected_revision=target_record.revision,
    )
    assert proof is not None

    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
    ).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.requires_manual_review
    assert any(
        item.code.startswith(
            "session_integrity"
        )
        for item in report.findings
    )


def test_missing_cached_receipt_proof_blocks_no_scan_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        proof_store,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    receipt_root = (
        result.finalized.checkpoint.receipt_root
    )
    target_key = proof_store._target_key(
        "receipts",
        receipt_root,
    )
    target_record = env.backend.get(
        "bounded-proofs",
        target_key,
    )
    env.backend.delete(
        "bounded-proofs",
        target_key,
        expected_revision=target_record.revision,
    )

    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
    ).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.requires_manual_review
    assert any(
        item.code.startswith(
            "session_integrity"
        )
        for item in report.findings
    )


def test_tampered_session_manifest_blocks_no_scan_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    session, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    finalization_id = (
        result.finalized.finalization
        .finalization_id
    )
    key = (
        env.session_journals
        ._manifest_key(
            finalization_id
        )
    )
    record = env.backend.get(
        "session-journals",
        key,
    )
    bad_evidence = replace(
        record.value.journal_evidence,
        events=(
            replace(
                record.value.journal_evidence.events[0],
                kind="tampered.kind",
            ),
            *record.value.journal_evidence.events[1:],
        ),
    )
    env.backend.compare_and_swap(
        "session-journals",
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            journal_evidence=bad_evidence,
        ),
    )

    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
    ).verify(
        finalization_id
    )
    assert report.requires_manual_review
    assert any(
        item.code
        == "session_journal.corruption"
        for item in report.findings
    )
    assert session.session_id == (
        result.finalized.session_journal
        .session_id
    )


def test_deleted_required_session_manifest_blocks_no_scan_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    finalization_id = (
        result.finalized.finalization
        .finalization_id
    )
    key = (
        env.session_journals
        ._manifest_key(
            finalization_id
        )
    )
    record = env.backend.get(
        "session-journals",
        key,
    )
    env.backend.delete(
        "session-journals",
        key,
        expected_revision=record.revision,
    )

    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
    ).verify(
        finalization_id
    )
    assert report.requires_manual_review
    assert any(
        item.code
        == "session_journal.corruption"
        for item in report.findings
    )


def test_tampered_journal_sequence_index_blocks_bounded_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    manifest = (
        result.finalized.session_journal_commit
        .stored.manifest
    )
    sequence = (
        manifest.journal_evidence.events[0]
        .global_sequence
    )
    key = env.journal._sequence_key(
        sequence
    )
    record = env.backend.get(
        "decision-journal",
        key,
    )
    wrong_sequence = max(
        1,
        sequence - 1,
    )
    wrong_root = (
        env.journal.root_for_sequence(
            wrong_sequence
        )
    )
    env.backend.compare_and_swap(
        "decision-journal",
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            event_hash=wrong_root,
        ),
    )

    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
    ).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.requires_manual_review


def test_tampered_receipt_id_index_blocks_bounded_recovery(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    step = (
        result.finalized.session_evidence
        .steps[0]
    )
    receipt_id = step.receipt_ids[0]
    key = env.receipts._index_key(
        receipt_id
    )
    record = env.backend.get(
        "receipts",
        key,
    )
    env.backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            receipt_fingerprint=fp(
                "tampered-receipt"
            ),
        ),
    )

    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
    ).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.requires_manual_review


def test_legacy_recovery_without_manifest_or_proofs_keeps_scan_fallback(tmp_path):
    env = DurableEnvironment(tmp_path)
    # Deliberately replace the finalizer with the legacy-compatible mode.
    legacy_finalizer = AIExecutionEvidenceFinalizer(
        journal=env.journal,
        receipt_chain=env.receipts,
        session_evidence=env.session_evidence,
        audit_anchors=env.anchors,
        audit_witnesses=env.witnesses,
        execution_evidence=env.execution_evidence,
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_journals=None,
    )
    env.finalizer = legacy_finalizer
    _, _, _, _, result = env.execute(
        session_id="legacy",
        intent_id="legacy-intent",
    )
    assert (
        result.finalized.recovery_checkpoint
        .session_journal_manifest_digest
        == ""
    )
    verifier = DurableSessionRecoveryVerifier(
        finalizations=env.finalizations,
        recovery_checkpoints=env.recovery,
        session_evidence=env.session_evidence,
        journal=env.journal,
        receipt_chain=env.receipts,
        execution_evidence=env.execution_evidence,
        session_journals=None,
    )
    report = verifier.require_verified(
        result.finalized.finalization.finalization_id
    )
    assert report.ok


def test_manifest_fast_path_rejects_wrong_configured_store_namespace(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    empty_manifest_store = DurableSessionJournalStore(
        env.backend,
        namespace="empty-session-journals",
    )
    report = bounded_recovery_verifier(
        env,
        proof_operator,
        journal=NoFullScanJournal(
            env.journal
        ),
        receipts=NoFullScanReceipts(
            env.receipts
        ),
        session_journals=empty_manifest_store,
    ).verify(
        result.finalized.finalization.finalization_id
    )
    assert report.requires_manual_review
    assert any(
        item.code
        == "session_journal.corruption"
        for item in report.findings
    )


def test_proof_operator_root_verification_round_trip(tmp_path):
    env = DurableEnvironment(tmp_path)
    (
        checkpoints,
        _,
        _,
        proof_operator,
    ) = bounded_recovery_proof_runtime(env)
    seed_and_checkpoint_durable_chains(
        env,
        checkpoints,
    )
    _, _, _, _, result = env.execute()
    build_finalization_proofs(
        env,
        proof_operator,
        result,
    )
    assert proof_operator.verify_root(
        "journal",
        result.finalized.checkpoint.journal_root,
    )
    assert proof_operator.verify_root(
        "receipts",
        result.finalized.checkpoint.receipt_root,
    )
    assert not proof_operator.verify_root(
        "journal",
        fp("not-cached"),
    )


def test_manifest_digest_is_cross_bound_in_recovery_and_signed_evidence(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    manifest_digest = (
        result.finalized.session_journal_commit
        .stored.manifest.digest
    )
    assert (
        result.finalized.recovery_checkpoint
        .session_journal_manifest_digest
        == manifest_digest
    )
    assert (
        result.finalized.execution_evidence
        .evidence.session_journal_manifest_digest
        == manifest_digest
    )
    assert len(manifest_digest) == 64


def test_serialized_finalization_exposes_manifest_commit(tmp_path):
    env = DurableEnvironment(tmp_path)
    _, _, _, _, result = env.execute()
    data = result.finalized.to_dict()
    commit = data[
        "session_journal_commit"
    ]
    assert commit is not None
    assert (
        commit["stored"]["manifest"]
        ["finalization_id"]
        == result.finalized.finalization
        .finalization_id
    )
    assert (
        commit["stored"]["manifest"]
        ["journal_digest"]
        == result.finalized.session_journal.digest
    )

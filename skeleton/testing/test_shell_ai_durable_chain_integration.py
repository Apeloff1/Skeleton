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
from skeleton.shells.ai.execution_attempt import AIExecutionAttemptStore
from skeleton.shells.ai.execution_evidence import AIExecutionEvidenceStore
from skeleton.shells.ai.execution_seal import ExecutionSealAuthority
from skeleton.shells.ai.finalization_reconciler import (
    AIExecutionFinalizationReconciler,
    FinalizationReconcileAction,
)
from skeleton.shells.ai.finalization_state import AIExecutionFinalizationStore
from skeleton.shells.ai.governance import AIShellGovernance
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

"""Public API and compatibility contracts for durable shell evidence."""

from __future__ import annotations

import inspect

import pytest

import skeleton.shells as shells
import skeleton.shells.ai as ai
from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalConflict,
    DistributedJournalCorruption,
    DistributedJournalHead,
)
from skeleton.shells.ai.durable_archive_repair import (
    ArchiveIndexRepairAction,
    ArchiveIndexRepairBatchReport,
    ArchiveIndexRepairError,
    ArchiveIndexRepairPlan,
    ArchiveIndexRepairPolicy,
    ArchiveIndexRepairResult,
    ArchiveIndexRepairState,
    DurableArchiveIndexRepairCoordinator,
)
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchivedNode,
    DurableArchivedNodeType,
    DurableArchiveHead,
    DurableArchiveIndexHealth,
    DurableArchiveIndexState,
    DurableArchiveRepository,
    DurableArchiveRootIndex,
    DurableArchiveRootReplica,
    DurableArchiveRootResolution,
    DurableArchiveStoreError,
    DurableArchiveStoreReport,
    StoredDurableArchive,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableCheckpointIndexHealth,
    DurableCheckpointIndexState,
    DurableCheckpointLookupIndex,
)
from skeleton.shells.ai.durable_checkpoint_repair import (
    CheckpointIndexRepairAction,
    CheckpointIndexRepairBatchReport,
    CheckpointIndexRepairError,
    CheckpointIndexRepairPlan,
    CheckpointIndexRepairPolicy,
    CheckpointIndexRepairResult,
    CheckpointIndexRepairState,
    DurableCheckpointIndexRepairCoordinator,
)
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionError,
    DurableCompactionPlanner,
    DurableCompactionPolicy,
    DurableCompactionReadiness,
    DurableCompactionRootCoverage,
    DurableCompactionState,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificate,
    DurableCompactionCertificateError,
    DurableCompactionCertificateHead,
    DurableCompactionCertificateStore,
    DurableCompactionCertificateVerification,
    SignedDurableCompactionCertificate,
)
from skeleton.shells.ai.durable_lifecycle import (
    DurableEvidenceLifecycleCoordinator,
    DurableLifecycleAction,
    DurableLifecycleError,
    DurableLifecyclePolicy,
    DurableLifecycleReport,
    DurableLifecycleState,
)
from skeleton.shells.ai.durable_failover import (
    DurableFailoverAuthority,
    DurableFailoverConflict,
    DurableFailoverCoordinator,
    DurableFailoverPhase,
    DurableFailoverRecord,
    DurableFailoverRegistry,
    DurableFailoverTicket,
    DurableFailoverTicketError,
    SignedDurableFailoverTicket,
    StoredDurableFailover,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetError,
    DurableReplicaFleetFinding,
    DurableReplicaFleetMember,
    DurableReplicaFleetMemberReport,
    DurableReplicaFleetMemberRun,
    DurableReplicaFleetPolicy,
    DurableReplicaFleetReport,
    DurableReplicaFleetRun,
)
from skeleton.shells.ai.durable_replication import (
    DurableChainReplicationReport,
    DurableChainReplicator,
    DurableEvidenceReplicaManager,
    DurableEvidenceReplicationReport,
    DurableEvidenceReplicationRun,
    DurableReplicaState,
    DurableReplicationBatch,
    DurableReplicationError,
    DurableReplicationPolicy,
    DurableReplicationRun,
)
from skeleton.shells.ai.durable_proof_window import (
    PROOF_ARTIFACT_TYPE,
    DurableHistoricalProofAuthority,
    DurableHistoricalProofError,
    DurableHistoricalProofIndex,
    DurableHistoricalProofStore,
    DurableHistoricalProofVerification,
    DurableHistoricalProofWindow,
    ProofWindowChain,
    SignedDurableHistoricalProofWindow,
)
from skeleton.shells.ai.durable_proof_window_operator import (
    DurableProofWindowFleetReport,
    DurableProofWindowFinding,
    DurableProofWindowOperator,
    DurableProofWindowOperatorError,
    DurableProofWindowPolicy,
    DurableProofWindowReport,
    DurableProofWindowState,
    DurableProofWindowTarget,
)
from skeleton.shells.ai.durable_session_journal import (
    DurableSessionJournalCommit,
    DurableSessionJournalConflict,
    DurableSessionJournalCorruption,
    DurableSessionJournalHead,
    DurableSessionJournalManifest,
    DurableSessionJournalStore,
    StoredDurableSessionJournal,
)
from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryFinding,
    DurableRecoveryStatus,
    DurableRecoveryVerificationError,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
    RecoveryFindingSeverity,
)
from skeleton.shells.ai.session_integrity import (
    JournalInclusionResult,
    ReceiptInclusionResult,
    SessionEvidenceIntegrityError,
    SessionEvidenceIntegrityReport,
    SessionEvidenceIntegrityVerifier,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    DistributedReceiptHead,
    ReceiptInclusion,
    ReceiptIndexEntry,
)


AI_EXPORTS = {
    "PROOF_ARTIFACT_TYPE": PROOF_ARTIFACT_TYPE,
    "DurableHistoricalProofAuthority": DurableHistoricalProofAuthority,
    "DurableHistoricalProofError": DurableHistoricalProofError,
    "DurableHistoricalProofIndex": DurableHistoricalProofIndex,
    "DurableHistoricalProofStore": DurableHistoricalProofStore,
    "DurableHistoricalProofVerification": DurableHistoricalProofVerification,
    "DurableHistoricalProofWindow": DurableHistoricalProofWindow,
    "ProofWindowChain": ProofWindowChain,
    "SignedDurableHistoricalProofWindow": SignedDurableHistoricalProofWindow,
    "DurableProofWindowFleetReport": DurableProofWindowFleetReport,
    "DurableProofWindowFinding": DurableProofWindowFinding,
    "DurableProofWindowOperator": DurableProofWindowOperator,
    "DurableProofWindowOperatorError": DurableProofWindowOperatorError,
    "DurableProofWindowPolicy": DurableProofWindowPolicy,
    "DurableProofWindowReport": DurableProofWindowReport,
    "DurableProofWindowState": DurableProofWindowState,
    "DurableProofWindowTarget": DurableProofWindowTarget,
    "DurableSessionJournalCommit": DurableSessionJournalCommit,
    "DurableSessionJournalConflict": DurableSessionJournalConflict,
    "DurableSessionJournalCorruption": DurableSessionJournalCorruption,
    "DurableSessionJournalHead": DurableSessionJournalHead,
    "DurableSessionJournalManifest": DurableSessionJournalManifest,
    "DurableSessionJournalStore": DurableSessionJournalStore,
    "StoredDurableSessionJournal": StoredDurableSessionJournal,
    "ArchiveIndexRepairAction": ArchiveIndexRepairAction,
    "ArchiveIndexRepairBatchReport": ArchiveIndexRepairBatchReport,
    "ArchiveIndexRepairError": ArchiveIndexRepairError,
    "ArchiveIndexRepairPlan": ArchiveIndexRepairPlan,
    "ArchiveIndexRepairPolicy": ArchiveIndexRepairPolicy,
    "ArchiveIndexRepairResult": ArchiveIndexRepairResult,
    "ArchiveIndexRepairState": ArchiveIndexRepairState,
    "DurableArchiveIndexHealth": DurableArchiveIndexHealth,
    "DurableArchiveIndexRepairCoordinator": DurableArchiveIndexRepairCoordinator,
    "DurableArchiveIndexState": DurableArchiveIndexState,
    "CheckpointIndexRepairAction": CheckpointIndexRepairAction,
    "CheckpointIndexRepairBatchReport": CheckpointIndexRepairBatchReport,
    "CheckpointIndexRepairError": CheckpointIndexRepairError,
    "CheckpointIndexRepairPlan": CheckpointIndexRepairPlan,
    "CheckpointIndexRepairPolicy": CheckpointIndexRepairPolicy,
    "CheckpointIndexRepairResult": CheckpointIndexRepairResult,
    "CheckpointIndexRepairState": CheckpointIndexRepairState,
    "DurableCheckpointIndexRepairCoordinator": DurableCheckpointIndexRepairCoordinator,
    "DurableCheckpointIndexHealth": DurableCheckpointIndexHealth,
    "DurableCheckpointIndexState": DurableCheckpointIndexState,
    "DurableCheckpointLookupIndex": DurableCheckpointLookupIndex,
    "DurableEvidenceLifecycleCoordinator": DurableEvidenceLifecycleCoordinator,
    "DurableLifecycleAction": DurableLifecycleAction,
    "DurableLifecycleError": DurableLifecycleError,
    "DurableLifecyclePolicy": DurableLifecyclePolicy,
    "DurableLifecycleReport": DurableLifecycleReport,
    "DurableLifecycleState": DurableLifecycleState,
    "DurableCompactionCertificate": DurableCompactionCertificate,
    "DurableCompactionCertificateError": DurableCompactionCertificateError,
    "DurableCompactionCertificateHead": DurableCompactionCertificateHead,
    "DurableCompactionCertificateStore": DurableCompactionCertificateStore,
    "DurableCompactionCertificateVerification": DurableCompactionCertificateVerification,
    "SignedDurableCompactionCertificate": SignedDurableCompactionCertificate,
    "DurableCompactionError": DurableCompactionError,
    "DurableCompactionPlanner": DurableCompactionPlanner,
    "DurableCompactionPolicy": DurableCompactionPolicy,
    "DurableCompactionReadiness": DurableCompactionReadiness,
    "DurableCompactionRootCoverage": DurableCompactionRootCoverage,
    "DurableCompactionState": DurableCompactionState,
    "ArchiveBackedHistoricalChain": ArchiveBackedHistoricalChain,
    "DurableArchivedNode": DurableArchivedNode,
    "DurableArchivedNodeType": DurableArchivedNodeType,
    "DurableArchiveHead": DurableArchiveHead,
    "DurableArchiveRepository": DurableArchiveRepository,
    "DurableArchiveRootIndex": DurableArchiveRootIndex,
    "DurableArchiveRootReplica": DurableArchiveRootReplica,
    "DurableArchiveRootResolution": DurableArchiveRootResolution,
    "DurableArchiveStoreError": DurableArchiveStoreError,
    "DurableArchiveStoreReport": DurableArchiveStoreReport,
    "StoredDurableArchive": StoredDurableArchive,
    "DistributedAIDecisionJournal": DistributedAIDecisionJournal,
    "DistributedJournalConflict": DistributedJournalConflict,
    "DistributedJournalCorruption": DistributedJournalCorruption,
    "DistributedJournalHead": DistributedJournalHead,
    "JournalInclusionResult": JournalInclusionResult,
    "ReceiptInclusionResult": ReceiptInclusionResult,
    "SessionEvidenceIntegrityError": SessionEvidenceIntegrityError,
    "SessionEvidenceIntegrityReport": SessionEvidenceIntegrityReport,
    "SessionEvidenceIntegrityVerifier": SessionEvidenceIntegrityVerifier,
    "DurableRecoveryFinding": DurableRecoveryFinding,
    "DurableRecoveryStatus": DurableRecoveryStatus,
    "DurableRecoveryVerificationError": DurableRecoveryVerificationError,
    "DurableSessionRecoveryReport": DurableSessionRecoveryReport,
    "DurableSessionRecoveryVerifier": DurableSessionRecoveryVerifier,
    "RecoveryFindingSeverity": RecoveryFindingSeverity,
    "DurableChainReplicationReport": DurableChainReplicationReport,
    "DurableChainReplicator": DurableChainReplicator,
    "DurableEvidenceReplicaManager": DurableEvidenceReplicaManager,
    "DurableEvidenceReplicationReport": DurableEvidenceReplicationReport,
    "DurableEvidenceReplicationRun": DurableEvidenceReplicationRun,
    "DurableReplicaState": DurableReplicaState,
    "DurableReplicationBatch": DurableReplicationBatch,
    "DurableReplicationError": DurableReplicationError,
    "DurableReplicationPolicy": DurableReplicationPolicy,
    "DurableReplicationRun": DurableReplicationRun,
    "DurableFailoverAuthority": DurableFailoverAuthority,
    "DurableFailoverConflict": DurableFailoverConflict,
    "DurableFailoverCoordinator": DurableFailoverCoordinator,
    "DurableFailoverPhase": DurableFailoverPhase,
    "DurableFailoverRecord": DurableFailoverRecord,
    "DurableFailoverRegistry": DurableFailoverRegistry,
    "DurableFailoverTicket": DurableFailoverTicket,
    "DurableFailoverTicketError": DurableFailoverTicketError,
    "SignedDurableFailoverTicket": SignedDurableFailoverTicket,
    "StoredDurableFailover": StoredDurableFailover,
    "DurableReplicaFleet": DurableReplicaFleet,
    "DurableReplicaFleetError": DurableReplicaFleetError,
    "DurableReplicaFleetFinding": DurableReplicaFleetFinding,
    "DurableReplicaFleetMember": DurableReplicaFleetMember,
    "DurableReplicaFleetMemberReport": DurableReplicaFleetMemberReport,
    "DurableReplicaFleetMemberRun": DurableReplicaFleetMemberRun,
    "DurableReplicaFleetPolicy": DurableReplicaFleetPolicy,
    "DurableReplicaFleetReport": DurableReplicaFleetReport,
    "DurableReplicaFleetRun": DurableReplicaFleetRun,
}


SHELL_EXPORTS = {
    "DistributedReceiptChain": DistributedReceiptChain,
    "DistributedReceiptConflict": DistributedReceiptConflict,
    "DistributedReceiptCorruption": DistributedReceiptCorruption,
    "DistributedReceiptHead": DistributedReceiptHead,
    "ReceiptInclusion": ReceiptInclusion,
    "ReceiptIndexEntry": ReceiptIndexEntry,
}


@pytest.mark.parametrize(
    "name,value",
    sorted(AI_EXPORTS.items()),
)
def test_ai_package_exports_durable_evidence_surface(name, value):
    assert hasattr(ai, name)
    assert getattr(ai, name) is value
    assert name in ai.__all__


@pytest.mark.parametrize(
    "name,value",
    sorted(SHELL_EXPORTS.items()),
)
def test_shell_package_exports_durable_receipt_surface(name, value):
    assert hasattr(shells, name)
    assert getattr(shells, name) is value
    assert name in shells.__all__


def test_legacy_durable_receipt_import_is_canonical_class():
    from skeleton.shells.durable_receipts import (
        DistributedReceiptChain as LegacyImport,
    )

    assert LegacyImport is DistributedReceiptChain
    assert shells.DistributedReceiptChain is DistributedReceiptChain


def test_direct_distributed_receipt_import_is_canonical_class():
    from skeleton.shells.distributed_receipts import (
        DistributedReceiptChain as DirectImport,
    )

    assert DirectImport is DistributedReceiptChain


@pytest.mark.parametrize(
    "name",
    sorted(SHELL_EXPORTS),
)
def test_legacy_durable_receipt_module_exports_expected_names(name):
    import skeleton.shells.durable_receipts as durable

    assert name in durable.__all__
    assert getattr(durable, name) is SHELL_EXPORTS[name]


def test_no_duplicate_ai_export_names():
    assert len(ai.__all__) == len(set(ai.__all__))


def test_no_duplicate_shell_export_names():
    assert len(shells.__all__) == len(set(shells.__all__))


def test_distributed_journal_constructor_exposes_durable_backend():
    signature = inspect.signature(DistributedAIDecisionJournal)
    assert "backend" in signature.parameters
    assert "namespace" in signature.parameters
    assert "max_events" in signature.parameters
    assert "max_cas_retries" in signature.parameters
    assert "clock" in signature.parameters


def test_distributed_receipt_constructor_exposes_durable_backend():
    signature = inspect.signature(DistributedReceiptChain)
    assert "backend" in signature.parameters
    assert "namespace" in signature.parameters
    assert "max_receipts" in signature.parameters
    assert "max_cas_retries" in signature.parameters


def test_integrity_verifier_constructor_requires_both_authoritative_chains():
    signature = inspect.signature(SessionEvidenceIntegrityVerifier)
    assert "journal" in signature.parameters
    assert "receipt_chain" in signature.parameters
    assert "require_session_journal" in signature.parameters


def test_durable_recovery_verifier_constructor_requires_all_core_stores():
    signature = inspect.signature(DurableSessionRecoveryVerifier)
    required = {
        "finalizations",
        "recovery_checkpoints",
        "session_evidence",
        "journal",
        "receipt_chain",
    }
    assert required.issubset(signature.parameters)
    assert "execution_evidence" in signature.parameters


@pytest.mark.parametrize(
    "method",
    [
        "append",
        "snapshot",
        "snapshot_at",
        "verify",
        "verify_root",
        "root_is_ancestor",
        "root_hash",
        "length",
        "events_for_session",
        "require_root",
    ],
)
def test_distributed_journal_public_methods_are_stable(method):
    assert callable(
        getattr(
            DistributedAIDecisionJournal,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "append",
        "snapshot",
        "snapshot_at",
        "verify",
        "verify_root",
        "root_is_ancestor",
        "root_hash",
        "length",
        "find_by_receipt_id",
        "require_receipt",
        "require_receipts",
        "require_root",
    ],
)
def test_distributed_receipt_public_methods_are_stable(method):
    assert callable(
        getattr(
            DistributedReceiptChain,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    ["verify", "require"],
)
def test_session_integrity_verifier_methods_are_stable(method):
    assert callable(
        getattr(
            SessionEvidenceIntegrityVerifier,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    ["verify", "require_verified"],
)
def test_durable_recovery_verifier_methods_are_stable(method):
    assert callable(
        getattr(
            DurableSessionRecoveryVerifier,
            method,
            None,
        )
    )


def test_recovery_status_values_are_wire_stable():
    assert {
        item.value
        for item in DurableRecoveryStatus
    } == {
        "verified",
        "incomplete",
        "manual_review",
    }


def test_recovery_finding_severity_values_are_wire_stable():
    assert {
        item.value
        for item in RecoveryFindingSeverity
    } == {
        "missing",
        "conflict",
        "corruption",
    }


@pytest.mark.parametrize(
    "value",
    [
        "verified",
        "incomplete",
        "manual_review",
    ],
)
def test_recovery_status_round_trip(value):
    assert DurableRecoveryStatus(value).value == value


@pytest.mark.parametrize(
    "value",
    [
        "missing",
        "conflict",
        "corruption",
    ],
)
def test_recovery_severity_round_trip(value):
    assert RecoveryFindingSeverity(value).value == value


def test_distributed_journal_head_serialization_contract():
    head = DistributedJournalHead(
        7,
        "a" * 64,
    )
    assert head.to_dict() == {
        "sequence": 7,
        "root_hash": "a" * 64,
    }


def test_distributed_receipt_head_serialization_contract():
    head = DistributedReceiptHead(
        8,
        "b" * 64,
    )
    assert head.to_dict() == {
        "sequence": 8,
        "root_hash": "b" * 64,
    }


def test_receipt_index_serialization_contract():
    entry = ReceiptIndexEntry(
        "receipt-1",
        "c" * 64,
        "d" * 64,
        9,
    )
    assert entry.to_dict() == {
        "receipt_id": "receipt-1",
        "receipt_hash": "c" * 64,
        "receipt_fingerprint": "d" * 64,
        "sequence": 9,
    }


def test_durable_recovery_finding_serialization_contract():
    finding = DurableRecoveryFinding(
        "checkpoint.missing",
        RecoveryFindingSeverity.MISSING,
        "checkpoint is absent",
    )
    assert finding.to_dict() == {
        "code": "checkpoint.missing",
        "severity": "missing",
        "message": "checkpoint is absent",
    }


def test_journal_inclusion_serialization_contract():
    item = JournalInclusionResult(
        1,
        "a" * 64,
        "ai.plan.completed",
        "proposal",
        True,
        True,
    )
    assert item.to_dict() == {
        "global_sequence": 1,
        "event_hash": "a" * 64,
        "kind": "ai.plan.completed",
        "proposal_id": "proposal",
        "found": True,
        "valid": True,
        "reason": "",
    }


def test_receipt_inclusion_result_serialization_contract():
    item = ReceiptInclusionResult(
        "step",
        "correlation",
        1,
        "receipt",
        "a" * 64,
        0,
        2,
        True,
        True,
    )
    assert item.to_dict() == {
        "step_id": "step",
        "correlation_id": "correlation",
        "attempt": 1,
        "receipt_id": "receipt",
        "fingerprint": "a" * 64,
        "returncode": 0,
        "global_sequence": 2,
        "found": True,
        "valid": True,
        "reason": "",
    }


def test_integrity_report_boolean_properties_are_derived():
    journal = JournalInclusionResult(
        1,
        "a" * 64,
        "event",
        "",
        True,
        True,
    )
    receipt = ReceiptInclusionResult(
        "step",
        "correlation",
        1,
        "receipt",
        "b" * 64,
        0,
        1,
        True,
        True,
    )
    report = SessionEvidenceIntegrityReport(
        "session",
        True,
        True,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        (journal,),
        (receipt,),
        (),
    )
    assert report.ok
    data = report.to_dict()
    assert data["ok"] is True
    assert data["digest"] == report.digest


def test_integrity_report_issue_makes_report_not_ok():
    journal = JournalInclusionResult(
        1,
        "a" * 64,
        "event",
        "",
        True,
        True,
    )
    report = SessionEvidenceIntegrityReport(
        "session",
        True,
        True,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        (journal,),
        (),
        ("problem",),
    )
    assert not report.ok


def test_recovery_report_verified_properties():
    report = DurableSessionRecoveryReport(
        "finalization",
        "session",
        DurableRecoveryStatus.VERIFIED,
        "complete",
        1,
        1,
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        "1" * 64,
        "2" * 64,
        None,
        (),
    )
    assert report.ok
    assert not report.safe_to_resume
    assert not report.requires_manual_review
    assert report.to_dict()["status"] == "verified"


def test_recovery_report_incomplete_properties():
    report = DurableSessionRecoveryReport(
        "finalization",
        "session",
        DurableRecoveryStatus.INCOMPLETE,
        "checkpointed",
        1,
        1,
        None,
        "a" * 64,
        "b" * 64,
        "",
        "",
        "",
        "",
        "1" * 64,
        "2" * 64,
        None,
        (
            DurableRecoveryFinding(
                "session.missing",
                RecoveryFindingSeverity.MISSING,
                "session evidence missing",
            ),
        ),
    )
    assert not report.ok
    assert report.safe_to_resume
    assert not report.requires_manual_review


def test_recovery_report_manual_review_properties():
    report = DurableSessionRecoveryReport(
        "finalization",
        "session",
        DurableRecoveryStatus.MANUAL_REVIEW,
        "complete",
        1,
        1,
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        "1" * 64,
        "2" * 64,
        None,
        (
            DurableRecoveryFinding(
                "evidence.conflict",
                RecoveryFindingSeverity.CONFLICT,
                "evidence differs",
            ),
        ),
    )
    assert not report.ok
    assert not report.safe_to_resume
    assert report.requires_manual_review


def test_recovery_report_digest_excluded_from_digest_input():
    report = DurableSessionRecoveryReport(
        "finalization",
        "session",
        DurableRecoveryStatus.VERIFIED,
        "complete",
        1,
        1,
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        "1" * 64,
        "2" * 64,
        None,
        (),
    )
    data = report.to_dict(
        include_digest=False
    )
    assert "digest" not in data
    assert report.to_dict()["digest"] == report.digest


@pytest.mark.parametrize(
    "status,ok,resume,manual",
    [
        (
            DurableRecoveryStatus.VERIFIED,
            True,
            False,
            False,
        ),
        (
            DurableRecoveryStatus.INCOMPLETE,
            False,
            True,
            False,
        ),
        (
            DurableRecoveryStatus.MANUAL_REVIEW,
            False,
            False,
            True,
        ),
    ],
)
def test_recovery_status_property_matrix(status, ok, resume, manual):
    report = DurableSessionRecoveryReport(
        "finalization",
        "session",
        status,
        "complete",
        1,
        1,
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        "1" * 64,
        "2" * 64,
        None,
        (),
    )
    assert report.ok is ok
    assert report.safe_to_resume is resume
    assert report.requires_manual_review is manual


@pytest.mark.parametrize(
    "bad_id",
    ["", "x" * 257],
)
def test_recovery_report_validates_finalization_id(bad_id):
    with pytest.raises(ValueError, match="finalization_id"):
        DurableSessionRecoveryReport(
            bad_id,
            "session",
            DurableRecoveryStatus.VERIFIED,
            "complete",
            1,
            1,
            1,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            "e" * 64,
            "f" * 64,
            "1" * 64,
            "2" * 64,
            None,
            (),
        )


@pytest.mark.parametrize(
    "field",
    [
        "finalization_revision",
        "recovery_revision",
        "session_evidence_revision",
    ],
)
def test_recovery_report_validates_positive_revisions(field):
    values = dict(
        finalization_id="finalization",
        session_id="session",
        status=DurableRecoveryStatus.VERIFIED,
        finalization_phase="complete",
        finalization_revision=1,
        recovery_revision=1,
        session_evidence_revision=1,
        finalization_digest="a" * 64,
        recovery_checkpoint_digest="b" * 64,
        session_evidence_digest="c" * 64,
        session_journal_digest="d" * 64,
        session_integrity_digest="e" * 64,
        signed_execution_evidence_digest="f" * 64,
        journal_root="1" * 64,
        receipt_root="2" * 64,
        integrity=None,
        findings=(),
    )
    values[field] = 0
    with pytest.raises(ValueError, match=field):
        DurableSessionRecoveryReport(**values)


@pytest.mark.parametrize(
    "field",
    [
        "finalization_digest",
        "recovery_checkpoint_digest",
        "session_evidence_digest",
        "session_journal_digest",
        "session_integrity_digest",
        "signed_execution_evidence_digest",
        "journal_root",
        "receipt_root",
    ],
)
def test_recovery_report_validates_digest_shape(field):
    values = dict(
        finalization_id="finalization",
        session_id="session",
        status=DurableRecoveryStatus.VERIFIED,
        finalization_phase="complete",
        finalization_revision=1,
        recovery_revision=1,
        session_evidence_revision=1,
        finalization_digest="a" * 64,
        recovery_checkpoint_digest="b" * 64,
        session_evidence_digest="c" * 64,
        session_journal_digest="d" * 64,
        session_integrity_digest="e" * 64,
        signed_execution_evidence_digest="f" * 64,
        journal_root="1" * 64,
        receipt_root="2" * 64,
        integrity=None,
        findings=(),
    )
    values[field] = "bad"
    with pytest.raises(ValueError, match=field):
        DurableSessionRecoveryReport(**values)


@pytest.mark.parametrize(
    "code,message",
    [
        ("", "message"),
        ("x" * 129, "message"),
        ("code", ""),
        ("code", "x" * 2049),
    ],
)
def test_recovery_finding_validates_text_bounds(code, message):
    with pytest.raises(ValueError):
        DurableRecoveryFinding(
            code,
            RecoveryFindingSeverity.MISSING,
            message,
        )


def test_recovery_finding_accepts_string_severity():
    finding = DurableRecoveryFinding(
        "missing",
        "missing",
        "missing data",
    )
    assert finding.severity is RecoveryFindingSeverity.MISSING


def test_recovery_report_accepts_string_status():
    report = DurableSessionRecoveryReport(
        "finalization",
        "session",
        "verified",
        "complete",
        1,
        1,
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "f" * 64,
        "1" * 64,
        "2" * 64,
        None,
        (),
    )
    assert report.status is DurableRecoveryStatus.VERIFIED


def test_error_types_remain_runtime_errors():
    assert issubclass(
        DistributedJournalConflict,
        RuntimeError,
    )
    assert issubclass(
        DistributedJournalCorruption,
        RuntimeError,
    )
    assert issubclass(
        DistributedReceiptConflict,
        RuntimeError,
    )
    assert issubclass(
        DistributedReceiptCorruption,
        RuntimeError,
    )
    assert issubclass(
        SessionEvidenceIntegrityError,
        RuntimeError,
    )
    assert issubclass(
        DurableRecoveryVerificationError,
        RuntimeError,
    )


def test_public_modules_have_docstrings():
    assert DistributedAIDecisionJournal.__module__
    assert DistributedReceiptChain.__module__
    assert SessionEvidenceIntegrityVerifier.__module__
    assert DurableSessionRecoveryVerifier.__module__
    assert inspect.getdoc(
        DistributedAIDecisionJournal
    )
    assert inspect.getdoc(
        DistributedReceiptChain
    )
    assert inspect.getdoc(
        SessionEvidenceIntegrityVerifier
    )
    assert inspect.getdoc(
        DurableSessionRecoveryVerifier
    )


def test_compatibility_module_declares_only_supported_receipt_exports():
    import skeleton.shells.durable_receipts as durable

    assert set(durable.__all__) == set(SHELL_EXPORTS)


def test_shell_export_points_to_compatibility_reexport_without_wrapper():
    from skeleton.shells import DistributedReceiptChain as RootImport
    from skeleton.shells.durable_receipts import (
        DistributedReceiptChain as CompatibilityImport,
    )
    from skeleton.shells.distributed_receipts import (
        DistributedReceiptChain as CanonicalImport,
    )

    assert RootImport is CanonicalImport
    assert CompatibilityImport is CanonicalImport


def test_ai_export_points_to_canonical_distributed_journal():
    from skeleton.shells.ai import (
        DistributedAIDecisionJournal as RootImport,
    )
    from skeleton.shells.ai.distributed_journal import (
        DistributedAIDecisionJournal as CanonicalImport,
    )

    assert RootImport is CanonicalImport


def test_ai_export_points_to_canonical_integrity_verifier():
    from skeleton.shells.ai import (
        SessionEvidenceIntegrityVerifier as RootImport,
    )
    from skeleton.shells.ai.session_integrity import (
        SessionEvidenceIntegrityVerifier as CanonicalImport,
    )

    assert RootImport is CanonicalImport


def test_ai_export_points_to_canonical_recovery_verifier():
    from skeleton.shells.ai import (
        DurableSessionRecoveryVerifier as RootImport,
    )
    from skeleton.shells.ai.durable_recovery import (
        DurableSessionRecoveryVerifier as CanonicalImport,
    )

    assert RootImport is CanonicalImport

def test_archive_repository_constructor_exposes_durable_authority():
    signature = inspect.signature(DurableArchiveRepository)
    required = {
        "backend",
        "checkpoints",
        "archive_signer",
        "namespace",
        "max_nodes_per_archive",
        "max_cas_retries",
        "clock",
    }
    assert required.issubset(signature.parameters)


@pytest.mark.parametrize(
    "method",
    [
        "put",
        "get",
        "require",
        "root_index",
        "latest",
        "get_node",
        "snapshot_at",
        "sequence_for_root",
        "snapshot_segment",
        "verify_root",
        "root_is_archived",
        "verify_archive",
        "repair_indexes",
    ],
)
def test_archive_repository_public_methods_are_stable(method):
    assert callable(
        getattr(
            DurableArchiveRepository,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "head",
        "verify",
        "snapshot",
        "root_hash",
        "length",
        "snapshot_at",
        "sequence_for_root",
        "snapshot_segment",
        "verify_root",
        "root_is_ancestor",
    ],
)
def test_archive_backed_historical_chain_surface_is_stable(method):
    assert callable(
        getattr(
            ArchiveBackedHistoricalChain,
            method,
            None,
        )
    )


def test_archive_node_type_wire_values_are_stable():
    assert {
        item.value
        for item in DurableArchivedNodeType
    } == {
        "ai_decision_event",
        "execution_receipt",
        "evidence_node",
    }


def test_archive_store_error_is_runtime_error():
    assert issubclass(
        DurableArchiveStoreError,
        RuntimeError,
    )

def test_compaction_planner_constructor_exposes_archive_authority():
    signature = inspect.signature(DurableCompactionPlanner)
    assert "archives" in signature.parameters
    assert "policy" in signature.parameters


@pytest.mark.parametrize(
    "method",
    ["inspect", "require_ready"],
)
def test_compaction_planner_public_methods_are_stable(method):
    assert callable(
        getattr(
            DurableCompactionPlanner,
            method,
            None,
        )
    )


def test_compaction_state_wire_values_are_public_contract():
    assert {
        item.value
        for item in DurableCompactionState
    } == {
        "ready",
        "no_archive_candidate",
        "archive_missing",
        "archive_invalid",
        "stale_retention_plan",
        "live_tail_too_small",
        "protected_root_gap",
        "chain_invalid",
    }


def test_compaction_error_is_runtime_error_public_contract():
    assert issubclass(
        DurableCompactionError,
        RuntimeError,
    )


def test_compaction_readiness_exposes_non_destructive_authority_property():
    assert isinstance(
        DurableCompactionReadiness.destructive_action_authorized,
        property,
    )

def test_durable_lifecycle_coordinator_constructor_contract():
    signature = inspect.signature(
        DurableEvidenceLifecycleCoordinator
    )
    assert {
        "checkpoints",
        "retention",
        "archive_builder",
        "archives",
        "compaction",
        "policy",
    }.issubset(signature.parameters)


@pytest.mark.parametrize(
    "method",
    ["inspect", "prepare", "require_operational"],
)
def test_durable_lifecycle_coordinator_public_methods(method):
    assert callable(
        getattr(
            DurableEvidenceLifecycleCoordinator,
            method,
            None,
        )
    )


def test_durable_lifecycle_state_wire_values_public_contract():
    assert {
        item.value
        for item in DurableLifecycleState
    } == {
        "healthy",
        "checkpoint_required",
        "checkpoint_primed",
        "archive_required",
        "archive_stored",
        "compaction_ready",
        "blocked",
    }


def test_durable_lifecycle_action_wire_values_public_contract():
    assert {
        item.value
        for item in DurableLifecycleAction
    } == {
        "none",
        "checkpoint_published",
        "archive_persisted",
        "archive_reused",
    }


def test_durable_lifecycle_report_is_explicitly_non_destructive():
    assert isinstance(
        DurableLifecycleReport.destructive_action_authorized,
        property,
    )


def test_durable_lifecycle_error_is_runtime_error_public_contract():
    assert issubclass(
        DurableLifecycleError,
        RuntimeError,
    )

def test_compaction_certificate_store_constructor_contract():
    signature = inspect.signature(
        DurableCompactionCertificateStore
    )
    assert {
        "backend",
        "signer",
        "planner",
        "namespace",
        "ttl_seconds",
        "max_ttl_seconds",
        "max_cas_retries",
        "clock",
    }.issubset(signature.parameters)


@pytest.mark.parametrize(
    "method",
    [
        "get",
        "latest",
        "issue",
        "inspect",
        "require_current",
    ],
)
def test_compaction_certificate_store_public_methods(method):
    assert callable(
        getattr(
            DurableCompactionCertificateStore,
            method,
            None,
        )
    )


def test_signed_compaction_certificate_is_non_destructive_public_contract():
    assert isinstance(
        SignedDurableCompactionCertificate.destructive_action_authorized,
        property,
    )
    assert isinstance(
        DurableCompactionCertificate.destructive_action_authorized,
        property,
    )
    assert isinstance(
        DurableCompactionCertificateVerification.destructive_action_authorized,
        property,
    )


def test_compaction_certificate_error_is_runtime_error_public_contract():
    assert issubclass(
        DurableCompactionCertificateError,
        RuntimeError,
    )


def test_archive_root_replica_public_shape():
    signature = inspect.signature(
        DurableArchiveRootReplica
    )
    assert tuple(signature.parameters) == (
        "archive_id",
        "archive_manifest_digest",
    )


def test_archive_root_resolution_public_shape():
    signature = inspect.signature(
        DurableArchiveRootResolution
    )
    assert {
        "chain_id",
        "root_hash",
        "sequence",
        "archive_id",
        "archive_manifest_digest",
        "replica_index",
    } == set(signature.parameters)

def test_checkpoint_lookup_index_public_shape():
    signature = inspect.signature(
        DurableCheckpointLookupIndex
    )
    assert tuple(signature.parameters) == (
        "chain_id",
        "sequence",
        "root_hash",
        "checkpoint_digest",
        "chain_node_hash",
    )


def test_checkpoint_index_health_public_shape():
    signature = inspect.signature(
        DurableCheckpointIndexHealth
    )
    assert tuple(signature.parameters) == (
        "chain_id",
        "state",
        "registry_valid",
        "checkpoint_count",
        "digest_indexes_present",
        "root_indexes_present",
        "missing_digest_indexes",
        "missing_root_indexes",
        "corrupt_indexes",
    )


def test_checkpoint_index_state_wire_values_are_stable():
    assert {
        item.value
        for item in DurableCheckpointIndexState
    } == {
        "healthy",
        "degraded",
        "invalid",
    }


def test_checkpoint_lookup_index_serialization_contract():
    item = DurableCheckpointLookupIndex(
        "journal",
        7,
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    assert item.to_dict() == {
        "chain_id": "journal",
        "sequence": 7,
        "root_hash": "a" * 64,
        "checkpoint_digest": "b" * 64,
        "chain_node_hash": "c" * 64,
    }


def test_checkpoint_index_health_serialization_contract():
    item = DurableCheckpointIndexHealth(
        "journal",
        DurableCheckpointIndexState.DEGRADED,
        True,
        2,
        1,
        2,
        ("a" * 64,),
        (),
        (),
    )
    data = item.to_dict()
    assert data["chain_id"] == "journal"
    assert data["state"] == "degraded"
    assert data["registry_valid"] is True
    assert data["checkpoint_count"] == 2
    assert data["digest_indexes_present"] == 1
    assert data["root_indexes_present"] == 2
    assert data["missing"] == 1
    assert data["corrupt"] == 0
    assert data["healthy"] is False
    assert data["repairable"] is True
    assert len(item.digest) == 64


def test_checkpoint_index_health_invalid_not_repairable():
    item = DurableCheckpointIndexHealth(
        "journal",
        DurableCheckpointIndexState.INVALID,
        True,
        1,
        1,
        1,
        (),
        (),
        ("digest:x:mismatch",),
    )
    assert not item.healthy
    assert not item.repairable
    assert item.corrupt == 1


@pytest.mark.parametrize(
    "method",
    [
        "find_by_digest",
        "find_by_root",
        "inspect_lookup_indexes",
        "repair_lookup_indexes",
        "verify_lookup_indexes",
    ],
)
def test_checkpoint_index_store_methods_are_public(method):
    from skeleton.shells.ai.durable_checkpoint import (
        DurableChainCheckpointStore,
    )

    assert callable(
        getattr(
            DurableChainCheckpointStore,
            method,
            None,
        )
    )


def test_archive_backed_chain_satisfies_incremental_surface():
    required = {
        "head",
        "verify",
        "snapshot_segment",
    }
    assert all(
        callable(
            getattr(
                ArchiveBackedHistoricalChain,
                method,
                None,
            )
        )
        for method in required
    )

def test_checkpoint_repair_action_wire_values_are_stable():
    assert {
        item.value
        for item in CheckpointIndexRepairAction
    } == {
        "none",
        "repair_missing",
        "block_registry",
        "block_corrupt",
        "block_limit",
    }


def test_checkpoint_repair_state_wire_values_are_stable():
    assert {
        item.value
        for item in CheckpointIndexRepairState
    } == {
        "healthy",
        "planned",
        "repaired",
        "already_repaired",
        "blocked",
        "stale",
    }


def test_checkpoint_repair_coordinator_constructor_contract():
    signature = inspect.signature(
        DurableCheckpointIndexRepairCoordinator
    )
    assert {
        "checkpoints",
        "policy",
        "clock",
    }.issubset(signature.parameters)


@pytest.mark.parametrize(
    "method",
    [
        "inspect",
        "apply",
        "repair",
        "repair_batch",
    ],
)
def test_checkpoint_repair_coordinator_public_methods(method):
    assert callable(
        getattr(
            DurableCheckpointIndexRepairCoordinator,
            method,
            None,
        )
    )


def test_checkpoint_repair_error_is_runtime_error():
    assert issubclass(
        CheckpointIndexRepairError,
        RuntimeError,
    )


def test_checkpoint_repair_plan_exposes_derived_properties():
    assert isinstance(
        CheckpointIndexRepairPlan.missing_count,
        property,
    )
    assert isinstance(
        CheckpointIndexRepairPlan.executable,
        property,
    )
    assert isinstance(
        CheckpointIndexRepairPlan.blocked,
        property,
    )


def test_checkpoint_repair_result_exposes_derived_properties():
    assert isinstance(
        CheckpointIndexRepairResult.ok,
        property,
    )
    assert isinstance(
        CheckpointIndexRepairResult.mutated,
        property,
    )


def test_checkpoint_repair_batch_exposes_derived_properties():
    assert isinstance(
        CheckpointIndexRepairBatchReport.ok,
        property,
    )
    assert isinstance(
        CheckpointIndexRepairBatchReport.repaired,
        property,
    )
    assert isinstance(
        CheckpointIndexRepairBatchReport.blocked,
        property,
    )


def test_checkpoint_repair_policy_public_shape():
    signature = inspect.signature(
        CheckpointIndexRepairPolicy
    )
    assert tuple(signature.parameters) == (
        "auto_repair_missing",
        "max_repairs_per_chain",
        "max_chains_per_batch",
        "require_registry_valid",
    )

def test_archive_index_state_wire_values_are_stable():
    assert {
        item.value
        for item in DurableArchiveIndexState
    } == {
        "healthy",
        "degraded",
        "invalid",
    }


def test_archive_repair_action_wire_values_are_stable():
    assert {
        item.value
        for item in ArchiveIndexRepairAction
    } == {
        "none",
        "repair_missing",
        "block_archive",
        "block_corrupt",
        "block_limit",
    }


def test_archive_repair_state_wire_values_are_stable():
    assert {
        item.value
        for item in ArchiveIndexRepairState
    } == {
        "healthy",
        "repaired",
        "already_repaired",
        "blocked",
        "stale",
    }


def test_archive_repair_policy_public_shape():
    signature = inspect.signature(
        ArchiveIndexRepairPolicy
    )
    assert tuple(signature.parameters) == (
        "auto_repair_missing",
        "max_repairs_per_archive",
        "max_archives_per_batch",
    )


def test_archive_repair_coordinator_constructor_contract():
    signature = inspect.signature(
        DurableArchiveIndexRepairCoordinator
    )
    assert {
        "archives",
        "policy",
        "clock",
    }.issubset(signature.parameters)


@pytest.mark.parametrize(
    "method",
    [
        "inspect",
        "apply",
        "repair",
        "repair_batch",
    ],
)
def test_archive_repair_coordinator_public_methods(method):
    assert callable(
        getattr(
            DurableArchiveIndexRepairCoordinator,
            method,
            None,
        )
    )


def test_archive_repair_error_is_runtime_error():
    assert issubclass(
        ArchiveIndexRepairError,
        RuntimeError,
    )


def test_archive_index_health_public_shape():
    signature = inspect.signature(
        DurableArchiveIndexHealth
    )
    assert tuple(signature.parameters) == (
        "archive_id",
        "chain_id",
        "state",
        "archive_valid",
        "expected_root_indexes",
        "root_indexes_present",
        "replica_bindings_present",
        "missing_root_indexes",
        "missing_replica_roots",
        "corrupt_root_indexes",
        "head_repair_required",
        "head_valid",
    )


def test_archive_repair_plan_properties_are_public():
    assert isinstance(
        ArchiveIndexRepairPlan.repair_units,
        property,
    )
    assert isinstance(
        ArchiveIndexRepairPlan.executable,
        property,
    )
    assert isinstance(
        ArchiveIndexRepairPlan.blocked,
        property,
    )


def test_archive_repair_result_properties_are_public():
    assert isinstance(
        ArchiveIndexRepairResult.ok,
        property,
    )
    assert isinstance(
        ArchiveIndexRepairResult.mutated,
        property,
    )


def test_archive_repair_batch_properties_are_public():
    assert isinstance(
        ArchiveIndexRepairBatchReport.ok,
        property,
    )
    assert isinstance(
        ArchiveIndexRepairBatchReport.repaired_units,
        property,
    )
    assert isinstance(
        ArchiveIndexRepairBatchReport.blocked,
        property,
    )


def test_archive_repository_exposes_index_health():
    assert callable(
        getattr(
            DurableArchiveRepository,
            "inspect_indexes",
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    ["inspect", "sync_once", "sync", "require_in_sync"],
)
def test_durable_chain_replicator_public_methods_are_stable(method):
    assert callable(getattr(DurableChainReplicator, method, None))


@pytest.mark.parametrize(
    "method",
    ["inspect", "sync", "require_promotion_ready"],
)
def test_durable_replica_manager_public_methods_are_stable(method):
    assert callable(getattr(DurableEvidenceReplicaManager, method, None))


@pytest.mark.parametrize(
    "method",
    ["issue", "verify_static", "verify"],
)
def test_durable_failover_authority_public_methods_are_stable(method):
    assert callable(getattr(DurableFailoverAuthority, method, None))


@pytest.mark.parametrize(
    "method",
    ["current", "claim", "applied", "cancel"],
)
def test_durable_failover_registry_public_methods_are_stable(method):
    assert callable(getattr(DurableFailoverRegistry, method, None))


@pytest.mark.parametrize(
    "method",
    ["issue", "claim", "complete", "cancel"],
)
def test_durable_failover_coordinator_public_methods_are_stable(method):
    assert callable(getattr(DurableFailoverCoordinator, method, None))


@pytest.mark.parametrize(
    "method",
    ["inspect", "sync_all", "require_quorum", "eligible_targets"],
)
def test_durable_replica_fleet_public_methods_are_stable(method):
    assert callable(getattr(DurableReplicaFleet, method, None))


@pytest.mark.parametrize(
    "method",
    [
        "append",
        "snapshot",
        "snapshot_at",
        "snapshot_range",
        "snapshot_segment",
        "verify_segment",
        "restore_segment",
        "verify",
        "verify_root",
        "root_for_sequence",
        "sequence_for_root",
        "get_by_sequence",
        "root_is_ancestor",
        "root_hash",
        "length",
    ],
)
def test_distributed_journal_replication_methods_are_public(method):
    assert callable(getattr(DistributedAIDecisionJournal, method, None))


@pytest.mark.parametrize(
    "method",
    [
        "append",
        "snapshot",
        "snapshot_at",
        "snapshot_range",
        "snapshot_segment",
        "verify_segment",
        "restore_segment",
        "verify",
        "verify_root",
        "root_for_sequence",
        "sequence_for_root",
        "get_by_sequence",
        "root_is_ancestor",
        "root_hash",
        "length",
    ],
)
def test_distributed_receipt_replication_methods_are_public(method):
    assert callable(getattr(DistributedReceiptChain, method, None))


def test_durable_replica_state_wire_values_are_stable():
    assert {item.value for item in DurableReplicaState} == {
        "in_sync",
        "lagging",
        "target_ahead",
        "diverged",
        "source_invalid",
        "target_invalid",
        "history_unavailable",
        "unsupported",
    }


def test_durable_failover_phase_wire_values_are_stable():
    assert {item.value for item in DurableFailoverPhase} == {
        "claimed",
        "applied",
        "cancelled",
    }


def test_replication_policy_constructor_contract():
    signature = inspect.signature(DurableReplicationPolicy)
    assert "max_batch_items" in signature.parameters
    assert "max_batches_per_run" in signature.parameters
    assert "require_source_integrity" in signature.parameters
    assert "require_target_integrity" in signature.parameters
    assert "promotion_max_lag_items" in signature.parameters


def test_replica_fleet_policy_constructor_contract():
    signature = inspect.signature(DurableReplicaFleetPolicy)
    assert "min_ready_replicas" in signature.parameters
    assert "min_ready_failure_domains" in signature.parameters
    assert "max_member_lag_items" in signature.parameters
    assert "require_all_required_members" in signature.parameters
    assert "continue_on_sync_error" in signature.parameters


def test_failover_ticket_constructor_exposes_fleet_commitments():
    signature = inspect.signature(DurableFailoverTicket)
    assert "fleet_state_digest" in signature.parameters
    assert "fleet_policy_digest" in signature.parameters


def test_failover_coordinator_constructor_exposes_optional_fleet():
    signature = inspect.signature(DurableFailoverCoordinator)
    assert "manager" in signature.parameters
    assert "authority" in signature.parameters
    assert "registry" in signature.parameters
    assert "source_id" in signature.parameters
    assert "target_id" in signature.parameters
    assert "fleet" in signature.parameters


def test_restore_segment_is_present_on_both_canonical_chain_types():
    assert hasattr(DistributedAIDecisionJournal, "restore_segment")
    assert hasattr(DistributedReceiptChain, "restore_segment")

def test_durable_historical_proof_public_exports():
    for name, expected in {
        "DurableHistoricalProofAuthority": DurableHistoricalProofAuthority,
        "DurableHistoricalProofError": DurableHistoricalProofError,
        "DurableHistoricalProofIndex": DurableHistoricalProofIndex,
        "DurableHistoricalProofStore": DurableHistoricalProofStore,
        "DurableHistoricalProofVerification": DurableHistoricalProofVerification,
        "DurableHistoricalProofWindow": DurableHistoricalProofWindow,
        "SignedDurableHistoricalProofWindow": SignedDurableHistoricalProofWindow,
        "DurableProofWindowOperator": DurableProofWindowOperator,
        "DurableProofWindowPolicy": DurableProofWindowPolicy,
        "DurableProofWindowState": DurableProofWindowState,
        "DurableProofWindowTarget": DurableProofWindowTarget,
    }.items():
        assert getattr(ai, name) is expected


def test_durable_session_journal_public_exports():
    for name, expected in {
        "DurableSessionJournalCommit": DurableSessionJournalCommit,
        "DurableSessionJournalConflict": DurableSessionJournalConflict,
        "DurableSessionJournalCorruption": DurableSessionJournalCorruption,
        "DurableSessionJournalHead": DurableSessionJournalHead,
        "DurableSessionJournalManifest": DurableSessionJournalManifest,
        "DurableSessionJournalStore": DurableSessionJournalStore,
        "StoredDurableSessionJournal": StoredDurableSessionJournal,
    }.items():
        assert getattr(ai, name) is expected


def test_proof_artifact_type_is_stable_public_wire_value():
    assert PROOF_ARTIFACT_TYPE == "shell-ai-durable-proof-window"
    assert ai.PROOF_ARTIFACT_TYPE == PROOF_ARTIFACT_TYPE


def test_proof_window_state_wire_values_are_stable():
    assert {
        item.value
        for item in DurableProofWindowState
    } == {
        "current",
        "missing",
        "invalid",
        "out_of_window",
        "unanchored",
        "error",
    }


@pytest.mark.parametrize(
    "method",
    [
        "build_for_sequence",
        "build_for_root",
        "verify",
        "require",
    ],
)
def test_historical_proof_authority_public_methods(method):
    assert callable(
        getattr(
            DurableHistoricalProofAuthority,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "put",
        "get",
        "find_target",
        "put_once_for_target",
    ],
)
def test_historical_proof_store_public_methods(method):
    assert callable(
        getattr(
            DurableHistoricalProofStore,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "inspect_target",
        "ensure_target",
        "verify_root",
        "require_root",
        "inspect",
        "ensure",
        "require",
    ],
)
def test_proof_window_operator_public_methods(method):
    assert callable(
        getattr(
            DurableProofWindowOperator,
            method,
            None,
        )
    )


@pytest.mark.parametrize(
    "method",
    [
        "get",
        "head",
        "put",
        "require",
        "current_session",
        "verify_manifest",
    ],
)
def test_session_journal_store_public_methods(method):
    assert callable(
        getattr(
            DurableSessionJournalStore,
            method,
            None,
        )
    )


def test_historical_proof_window_public_shape():
    signature = inspect.signature(
        DurableHistoricalProofWindow
    )
    assert tuple(signature.parameters) == (
        "schema_version",
        "chain_id",
        "checkpoint_digest",
        "checkpoint_sequence",
        "checkpoint_root",
        "target_sequence",
        "target_root",
        "item_count",
        "segment_digest",
        "first_item_hash",
        "last_item_hash",
        "generated_at",
    )


def test_signed_historical_proof_window_public_shape():
    signature = inspect.signature(
        SignedDurableHistoricalProofWindow
    )
    assert tuple(signature.parameters) == (
        "proof",
        "signature",
    )


def test_historical_proof_verification_public_shape():
    signature = inspect.signature(
        DurableHistoricalProofVerification
    )
    assert tuple(signature.parameters) == (
        "valid",
        "chain_id",
        "target_sequence",
        "target_root",
        "checkpoint_sequence",
        "checkpoint_root",
        "checked_items",
        "current_sequence",
        "current_root",
        "reasons",
    )


def test_historical_proof_index_public_shape():
    signature = inspect.signature(
        DurableHistoricalProofIndex
    )
    assert tuple(signature.parameters) == (
        "chain_id",
        "target_sequence",
        "target_root",
        "proof_digest",
    )


def test_proof_window_policy_public_shape():
    signature = inspect.signature(
        DurableProofWindowPolicy
    )
    assert tuple(signature.parameters) == (
        "max_targets",
        "require_all",
        "allow_build_missing",
        "refresh_invalid",
        "require_cached",
    )


def test_proof_window_target_public_shape():
    signature = inspect.signature(
        DurableProofWindowTarget
    )
    assert tuple(signature.parameters) == (
        "chain_id",
        "target_root",
    )


def test_proof_window_report_public_shape():
    signature = inspect.signature(
        DurableProofWindowReport
    )
    assert tuple(signature.parameters) == (
        "target",
        "state",
        "cached",
        "built",
        "proof_digest",
        "checkpoint_sequence",
        "target_sequence",
        "checked_items",
        "verification",
        "findings",
    )


def test_proof_window_fleet_report_public_shape():
    signature = inspect.signature(
        DurableProofWindowFleetReport
    )
    assert tuple(signature.parameters) == (
        "policy_digest",
        "reports",
        "mutations",
    )


def test_session_journal_manifest_public_shape():
    signature = inspect.signature(
        DurableSessionJournalManifest
    )
    assert tuple(signature.parameters) == (
        "schema_version",
        "finalization_id",
        "session_id",
        "journal_root",
        "journal_evidence",
        "stored_at",
    )


def test_session_journal_head_public_shape():
    signature = inspect.signature(
        DurableSessionJournalHead
    )
    assert tuple(signature.parameters) == (
        "session_id",
        "finalization_id",
        "journal_root",
        "journal_digest",
        "event_count",
        "last_sequence",
    )


def test_stored_session_journal_public_shape():
    signature = inspect.signature(
        StoredDurableSessionJournal
    )
    assert tuple(signature.parameters) == (
        "revision",
        "manifest",
    )


def test_session_journal_commit_public_shape():
    signature = inspect.signature(
        DurableSessionJournalCommit
    )
    assert tuple(signature.parameters) == (
        "stored",
        "head_revision",
        "head",
        "head_advanced",
    )


def test_proof_and_manifest_errors_are_runtime_errors():
    for error in (
        DurableHistoricalProofError,
        DurableProofWindowOperatorError,
        DurableSessionJournalConflict,
        DurableSessionJournalCorruption,
    ):
        assert issubclass(
            error,
            RuntimeError,
        )


def test_durable_recovery_constructor_exposes_acceleration_surfaces():
    signature = inspect.signature(
        DurableSessionRecoveryVerifier
    )
    assert {
        "session_journals",
        "proof_windows",
        "journal_proof_chain_id",
        "receipt_proof_chain_id",
    }.issubset(signature.parameters)


def test_session_integrity_constructor_exposes_root_verifiers():
    signature = inspect.signature(
        SessionEvidenceIntegrityVerifier
    )
    assert {
        "journal_root_verifier",
        "receipt_root_verifier",
    }.issubset(signature.parameters)


def test_recovery_checkpoint_exposes_manifest_commitment():
    from skeleton.shells.ai.recovery_checkpoint import (
        AIRecoveryCheckpoint,
    )

    assert (
        "session_journal_manifest_digest"
        in inspect.signature(
            AIRecoveryCheckpoint
        ).parameters
    )


def test_execution_evidence_exposes_manifest_commitment():
    from skeleton.shells.ai.execution_evidence import (
        AIExecutionEvidence,
    )

    assert (
        "session_journal_manifest_digest"
        in inspect.signature(
            AIExecutionEvidence
        ).parameters
    )


def test_finalizer_constructor_exposes_session_journal_store():
    from skeleton.shells.ai.evidence_finalizer import (
        AIExecutionEvidenceFinalizer,
    )

    assert (
        "session_journals"
        in inspect.signature(
            AIExecutionEvidenceFinalizer
        ).parameters
    )

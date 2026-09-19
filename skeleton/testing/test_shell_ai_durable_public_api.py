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
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchivedNode,
    DurableArchivedNodeType,
    DurableArchiveHead,
    DurableArchiveRepository,
    DurableArchiveRootIndex,
    DurableArchiveRootReplica,
    DurableArchiveRootResolution,
    DurableArchiveStoreError,
    DurableArchiveStoreReport,
    StoredDurableArchive,
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


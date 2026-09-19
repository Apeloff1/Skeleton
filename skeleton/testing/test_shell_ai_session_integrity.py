"""Session-scoped journal and receipt inclusion verification tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.session_evidence import (
    SessionExecutionEvidence,
    SessionReceiptEvidence,
)
from skeleton.shells.ai.session_integrity import (
    JournalInclusionResult,
    ReceiptInclusionResult,
    SessionEvidenceIntegrityError,
    SessionEvidenceIntegrityReport,
    SessionEvidenceIntegrityVerifier,
)
from skeleton.shells.ai.session_journal import (
    SessionJournalEvidence,
    SessionJournalEvent,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import (
    ExecutionReceipt,
    ReceiptChain,
)


def fp(char: str) -> str:
    return char * 64


def receipt(
    name: str,
    *,
    correlation_id="corr",
    fingerprint=None,
    returncode=0,
    attempt=1,
    receipt_id=None,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=correlation_id,
        fingerprint=fingerprint or fp("a"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=returncode,
        ok=returncode == 0,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=attempt,
        receipt_id=receipt_id or f"receipt-{name}",
    )


def local_fixture():
    journal = AIDecisionJournal(
        clock=lambda: 10.0,
    )
    first = journal.append(
        "ai.plan.proposed",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
        summary="proposed",
    )
    second = journal.append(
        "ai.plan.completed",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
        summary="completed",
    )
    journal_evidence = SessionJournalEvidence.from_journal(
        journal,
        "session",
    )

    receipts = ReceiptChain()
    one = receipt(
        "one",
        fingerprint=fp("a"),
        attempt=1,
    )
    two = receipt(
        "two",
        fingerprint=fp("b"),
        attempt=2,
    )
    receipts.append(one)
    receipts.append(two)
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (
            SessionReceiptEvidence(
                "step",
                "corr",
                (one.receipt_id, two.receipt_id),
                (one.fingerprint, two.fingerprint),
                (one.returncode, two.returncode),
                2,
                True,
            ),
        ),
    )
    return (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        first,
        second,
        one,
        two,
    )


def test_valid_local_session_inclusion():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        execution_evidence,
    )
    assert report.ok
    assert report.issues == ()
    assert report.journal_chain_ok
    assert report.receipt_chain_ok
    assert report.journal_root == journal.root_hash()
    assert report.receipt_root == receipts.root_hash()
    assert len(report.journal_inclusions) == 2
    assert len(report.receipt_inclusions) == 2
    assert all(
        item.valid
        for item in report.journal_inclusions
    )
    assert all(
        item.valid
        for item in report.receipt_inclusions
    )


def test_require_returns_verified_report():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    verifier = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    )
    report = verifier.require(
        journal_evidence,
        execution_evidence,
    )
    assert report.ok
    assert len(report.digest) == 64


def test_missing_journal_sequence_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    missing = SessionJournalEvidence(
        "session",
        (
            replace(
                journal_evidence.events[0],
                global_sequence=99,
            ),
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        missing,
        execution_evidence,
    )
    assert not report.ok
    assert not report.journal_inclusions[0].found
    assert "missing" in report.issues[0]


def test_journal_hash_substitution_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    bad_event = replace(
        journal_evidence.events[0],
        event_hash=fp("f"),
    )
    bad = SessionJournalEvidence(
        "session",
        (bad_event, journal_evidence.events[1]),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        bad,
        execution_evidence,
    )
    assert not report.ok
    assert report.journal_inclusions[0].found
    assert not report.journal_inclusions[0].valid
    assert "hash mismatch" in report.journal_inclusions[0].reason


def test_journal_kind_substitution_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    bad = SessionJournalEvidence(
        "session",
        (
            replace(
                journal_evidence.events[0],
                kind="different",
            ),
            journal_evidence.events[1],
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        bad,
        execution_evidence,
    )
    assert not report.ok
    assert "kind mismatch" in report.journal_inclusions[0].reason


def test_journal_proposal_substitution_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    bad = SessionJournalEvidence(
        "session",
        (
            replace(
                journal_evidence.events[0],
                proposal_id="other",
            ),
            journal_evidence.events[1],
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        bad,
        execution_evidence,
    )
    assert not report.ok
    assert "proposal id mismatch" in report.journal_inclusions[0].reason


def test_journal_event_from_other_session_is_rejected():
    journal = AIDecisionJournal(
        clock=lambda: 10.0,
    )
    foreign = journal.append(
        "event",
        session_id="other",
        intent_id="intent",
        proposal_id="proposal",
    )
    journal_evidence = SessionJournalEvidence(
        "session",
        (
            SessionJournalEvent(
                foreign.sequence,
                foreign.event_hash,
                foreign.kind,
                foreign.proposal_id,
            ),
        ),
    )
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        ReceiptChain(),
    ).verify(
        journal_evidence,
        execution_evidence,
    )
    assert not report.ok
    assert "session id mismatch" in report.journal_inclusions[0].reason


def test_empty_session_journal_fails_closed_by_default():
    journal = AIDecisionJournal()
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        ReceiptChain(),
    ).verify(
        SessionJournalEvidence("session", ()),
        execution_evidence,
    )
    assert not report.ok
    assert "no events" in report.issues[0]


def test_empty_session_journal_can_be_allowed_explicitly():
    journal = AIDecisionJournal()
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        ReceiptChain(),
        require_session_journal=False,
    ).verify(
        SessionJournalEvidence("session", ()),
        execution_evidence,
    )
    assert report.ok


def test_missing_receipt_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    bad_step = replace(
        execution_evidence.steps[0],
        receipt_ids=(
            "missing",
            execution_evidence.steps[0].receipt_ids[1],
        ),
    )
    bad = replace(
        execution_evidence,
        steps=(bad_step,),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        bad,
    )
    assert not report.ok
    assert not report.receipt_inclusions[0].found
    assert "missing" in report.receipt_inclusions[0].reason


def test_receipt_fingerprint_substitution_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    step = execution_evidence.steps[0]
    bad_step = replace(
        step,
        receipt_fingerprints=(
            fp("f"),
            step.receipt_fingerprints[1],
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        replace(
            execution_evidence,
            steps=(bad_step,),
        ),
    )
    assert not report.ok
    assert "fingerprint mismatch" in report.receipt_inclusions[0].reason


def test_receipt_correlation_substitution_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    bad_step = replace(
        execution_evidence.steps[0],
        correlation_id="other",
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        replace(
            execution_evidence,
            steps=(bad_step,),
        ),
    )
    assert not report.ok
    assert "correlation id mismatch" in report.receipt_inclusions[0].reason


def test_receipt_returncode_substitution_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    step = execution_evidence.steps[0]
    bad_step = replace(
        step,
        returncodes=(
            99,
            step.returncodes[1],
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        replace(
            execution_evidence,
            steps=(bad_step,),
        ),
    )
    assert not report.ok
    assert "returncode mismatch" in report.receipt_inclusions[0].reason


def test_receipt_attempt_order_substitution_is_rejected():
    journal = AIDecisionJournal(
        clock=lambda: 1.0,
    )
    journal.append(
        "event",
        session_id="session",
        intent_id="intent",
    )
    journal_evidence = SessionJournalEvidence.from_journal(
        journal,
        "session",
    )
    receipts = ReceiptChain()
    value = receipt(
        "wrong-attempt",
        attempt=2,
    )
    receipts.append(value)
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (
            SessionReceiptEvidence(
                "step",
                "corr",
                (value.receipt_id,),
                (value.fingerprint,),
                (value.returncode,),
                1,
                True,
            ),
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        execution_evidence,
    )
    assert not report.ok
    assert "attempt number mismatch" in report.receipt_inclusions[0].reason


def test_duplicate_receipt_id_in_committed_chain_is_rejected():
    (
        journal,
        _,
        journal_evidence,
        execution_evidence,
        _,
        _,
        one,
        _,
    ) = local_fixture()
    receipts = ReceiptChain()
    receipts.append(one)
    receipts.append(
        replace(
            one,
            metadata={"copy": True},
        )
    )
    one_step = SessionReceiptEvidence(
        "step",
        "corr",
        (one.receipt_id,),
        (one.fingerprint,),
        (one.returncode,),
        1,
        True,
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        replace(
            execution_evidence,
            steps=(one_step,),
        ),
    )
    assert not report.ok
    assert "multiple times" in report.receipt_inclusions[0].reason


def test_zero_attempt_step_requires_no_receipt():
    (
        journal,
        receipts,
        journal_evidence,
        _,
        *_,
    ) = local_fixture()
    evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        False,
        (
            SessionReceiptEvidence(
                "skipped",
                "",
                (),
                (),
                (),
                0,
                False,
            ),
        ),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        evidence,
    )
    assert report.ok
    assert report.receipt_inclusions == ()


def test_expected_journal_root_mismatch_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        execution_evidence,
        expected_journal_root=fp("f"),
    )
    assert not report.ok
    assert any(
        "journal root differs" in issue
        for issue in report.issues
    )


def test_expected_receipt_root_mismatch_is_rejected():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).verify(
        journal_evidence,
        execution_evidence,
        expected_receipt_root=fp("f"),
    )
    assert not report.ok
    assert any(
        "receipt root differs" in issue
        for issue in report.issues
    )


def test_expected_current_roots_are_accepted():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        journal_evidence,
        execution_evidence,
        expected_journal_root=journal.root_hash(),
        expected_receipt_root=receipts.root_hash(),
    )
    assert report.ok


def test_require_raises_first_integrity_issue():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    bad = replace(
        execution_evidence,
        steps=(
            replace(
                execution_evidence.steps[0],
                correlation_id="bad",
            ),
        ),
    )
    with pytest.raises(
        SessionEvidenceIntegrityError,
        match="correlation",
    ):
        SessionEvidenceIntegrityVerifier(
            journal,
            receipts,
        ).require(
            journal_evidence,
            bad,
        )


def test_session_identity_mismatch_is_rejected_before_chain_scan():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    with pytest.raises(
        ValueError,
        match="identity mismatch",
    ):
        SessionEvidenceIntegrityVerifier(
            journal,
            receipts,
        ).verify(
            journal_evidence,
            replace(
                execution_evidence,
                session_id="other",
            ),
        )


def test_verify_type_validation():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    verifier = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    )
    with pytest.raises(TypeError, match="session_journal"):
        verifier.verify(
            object(),
            execution_evidence,
        )
    with pytest.raises(TypeError, match="session_evidence"):
        verifier.verify(
            journal_evidence,
            object(),
        )


class MissingSurface:
    pass


@pytest.mark.parametrize(
    "name,value",
    [
        ("journal", MissingSurface()),
        ("receipt_chain", MissingSurface()),
    ],
)
def test_constructor_requires_chain_surface(name, value):
    journal = AIDecisionJournal()
    receipts = ReceiptChain()
    kwargs = {
        "journal": journal,
        "receipt_chain": receipts,
    }
    kwargs[name] = value
    with pytest.raises(TypeError, match=name):
        SessionEvidenceIntegrityVerifier(**kwargs)


def test_require_session_journal_must_be_bool():
    with pytest.raises(ValueError, match="bool"):
        SessionEvidenceIntegrityVerifier(
            AIDecisionJournal(),
            ReceiptChain(),
            require_session_journal="yes",
        )


def test_report_digest_is_deterministic():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    verifier = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    )
    first = verifier.require(
        journal_evidence,
        execution_evidence,
    )
    second = verifier.require(
        journal_evidence,
        execution_evidence,
    )
    assert first.digest == second.digest
    assert first == second


def test_report_digest_changes_when_global_root_advances():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    verifier = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    )
    first = verifier.require(
        journal_evidence,
        execution_evidence,
    )
    journal.append(
        "other",
        session_id="other",
        intent_id="other",
    )
    second = verifier.require(
        journal_evidence,
        execution_evidence,
    )
    assert second.ok
    assert second.digest != first.digest
    assert second.journal_root != first.journal_root


def test_unrelated_receipt_does_not_break_inclusion():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    receipts.append(
        receipt(
            "other",
            correlation_id="other",
        )
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        journal_evidence,
        execution_evidence,
    )
    assert report.ok
    assert len(report.receipt_inclusions) == 2


def test_unrelated_journal_event_does_not_break_inclusion():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    journal.append(
        "other",
        session_id="other",
        intent_id="other",
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        journal_evidence,
        execution_evidence,
    )
    assert report.ok
    assert len(report.journal_inclusions) == 2


def test_distributed_chains_are_drop_in_compatible():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    journal.append(
        "ai.plan.proposed",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    journal.append(
        "ai.plan.completed",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    journal_evidence = SessionJournalEvidence.from_journal(
        journal,
        "session",
    )

    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    value = receipt("distributed")
    receipts.append(value)
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (
            SessionReceiptEvidence(
                "step",
                value.correlation_id,
                (value.receipt_id,),
                (value.fingerprint,),
                (value.returncode,),
                1,
                True,
            ),
        ),
    )

    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        journal_evidence,
        execution_evidence,
    )
    assert report.ok
    assert report.journal_root == journal.root_hash()
    assert report.receipt_root == receipts.root_hash()
    assert report.receipt_inclusions[0].global_sequence == 1


def test_fresh_distributed_readers_verify_same_session():
    backend = InMemoryFencedStore()
    journal_writer = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    journal_writer.append(
        "event",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
    )
    journal_evidence = SessionJournalEvidence.from_journal(
        journal_writer,
        "session",
    )

    receipt_writer = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    value = receipt("fresh")
    receipt_writer.append(value)
    execution_evidence = SessionExecutionEvidence(
        1,
        "session",
        "plan",
        fp("p"),
        True,
        (
            SessionReceiptEvidence(
                "step",
                value.correlation_id,
                (value.receipt_id,),
                (value.fingerprint,),
                (value.returncode,),
                1,
                True,
            ),
        ),
    )

    journal_reader = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    receipt_reader = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    report = SessionEvidenceIntegrityVerifier(
        journal_reader,
        receipt_reader,
    ).require(
        journal_evidence,
        execution_evidence,
    )
    assert report.ok


class InvalidChain:
    def __init__(self, snapshot, root):
        self._snapshot = snapshot
        self._root = root

    def snapshot(self):
        return self._snapshot

    def verify(self):
        return False

    def root_hash(self):
        return self._root


def test_invalid_global_journal_chain_is_rejected_even_if_manifest_matches():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    invalid = InvalidChain(
        journal.snapshot(),
        journal.root_hash(),
    )
    report = SessionEvidenceIntegrityVerifier(
        invalid,
        receipts,
    ).verify(
        journal_evidence,
        execution_evidence,
    )
    assert not report.ok
    assert not report.journal_chain_ok
    assert any(
        "journal chain failed" in issue
        for issue in report.issues
    )


def test_invalid_global_receipt_chain_is_rejected_even_if_manifest_matches():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    invalid = InvalidChain(
        receipts.snapshot(),
        receipts.root_hash(),
    )
    report = SessionEvidenceIntegrityVerifier(
        journal,
        invalid,
    ).verify(
        journal_evidence,
        execution_evidence,
    )
    assert not report.ok
    assert not report.receipt_chain_ok
    assert any(
        "receipt chain failed" in issue
        for issue in report.issues
    )


def test_report_to_dict_contains_digest_and_manifests():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        journal_evidence,
        execution_evidence,
    )
    data = report.to_dict()
    assert data["ok"] is True
    assert data["digest"] == report.digest
    assert (
        data["journal_manifest_digest"]
        == report.journal_manifest_digest
    )
    assert (
        data["receipt_manifest_digest"]
        == report.receipt_manifest_digest
    )
    assert len(data["journal_inclusions"]) == 2
    assert len(data["receipt_inclusions"]) == 2


def test_report_digest_exclusion_avoids_recursive_digest():
    (
        journal,
        receipts,
        journal_evidence,
        execution_evidence,
        *_,
    ) = local_fixture()
    report = SessionEvidenceIntegrityVerifier(
        journal,
        receipts,
    ).require(
        journal_evidence,
        execution_evidence,
    )
    assert "digest" not in report.to_dict(
        include_digest=False
    )


def test_journal_inclusion_validation():
    with pytest.raises(ValueError):
        JournalInclusionResult(
            0,
            fp("a"),
            "event",
            "",
            True,
            True,
        )
    with pytest.raises(ValueError):
        JournalInclusionResult(
            1,
            "bad",
            "event",
            "",
            True,
            True,
        )
    with pytest.raises(ValueError):
        JournalInclusionResult(
            1,
            fp("a"),
            "",
            "",
            True,
            True,
        )
    with pytest.raises(ValueError):
        JournalInclusionResult(
            1,
            fp("a"),
            "event",
            "",
            False,
            True,
        )


def test_receipt_inclusion_validation():
    base = dict(
        step_id="step",
        correlation_id="corr",
        attempt=1,
        receipt_id="receipt",
        fingerprint=fp("a"),
        returncode=0,
        global_sequence=1,
        found=True,
        valid=True,
    )
    with pytest.raises(ValueError):
        ReceiptInclusionResult(
            **{**base, "step_id": ""}
        )
    with pytest.raises(ValueError):
        ReceiptInclusionResult(
            **{**base, "attempt": 0}
        )
    with pytest.raises(ValueError):
        ReceiptInclusionResult(
            **{**base, "receipt_id": ""}
        )
    with pytest.raises(ValueError):
        ReceiptInclusionResult(
            **{**base, "fingerprint": "bad"}
        )
    with pytest.raises(ValueError):
        ReceiptInclusionResult(
            **{
                **base,
                "found": False,
                "valid": True,
            }
        )


def test_integrity_report_validation():
    journal_item = JournalInclusionResult(
        1,
        fp("a"),
        "event",
        "",
        True,
        True,
    )
    receipt_item = ReceiptInclusionResult(
        "step",
        "corr",
        1,
        "receipt",
        fp("b"),
        0,
        1,
        True,
        True,
    )
    with pytest.raises(ValueError):
        SessionEvidenceIntegrityReport(
            "",
            True,
            True,
            fp("j"),
            fp("r"),
            fp("a"),
            fp("b"),
            (journal_item,),
            (receipt_item,),
            (),
        )
    with pytest.raises(ValueError):
        SessionEvidenceIntegrityReport(
            "session",
            True,
            True,
            "bad",
            fp("r"),
            fp("a"),
            fp("b"),
            (journal_item,),
            (receipt_item,),
            (),
        )

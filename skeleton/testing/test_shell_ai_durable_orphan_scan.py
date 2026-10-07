"""Durable orphan scanner classification and safety tests."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_orphan_scan import (
    DurableOrphanNodeKind,
    DurableOrphanRecordState,
    DurableOrphanScanError,
    DurableOrphanScanPolicy,
    DurableOrphanScanner,
)
from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


GENESIS = "0" * 64


def fp(char: str) -> str:
    return char * 64


def receipt(
    name: str,
    *,
    receipt_id: str | None = None,
    fingerprint: str | None = None,
    correlation_id: str = "correlation",
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=correlation_id,
        fingerprint=fingerprint or fp("a"),
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
        receipt_id=receipt_id or f"receipt-{name}",
        metadata={"name": name},
    )


def committed_journal(
    *,
    backend=None,
    namespace="journal",
):
    backend = backend or InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace=namespace,
        clock=lambda: 10.0,
    )
    event = journal.append(
        "committed",
        session_id="session",
        intent_id="intent",
        proposal_id="proposal",
        summary="committed",
    )
    return backend, journal, event


def committed_receipts(
    *,
    backend=None,
    namespace="receipts",
):
    backend = backend or InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace=namespace,
    )
    item = chain.append(receipt("committed"))
    return backend, chain, item


def orphan_event(
    journal: DistributedAIDecisionJournal,
    *,
    kind="orphan",
    session_id="orphan-session",
    observed_at=11.0,
    sequence=1,
    previous_hash=GENESIS,
) -> AIDecisionEvent:
    payload = MappingProxyType({"orphan": True})
    digest = AIDecisionJournal._hash(
        previous_hash,
        sequence,
        kind,
        observed_at,
        session_id,
        "orphan-intent",
        "orphan-proposal",
        "orphan",
        payload,
    )
    event = AIDecisionEvent(
        sequence,
        previous_hash,
        digest,
        kind,
        observed_at,
        session_id,
        "orphan-intent",
        "orphan-proposal",
        "orphan",
        payload,
    )
    journal.backend.put_if_absent(
        journal.namespace,
        journal._event_key(digest),
        event,
    )
    return event


def orphan_receipt(
    chain: DistributedReceiptChain,
    *,
    name="orphan",
    sequence=1,
    previous_hash=GENESIS,
) -> ChainedReceipt:
    value = receipt(
        name,
        receipt_id=f"receipt-{name}",
        fingerprint=fp("b"),
        correlation_id="orphan-correlation",
    )
    digest = ReceiptChain._hash(
        previous_hash,
        sequence,
        value,
    )
    item = ChainedReceipt(
        sequence,
        previous_hash,
        digest,
        value,
    )
    chain.backend.put_if_absent(
        chain.namespace,
        chain._node_key(digest),
        item,
    )
    return item


def fixed_scanner(**policy):
    return DurableOrphanScanner(
        policy=DurableOrphanScanPolicy(
            **policy
        ),
        clock=lambda: 50.0,
    )


def test_clean_journal_has_no_orphans():
    _, journal, _ = committed_journal()
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.healthy
    assert report.orphan_candidates == 0
    assert report.index_conflicts == 0
    assert report.corrupt == 0
    assert report.safe_delete_candidates == ()
    assert report.node_kind is DurableOrphanNodeKind.JOURNAL_EVENT


def test_clean_receipt_chain_has_no_orphans():
    _, chain, _ = committed_receipts()
    report = fixed_scanner().scan(
        "receipt-chain",
        chain,
    )
    assert report.healthy
    assert report.orphan_candidates == 0
    assert report.node_kind is DurableOrphanNodeKind.RECEIPT_NODE


def test_reachable_records_are_hidden_by_default():
    _, journal, committed = committed_journal()
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.records == ()
    assert report.node_records_inspected == 1
    assert committed.event_hash == journal.root_hash()


def test_reachable_records_can_be_included():
    _, journal, committed = committed_journal()
    scanner = fixed_scanner(
        include_reachable=True,
    )
    report = scanner.scan(
        "journal-chain",
        journal,
    )
    assert len(report.records) == 1
    item = report.records[0]
    assert item.node_hash == committed.event_hash
    assert item.state is DurableOrphanRecordState.REACHABLE
    assert not item.safe_to_delete


def test_unreachable_journal_candidate_is_delete_safe():
    _, journal, committed = committed_journal()
    orphan = orphan_event(journal)
    assert orphan.event_hash != committed.event_hash

    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.healthy
    assert report.orphan_candidates == 1
    assert len(report.safe_delete_candidates) == 1
    candidate = report.safe_delete_candidates[0]
    assert candidate.node_hash == orphan.event_hash
    assert candidate.sequence == 1
    assert candidate.state is DurableOrphanRecordState.ORPHAN_CANDIDATE
    assert candidate.safe_to_delete
    assert candidate.sequence_index_hash == committed.event_hash
    assert "unreachable" in candidate.reasons[0]


def test_unreachable_receipt_candidate_is_delete_safe():
    _, chain, committed = committed_receipts()
    orphan = orphan_receipt(chain)
    assert orphan.receipt_hash != committed.receipt_hash

    report = fixed_scanner().scan(
        "receipt-chain",
        chain,
    )
    assert report.healthy
    assert report.orphan_candidates == 1
    candidate = report.safe_delete_candidates[0]
    assert candidate.node_hash == orphan.receipt_hash
    assert candidate.sequence_index_hash == committed.receipt_hash
    assert candidate.safe_to_delete


def test_sequence_index_pointing_to_orphan_requires_manual_review():
    backend, journal, committed = committed_journal()
    orphan = orphan_event(journal)
    key = journal._sequence_key(1)
    record = backend.get(
        journal.namespace,
        key,
    )
    backend.compare_and_swap(
        journal.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            orphan.event_hash,
        ),
    )

    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.requires_manual_review
    assert report.index_conflicts == 1
    candidate = report.records[0]
    assert candidate.state is DurableOrphanRecordState.INDEX_CONFLICT
    assert not candidate.safe_to_delete
    assert candidate.sequence_index_hash == orphan.event_hash
    assert candidate.node_hash != committed.event_hash


def test_receipt_sequence_index_pointing_to_orphan_requires_manual_review():
    backend, chain, _ = committed_receipts()
    orphan = orphan_receipt(chain)
    key = chain._sequence_key(1)
    record = backend.get(
        chain.namespace,
        key,
    )
    backend.compare_and_swap(
        chain.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            orphan.receipt_hash,
        ),
    )
    report = fixed_scanner().scan(
        "receipt-chain",
        chain,
    )
    assert report.requires_manual_review
    assert report.index_conflicts == 1
    assert report.records[0].state is DurableOrphanRecordState.INDEX_CONFLICT


def test_future_sequence_journal_node_is_corrupt_not_gc_candidate():
    _, journal, committed = committed_journal()
    future = orphan_event(
        journal,
        sequence=2,
        previous_hash=committed.event_hash,
    )
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.requires_manual_review
    assert report.corrupt == 1
    item = report.records[0]
    assert item.node_hash == future.event_hash
    assert item.state is DurableOrphanRecordState.CORRUPT
    assert not item.safe_to_delete
    assert any(
        "ahead of committed head" in reason
        for reason in item.reasons
    )


def test_future_sequence_receipt_node_is_corrupt_not_gc_candidate():
    _, chain, committed = committed_receipts()
    future = orphan_receipt(
        chain,
        sequence=2,
        previous_hash=committed.receipt_hash,
    )
    report = fixed_scanner().scan(
        "receipt-chain",
        chain,
    )
    assert report.corrupt == 1
    assert report.records[0].node_hash == future.receipt_hash
    assert not report.records[0].safe_to_delete


def test_wrong_journal_node_type_is_corrupt():
    backend, journal, _ = committed_journal()
    backend.put_if_absent(
        journal.namespace,
        "event:" + fp("f"),
        {"bad": True},
    )
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.corrupt == 1
    item = report.records[0]
    assert item.state is DurableOrphanRecordState.CORRUPT
    assert not item.safe_to_delete
    assert any(
        "unexpected value type" in reason
        for reason in item.reasons
    )


def test_wrong_receipt_node_type_is_corrupt():
    backend, chain, _ = committed_receipts()
    backend.put_if_absent(
        chain.namespace,
        "node:" + fp("f"),
        {"bad": True},
    )
    report = fixed_scanner().scan(
        "receipt-chain",
        chain,
    )
    assert report.corrupt == 1
    assert report.requires_manual_review


def test_backend_key_hash_mismatch_is_corrupt():
    backend, journal, _ = committed_journal()
    orphan = orphan_event(journal)
    original = backend.get(
        journal.namespace,
        journal._event_key(orphan.event_hash),
    )
    backend.put_if_absent(
        journal.namespace,
        "event:" + fp("e"),
        orphan,
    )
    report = fixed_scanner(
        include_reachable=True,
    ).scan(
        "journal-chain",
        journal,
    )
    corrupt = [
        item
        for item in report.records
        if item.backend_key == "event:" + fp("e")
    ]
    assert len(corrupt) == 1
    assert corrupt[0].state is DurableOrphanRecordState.CORRUPT
    assert not corrupt[0].safe_to_delete
    assert original is not None


def test_corrupted_node_content_is_manual_review():
    backend, journal, _ = committed_journal()
    orphan = orphan_event(journal)
    key = journal._event_key(
        orphan.event_hash
    )
    record = backend.get(
        journal.namespace,
        key,
    )
    backend.compare_and_swap(
        journal.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            orphan,
            summary="tampered",
        ),
    )
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.corrupt == 1
    assert any(
        "integrity verification failed" in reason
        for reason in report.records[0].reasons
    )


def test_candidate_count_bound_fails_closed():
    _, journal, _ = committed_journal()
    for index in range(3):
        orphan_event(
            journal,
            kind=f"orphan-{index}",
            session_id=f"orphan-{index}",
            observed_at=20.0 + index,
        )
    scanner = fixed_scanner(
        max_candidates=2,
    )
    with pytest.raises(
        DurableOrphanScanError,
        match="candidate count",
    ):
        scanner.scan(
            "journal-chain",
            journal,
        )


def test_candidate_count_can_truncate_when_policy_allows():
    _, journal, _ = committed_journal()
    for index in range(3):
        orphan_event(
            journal,
            kind=f"orphan-{index}",
            session_id=f"orphan-{index}",
            observed_at=20.0 + index,
        )
    scanner = fixed_scanner(
        max_candidates=2,
        fail_on_candidate_overflow=False,
    )
    report = scanner.scan(
        "journal-chain",
        journal,
    )
    assert report.truncated
    assert report.requires_manual_review


def test_record_bound_marks_scan_truncated():
    backend, journal, _ = committed_journal()
    for index in range(5):
        backend.put_if_absent(
            journal.namespace,
            f"metadata:{index}",
            {"value": index},
        )
    scanner = fixed_scanner(
        max_records=2,
    )
    report = scanner.scan(
        "journal-chain",
        journal,
    )
    assert report.truncated
    assert report.backend_records_inspected == 2
    assert report.requires_manual_review


class NonListingBackend:
    def __init__(self):
        self.delegate = InMemoryFencedStore()

    def get(self, namespace, key):
        return self.delegate.get(
            namespace,
            key,
        )

    def put_if_absent(self, namespace, key, value):
        return self.delegate.put_if_absent(
            namespace,
            key,
            value,
        )

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        return self.delegate.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        return self.delegate.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_scanner_requires_explicit_listing_capability():
    backend = NonListingBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    journal.append(
        "event",
        session_id="session",
        intent_id="intent",
    )
    with pytest.raises(
        DurableOrphanScanError,
        match="record listing",
    ):
        fixed_scanner().scan(
            "journal-chain",
            journal,
        )


def test_scanner_rejects_unsupported_chain_type():
    with pytest.raises(
        TypeError,
        match="Distributed",
    ):
        fixed_scanner().scan(
            "chain",
            object(),
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129],
)
def test_chain_id_validation(chain_id):
    _, journal, _ = committed_journal()
    with pytest.raises(ValueError, match="chain_id"):
        fixed_scanner().scan(
            chain_id,
            journal,
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("max_records", 0),
        ("max_records", True),
        ("max_candidates", 0),
        ("max_candidates", True),
    ],
)
def test_policy_integer_validation(name, value):
    with pytest.raises(ValueError):
        DurableOrphanScanPolicy(
            **{name: value}
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("fail_on_candidate_overflow", 1),
        ("include_reachable", "yes"),
        ("include_compacted_retained", None),
    ],
)
def test_policy_boolean_validation(name, value):
    with pytest.raises(ValueError, match="bool"):
        DurableOrphanScanPolicy(
            **{name: value}
        )


def test_policy_digest_is_stable():
    first = DurableOrphanScanPolicy()
    second = DurableOrphanScanPolicy()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_report_digest_is_stable_with_fixed_clock():
    _, journal, _ = committed_journal()
    orphan_event(journal)
    scanner = fixed_scanner()
    first = scanner.scan(
        "journal-chain",
        journal,
    )
    second = scanner.scan(
        "journal-chain",
        journal,
    )
    assert first.digest == second.digest
    assert first == second


def test_report_digest_changes_when_orphan_set_changes():
    _, journal, _ = committed_journal()
    scanner = fixed_scanner()
    before = scanner.scan(
        "journal-chain",
        journal,
    )
    orphan_event(journal)
    after = scanner.scan(
        "journal-chain",
        journal,
    )
    assert after.digest != before.digest


def test_fresh_reader_produces_same_scan():
    backend, journal, _ = committed_journal()
    orphan_event(journal)
    first = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    fresh = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 99.0,
    )
    second = fixed_scanner().scan(
        "journal-chain",
        fresh,
    )
    assert second.digest == first.digest
    assert second.records == first.records


def test_require_clean_allows_orphans_by_default():
    _, journal, _ = committed_journal()
    orphan_event(journal)
    report = fixed_scanner().require_clean(
        "journal-chain",
        journal,
    )
    assert report.orphan_candidates == 1
    assert report.healthy


def test_require_clean_can_forbid_orphans():
    _, journal, _ = committed_journal()
    orphan_event(journal)
    with pytest.raises(
        DurableOrphanScanError,
        match="candidates",
    ):
        fixed_scanner().require_clean(
            "journal-chain",
            journal,
            allow_orphans=False,
        )


def test_require_clean_rejects_manual_review_state():
    backend, journal, _ = committed_journal()
    orphan = orphan_event(journal)
    key = journal._sequence_key(1)
    record = backend.get(
        journal.namespace,
        key,
    )
    backend.compare_and_swap(
        journal.namespace,
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            orphan.event_hash,
        ),
    )
    with pytest.raises(
        DurableOrphanScanError,
        match="manual review",
    ):
        fixed_scanner().require_clean(
            "journal-chain",
            journal,
        )


def test_report_serialization_contains_counts_and_digest():
    _, journal, _ = committed_journal()
    orphan_event(journal)
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    data = report.to_dict()
    assert data["chain_id"] == "journal-chain"
    assert data["orphan_candidates"] == 1
    assert data["safe_delete_candidates"] == 1
    assert data["requires_manual_review"] is False
    assert data["digest"] == report.digest


def test_record_identity_digest_binds_backend_revision():
    _, journal, _ = committed_journal()
    orphan_event(journal)
    item = fixed_scanner().scan(
        "journal-chain",
        journal,
    ).records[0]
    changed = replace(
        item,
        backend_revision=item.backend_revision + 1,
    )
    assert changed.identity_digest != item.identity_digest


def test_record_identity_digest_binds_node_hash():
    _, journal, _ = committed_journal()
    orphan_event(journal)
    item = fixed_scanner().scan(
        "journal-chain",
        journal,
    ).records[0]
    changed = replace(
        item,
        node_hash=fp("f"),
    )
    assert changed.identity_digest != item.identity_digest


def test_safe_delete_requires_orphan_state():
    _, journal, _ = committed_journal()
    committed = journal.snapshot()[0]
    with pytest.raises(
        ValueError,
        match="only orphan",
    ):
        from skeleton.shells.ai.durable_orphan_scan import (
            DurableOrphanNodeRecord,
        )

        DurableOrphanNodeRecord(
            "chain",
            DurableOrphanNodeKind.JOURNAL_EVENT,
            DurableOrphanRecordState.REACHABLE,
            journal.namespace,
            journal._event_key(
                committed.event_hash
            ),
            1,
            committed.sequence,
            committed.event_hash,
            committed.previous_hash,
            committed.event_hash,
            True,
            ("bad",),
        )


def test_scan_clock_validation():
    _, journal, _ = committed_journal()
    scanner = DurableOrphanScanner(
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        ValueError,
        match="scan clock",
    ):
        scanner.scan(
            "journal-chain",
            journal,
        )


class CompetingJournalBackend:
    """Inject one committed competitor while preserving the losing candidate."""

    def __init__(self):
        self.store = InMemoryFencedStore()
        self.injected = False

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def records(self, namespace=None):
        return self.store.records(namespace)

    def put_if_absent(self, namespace, key, value):
        return self.store.put_if_absent(
            namespace,
            key,
            value,
        )

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            key == "head"
            and not self.injected
            and expected_revision == 0
        ):
            self.injected = True
            payload = MappingProxyType(
                {"competitor": True}
            )
            digest = AIDecisionJournal._hash(
                GENESIS,
                1,
                "competitor",
                1.0,
                "competitor-session",
                "competitor-intent",
                "",
                "",
                payload,
            )
            event = AIDecisionEvent(
                1,
                GENESIS,
                digest,
                "competitor",
                1.0,
                "competitor-session",
                "competitor-intent",
                "",
                "",
                payload,
            )
            self.store.put_if_absent(
                namespace,
                f"event:{digest}",
                event,
            )
            self.store.compare_and_swap(
                namespace,
                "head",
                expected_revision=0,
                value=type(value)(
                    1,
                    digest,
                ),
            )
            self.store.put_if_absent(
                namespace,
                "sequence:00000000000000000001",
                DistributedJournalSequenceIndex(
                    1,
                    digest,
                ),
            )
            raise DistributedStateConflict(
                "synthetic competing append"
            )
        return self.store.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(
        self,
        namespace,
        key,
        *,
        expected_revision,
    ):
        return self.store.delete(
            namespace,
            key,
            expected_revision=expected_revision,
        )


def test_real_cas_loser_is_detected_as_orphan():
    backend = CompetingJournalBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 2.0,
    )
    ours = journal.append(
        "ours",
        session_id="ours",
        intent_id="intent",
    )
    assert ours.sequence == 2
    report = fixed_scanner().scan(
        "journal-chain",
        journal,
    )
    assert report.orphan_candidates == 1
    orphan = report.safe_delete_candidates[0]
    assert orphan.sequence == 1
    assert orphan.node_hash not in {
        event.event_hash
        for event in journal.snapshot()
    }
    assert orphan.sequence_index_hash != orphan.node_hash


def test_scanner_never_marks_committed_cas_winner_delete_safe():
    backend = CompetingJournalBackend()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 2.0,
    )
    journal.append(
        "ours",
        session_id="ours",
        intent_id="intent",
    )
    report = fixed_scanner(
        include_reachable=True,
    ).scan(
        "journal-chain",
        journal,
    )
    committed_hashes = {
        event.event_hash
        for event in journal.snapshot()
    }
    for item in report.records:
        if item.node_hash in committed_hashes:
            assert item.state is DurableOrphanRecordState.REACHABLE
            assert not item.safe_to_delete

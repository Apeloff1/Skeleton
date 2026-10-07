"""Indexed bounded-tail verification tests for signed durable cursors."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorError,
    DurableVerificationCursorStore,
    DurableVerificationMode,
    DurableVerificationPolicy,
    DurableVerificationStatus,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def make_receipt(index: int) -> ExecutionReceipt:
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
        stdout_bytes=index,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def append_journal(
    chain: DistributedAIDecisionJournal,
    count: int,
    *,
    start: int = 1,
):
    return tuple(
        chain.append(
            "indexed.verify",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
        )
        for index in range(start, start + count)
    )


def append_receipts(
    chain: DistributedReceiptChain,
    count: int,
    *,
    start: int = 1,
):
    return tuple(
        chain.append(
            make_receipt(index)
        )
        for index in range(start, start + count)
    )


def verifier(
    backend,
    *,
    namespace="cursor",
    clock=lambda: 100.0,
    policy=None,
):
    store = DurableVerificationCursorStore(
        backend,
        ArtifactSigner(
            "cursor",
            b"v" * 32,
            clock=clock,
        ),
        namespace=namespace,
    )
    verify = DurableIncrementalVerifier(
        store,
        policy
        or DurableVerificationPolicy(
            max_tail_items=32,
            max_items_between_full_verification=128,
            max_full_verification_age_seconds=3600.0,
        ),
        clock=clock,
    )
    return store, verify


class IndexedJournalView:
    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0
        self.segment_calls = 0
        self.range_calls = 0
        self.root_lookup_calls = 0

    def head(self):
        return self.delegate.head()

    def verify(self):
        self.verify_calls += 1
        return self.delegate.verify()

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        self.segment_calls += 1
        return self.delegate.snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )

    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items=4096,
    ):
        self.range_calls += 1
        return self.delegate.snapshot_range(
            start_sequence,
            end_sequence,
            max_items=max_items,
        )

    def root_for_sequence(self, sequence):
        self.root_lookup_calls += 1
        return self.delegate.root_for_sequence(
            sequence
        )


class IndexedReceiptView:
    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0
        self.segment_calls = 0
        self.range_calls = 0
        self.root_lookup_calls = 0

    def head(self):
        return self.delegate.head()

    def verify(self):
        self.verify_calls += 1
        return self.delegate.verify()

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        self.segment_calls += 1
        return self.delegate.snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )

    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items=4096,
    ):
        self.range_calls += 1
        return self.delegate.snapshot_range(
            start_sequence,
            end_sequence,
            max_items=max_items,
        )

    def root_for_sequence(self, sequence):
        self.root_lookup_calls += 1
        return self.delegate.root_for_sequence(
            sequence
        )


class LegacyView:
    """Expose only the original incremental protocol."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.verify_calls = 0
        self.segment_calls = 0

    def head(self):
        return self.delegate.head()

    def verify(self):
        self.verify_calls += 1
        return self.delegate.verify()

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        self.segment_calls += 1
        return self.delegate.snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )


def test_journal_incremental_verification_uses_indexed_range():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 3)
    view = IndexedJournalView(raw)
    store, verify = verifier(backend)

    bootstrap = verify.require_current(
        "journal",
        view,
    )
    assert bootstrap.valid
    assert (
        bootstrap.cursor.cursor.mode
        is DurableVerificationMode.FULL
    )
    before_full = view.verify_calls

    append_journal(
        raw,
        2,
        start=4,
    )
    result = verify.require_current(
        "journal",
        view,
    )
    assert result.valid
    assert (
        result.report.status
        is DurableVerificationStatus.TAIL_VERIFIED
    )
    assert result.cursor.cursor.mode is DurableVerificationMode.INCREMENTAL
    assert view.range_calls == 1
    assert view.root_lookup_calls == 2
    assert view.segment_calls == 0
    assert view.verify_calls == before_full
    assert result.cursor.cursor.segment_items == 2
    assert store.latest("journal").item == result.cursor


def test_receipt_incremental_verification_uses_indexed_range():
    backend = InMemoryFencedStore()
    raw = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(raw, 3)
    view = IndexedReceiptView(raw)
    _, verify = verifier(
        backend,
        namespace="receipt-cursor",
    )
    verify.require_current(
        "receipts",
        view,
    )
    before_full = view.verify_calls

    append_receipts(
        raw,
        3,
        start=4,
    )
    result = verify.require_current(
        "receipts",
        view,
    )
    assert result.valid
    assert view.range_calls == 1
    assert view.root_lookup_calls == 2
    assert view.segment_calls == 0
    assert view.verify_calls == before_full
    assert result.cursor.cursor.segment_items == 3


def test_legacy_journal_view_keeps_segment_fallback():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    view = LegacyView(raw)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        view,
    )
    append_journal(raw, 1, start=3)
    result = verify.require_current(
        "journal",
        view,
    )
    assert result.valid
    assert view.segment_calls == 1


def test_legacy_receipt_view_keeps_segment_fallback():
    backend = InMemoryFencedStore()
    raw = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(raw, 2)
    view = LegacyView(raw)
    _, verify = verifier(
        backend,
        namespace="receipt-cursor",
    )
    verify.require_current(
        "receipts",
        view,
    )
    append_receipts(raw, 1, start=3)
    result = verify.require_current(
        "receipts",
        view,
    )
    assert result.valid
    assert view.segment_calls == 1


def test_missing_journal_cursor_endpoint_index_self_heals():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 3)
    view = IndexedJournalView(raw)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        view,
    )

    key = raw._sequence_key(3)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    append_journal(raw, 1, start=4)
    result = verify.require_current(
        "journal",
        view,
    )
    assert result.valid
    assert raw._sequence_index(3) is not None
    assert raw.inspect_sequence_indexes().healthy


def test_missing_journal_head_index_self_heals():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    view = IndexedJournalView(raw)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        view,
    )
    append_journal(raw, 2, start=3)
    key = raw._sequence_key(4)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    result = verify.require_current(
        "journal",
        view,
    )
    assert result.valid
    assert raw._sequence_index(4) is not None


def test_missing_receipt_cursor_endpoint_index_self_heals():
    backend = InMemoryFencedStore()
    raw = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(raw, 3)
    view = IndexedReceiptView(raw)
    _, verify = verifier(
        backend,
        namespace="receipt-cursor",
    )
    verify.require_current(
        "receipts",
        view,
    )
    key = raw._sequence_key(3)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    append_receipts(raw, 1, start=4)
    result = verify.require_current(
        "receipts",
        view,
    )
    assert result.valid
    assert raw._sequence_index(3) is not None


def test_corrupt_journal_cursor_index_fails_incremental_verification():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    events = append_journal(raw, 3)
    view = IndexedJournalView(raw)
    store, verify = verifier(backend)
    first = verify.require_current(
        "journal",
        view,
    )
    key = raw._sequence_key(3)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            3,
            events[1].event_hash,
        ),
    )
    append_journal(raw, 1, start=4)

    with pytest.raises(
        DurableVerificationCursorError,
        match="indexed tail root resolution",
    ):
        verify.require_current(
            "journal",
            view,
        )
    assert (
        store.latest("journal").item.cursor.digest
        == first.cursor.cursor.digest
    )


def test_corrupt_journal_head_index_fails_incremental_verification():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    view = IndexedJournalView(raw)
    store, verify = verifier(backend)
    first = verify.require_current(
        "journal",
        view,
    )
    events = append_journal(raw, 2, start=3)
    key = raw._sequence_key(4)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            4,
            events[0].event_hash,
        ),
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="indexed tail root resolution",
    ):
        verify.require_current(
            "journal",
            view,
        )
    assert store.latest("journal").item == first.cursor


def test_corrupt_receipt_cursor_index_fails_incremental_verification():
    backend = InMemoryFencedStore()
    raw = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    items = append_receipts(raw, 3)
    view = IndexedReceiptView(raw)
    store, verify = verifier(
        backend,
        namespace="receipt-cursor",
    )
    first = verify.require_current(
        "receipts",
        view,
    )
    key = raw._sequence_key(3)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            3,
            items[1].receipt_hash,
        ),
    )
    append_receipts(raw, 1, start=4)
    with pytest.raises(
        DurableVerificationCursorError,
        match="indexed tail root resolution",
    ):
        verify.require_current(
            "receipts",
            view,
        )
    assert (
        store.latest("receipts").item.cursor.digest
        == first.cursor.cursor.digest
    )


def test_corrupt_receipt_head_index_fails_incremental_verification():
    backend = InMemoryFencedStore()
    raw = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(raw, 2)
    view = IndexedReceiptView(raw)
    store, verify = verifier(
        backend,
        namespace="receipt-cursor",
    )
    first = verify.require_current(
        "receipts",
        view,
    )
    items = append_receipts(raw, 2, start=3)
    key = raw._sequence_key(4)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            4,
            items[0].receipt_hash,
        ),
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="indexed tail root resolution",
    ):
        verify.require_current(
            "receipts",
            view,
        )
    assert store.latest("receipts").item == first.cursor


class RootMismatchView(IndexedJournalView):
    def root_for_sequence(self, sequence):
        self.root_lookup_calls += 1
        if sequence == self.delegate.head().sequence:
            return fp("wrong-head")
        return self.delegate.root_for_sequence(
            sequence
        )


def test_indexed_head_root_mismatch_fails_closed():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    bootstrap_view = IndexedJournalView(raw)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        bootstrap_view,
    )
    append_journal(raw, 1, start=3)
    bad = RootMismatchView(raw)
    with pytest.raises(
        DurableVerificationCursorError,
        match="live head root",
    ):
        verify.require_current(
            "journal",
            bad,
        )


class CursorMismatchView(IndexedJournalView):
    def __init__(self, delegate, cursor_sequence):
        super().__init__(delegate)
        self.cursor_sequence = cursor_sequence

    def root_for_sequence(self, sequence):
        self.root_lookup_calls += 1
        if sequence == self.cursor_sequence:
            return fp("wrong-cursor")
        return self.delegate.root_for_sequence(
            sequence
        )


def test_indexed_cursor_root_mismatch_fails_closed():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    base = IndexedJournalView(raw)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        base,
    )
    append_journal(raw, 1, start=3)
    bad = CursorMismatchView(
        raw,
        2,
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="signed cursor root",
    ):
        verify.require_current(
            "journal",
            bad,
        )


class ShortRangeView(IndexedJournalView):
    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items=4096,
    ):
        values = super().snapshot_range(
            start_sequence,
            end_sequence,
            max_items=max_items,
        )
        return values[:-1]


def test_short_indexed_range_fails_closed():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    append_journal(raw, 2, start=3)
    with pytest.raises(
        DurableVerificationCursorError,
        match="length",
    ):
        verify.require_current(
            "journal",
            ShortRangeView(raw),
        )


class ShiftedRangeView(IndexedJournalView):
    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items=4096,
    ):
        values = super().snapshot_range(
            start_sequence,
            end_sequence,
            max_items=max_items,
        )
        if not values:
            return values
        return (
            replace(
                values[0],
                sequence=values[0].sequence + 10,
            ),
            *values[1:],
        )


def test_shifted_indexed_range_fails_closed():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    append_journal(raw, 1, start=3)
    with pytest.raises(
        DurableVerificationCursorError,
        match="sequence bounds",
    ):
        verify.require_current(
            "journal",
            ShiftedRangeView(raw),
        )


class PreviousHashMismatchView(IndexedJournalView):
    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items=4096,
    ):
        values = super().snapshot_range(
            start_sequence,
            end_sequence,
            max_items=max_items,
        )
        return (
            replace(
                values[0],
                previous_hash=fp("wrong"),
            ),
            *values[1:],
        )


def test_previous_hash_mismatch_fails_closed():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    append_journal(raw, 1, start=3)
    with pytest.raises(
        DurableVerificationCursorError,
        match="signed cursor root",
    ):
        verify.require_current(
            "journal",
            PreviousHashMismatchView(raw),
        )


class TerminalHashMismatchView(IndexedJournalView):
    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items=4096,
    ):
        values = super().snapshot_range(
            start_sequence,
            end_sequence,
            max_items=max_items,
        )
        return (
            *values[:-1],
            replace(
                values[-1],
                event_hash=fp("wrong-terminal"),
            ),
        )


def test_terminal_hash_mismatch_fails_closed():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    append_journal(raw, 1, start=3)
    with pytest.raises(
        DurableVerificationCursorError,
        match="live head root",
    ):
        verify.require_current(
            "journal",
            TerminalHashMismatchView(raw),
        )


def test_indexed_path_respects_tail_policy_bound():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    _, verify = verifier(
        backend,
        policy=DurableVerificationPolicy(
            max_tail_items=2,
            max_items_between_full_verification=10,
            max_full_verification_age_seconds=3600,
            allow_full_refresh=False,
        ),
    )
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    append_journal(raw, 3, start=3)
    report = verify.inspect(
        "journal",
        IndexedJournalView(raw),
    )
    assert (
        report.status
        is DurableVerificationStatus.FULL_REQUIRED
    )
    result = verify.ensure_current(
        "journal",
        IndexedJournalView(raw),
    )
    assert not result.valid


def test_indexed_range_cursor_digest_is_stable_for_same_tail():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    store, verify = verifier(backend)
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    append_journal(raw, 2, start=3)
    first = verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    latest = store.latest("journal").item
    assert latest.cursor.digest == first.cursor.cursor.digest
    second = verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    assert second.cursor.cursor.digest == first.cursor.cursor.digest
    assert not second.published


def test_indexed_journal_tail_segment_digest_matches_verified_items():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    appended = append_journal(
        raw,
        2,
        start=3,
    )
    result = verify.require_current(
        "journal",
        IndexedJournalView(raw),
    )
    assert result.cursor.cursor.segment_items == len(appended)
    assert len(result.cursor.cursor.segment_digest) == 64


def test_indexed_receipt_tail_segment_digest_matches_verified_items():
    backend = InMemoryFencedStore()
    raw = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    append_receipts(raw, 2)
    _, verify = verifier(
        backend,
        namespace="receipt-cursor",
    )
    verify.require_current(
        "receipts",
        IndexedReceiptView(raw),
    )
    appended = append_receipts(
        raw,
        2,
        start=3,
    )
    result = verify.require_current(
        "receipts",
        IndexedReceiptView(raw),
    )
    assert result.cursor.cursor.segment_items == len(appended)
    assert len(result.cursor.cursor.segment_digest) == 64


def test_full_refresh_still_uses_full_chain_verification():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 3)
    view = IndexedJournalView(raw)
    _, verify = verifier(backend)
    before = view.verify_calls
    result = verify.full_verify(
        "journal",
        view,
    )
    assert result.valid
    assert view.verify_calls == before + 1
    assert view.range_calls == 0


def test_indexed_path_does_not_call_full_verify_for_bounded_tail():
    backend = InMemoryFencedStore()
    raw = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_journal(raw, 2)
    view = IndexedJournalView(raw)
    _, verify = verifier(backend)
    verify.require_current(
        "journal",
        view,
    )
    baseline = view.verify_calls
    append_journal(raw, 1, start=3)
    verify.require_current(
        "journal",
        view,
    )
    assert view.verify_calls == baseline
    assert view.range_calls == 1

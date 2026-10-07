"""Incremental durable evidence verification cursor tests."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalConflict,
    DistributedJournalCorruption,
    DistributedJournalHead,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursor,
    DurableVerificationCursorError,
    DurableVerificationCursorHead,
    DurableVerificationCursorStore,
    DurableVerificationMode,
    DurableVerificationPolicy,
    DurableVerificationStatus,
    SignedDurableVerificationCursor,
)
from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    DistributedReceiptHead,
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
    correlation_id: str = "correlation",
    attempt: int = 1,
    fingerprint: str | None = None,
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
        attempt=attempt,
        receipt_id=f"receipt-{name}",
        metadata={"name": name},
    )


def append_event(
    journal: DistributedAIDecisionJournal,
    name: str,
    *,
    session_id: str = "session",
):
    return journal.append(
        f"event.{name}",
        session_id=session_id,
        intent_id="intent",
        proposal_id="proposal",
        summary=name,
        data={"name": name},
    )


def cursor_runtime(
    *,
    backend=None,
    clock=None,
    policy=None,
    namespace="verification-cursors",
):
    backend = backend or InMemoryFencedStore()
    signer = ArtifactSigner(
        "verification",
        b"v" * 32,
        clock=clock or (lambda: 10.0),
    )
    store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace=namespace,
    )
    verifier = DurableIncrementalVerifier(
        store,
        policy,
        clock=clock or (lambda: 10.0),
    )
    return backend, signer, store, verifier


def test_journal_segment_returns_only_tail():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    one = append_event(journal, "one")
    two = append_event(journal, "two")
    three = append_event(journal, "three")

    segment = journal.snapshot_segment(
        one.event_hash,
        three.event_hash,
    )
    assert segment == (two, three)
    assert journal.verify_segment(
        one.event_hash,
        three.event_hash,
    )


def test_journal_segment_defaults_to_current_head():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    one = append_event(journal, "one")
    two = append_event(journal, "two")
    assert journal.snapshot_segment(
        one.event_hash
    ) == (two,)


def test_journal_segment_same_root_is_empty():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    one = append_event(journal, "one")
    assert journal.snapshot_segment(
        one.event_hash,
        one.event_hash,
    ) == ()


def test_journal_segment_from_genesis():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    one = append_event(journal, "one")
    two = append_event(journal, "two")
    assert journal.snapshot_segment(
        GENESIS,
        two.event_hash,
    ) == (one, two)


def test_journal_segment_enforces_bound_before_walk():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    for index in range(5):
        append_event(journal, str(index))
    with pytest.raises(
        DistributedJournalConflict,
        match="bounded",
    ):
        journal.snapshot_segment(
            GENESIS,
            max_items=4,
        )
    assert not journal.verify_segment(
        GENESIS,
        max_items=4,
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_journal_segment_bound_validation(value):
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="max_items"):
        journal.snapshot_segment(
            GENESIS,
            max_items=value,
        )


def test_journal_segment_rejects_nonancestor_orphan():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    committed = append_event(journal, "committed")
    payload = MappingProxyType({"orphan": True})
    orphan_hash = AIDecisionJournal._hash(
        GENESIS,
        1,
        "orphan",
        2.0,
        "other",
        "intent",
        "",
        "",
        payload,
    )
    backend.put_if_absent(
        "journal",
        f"event:{orphan_hash}",
        AIDecisionEvent(
            1,
            GENESIS,
            orphan_hash,
            "orphan",
            2.0,
            "other",
            "intent",
            "",
            "",
            payload,
        ),
    )
    with pytest.raises(
        DistributedJournalCorruption,
        match="equal segment sequence",
    ):
        journal.snapshot_segment(
            orphan_hash,
            committed.event_hash,
        )


def test_receipt_segment_returns_only_tail():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    one = chain.append(receipt("one"))
    two = chain.append(
        receipt("two", attempt=2)
    )
    three = chain.append(
        receipt("three", attempt=3)
    )
    segment = chain.snapshot_segment(
        one.receipt_hash,
        three.receipt_hash,
    )
    assert segment == (two, three)
    assert chain.verify_segment(
        one.receipt_hash,
        three.receipt_hash,
    )


def test_receipt_segment_defaults_to_current_head():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    one = chain.append(receipt("one"))
    two = chain.append(
        receipt("two", attempt=2)
    )
    assert chain.snapshot_segment(
        one.receipt_hash
    ) == (two,)


def test_receipt_segment_same_root_is_empty():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    one = chain.append(receipt("one"))
    assert chain.snapshot_segment(
        one.receipt_hash,
        one.receipt_hash,
    ) == ()


def test_receipt_segment_from_genesis():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    one = chain.append(receipt("one"))
    two = chain.append(
        receipt("two", attempt=2)
    )
    assert chain.snapshot_segment(
        GENESIS,
        two.receipt_hash,
    ) == (one, two)


def test_receipt_segment_enforces_bound():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    for index in range(5):
        chain.append(
            receipt(
                str(index),
                attempt=index + 1,
            )
        )
    with pytest.raises(
        DistributedReceiptConflict,
        match="bounded",
    ):
        chain.snapshot_segment(
            GENESIS,
            max_items=4,
        )
    assert not chain.verify_segment(
        GENESIS,
        max_items=4,
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_receipt_segment_bound_validation(value):
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    with pytest.raises(ValueError, match="max_items"):
        chain.snapshot_segment(
            GENESIS,
            max_items=value,
        )


def test_receipt_segment_rejects_nonancestor_orphan():
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    committed = chain.append(receipt("committed"))
    orphan_receipt = receipt(
        "orphan",
        fingerprint=fp("f"),
    )
    orphan_hash = ReceiptChain._hash(
        GENESIS,
        1,
        orphan_receipt,
    )
    backend.put_if_absent(
        "receipts",
        f"node:{orphan_hash}",
        ChainedReceipt(
            1,
            GENESIS,
            orphan_hash,
            orphan_receipt,
        ),
    )
    with pytest.raises(
        DistributedReceiptCorruption,
        match="equal receipt segment sequence",
    ):
        chain.snapshot_segment(
            orphan_hash,
            committed.receipt_hash,
        )


def test_full_bootstrap_publishes_signed_cursor():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    _, _, store, verifier = cursor_runtime()
    result = verifier.ensure_current(
        "journal",
        journal,
    )
    assert result.valid
    assert result.published
    assert (
        result.report.status
        is DurableVerificationStatus.FULL_VERIFIED
    )
    assert result.cursor is not None
    assert (
        result.cursor.cursor.mode
        is DurableVerificationMode.FULL
    )
    assert result.cursor.cursor.sequence == 1
    assert (
        result.cursor.cursor.root_hash
        == journal.root_hash()
    )
    store.verify_item(result.cursor)


def test_full_bootstrap_empty_chain():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, _, verifier = cursor_runtime()
    result = verifier.require_current(
        "empty-journal",
        journal,
    )
    assert result.valid
    assert result.cursor.cursor.sequence == 0
    assert result.cursor.cursor.root_hash == GENESIS


def test_current_cursor_is_reused_without_publication():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    _, _, _, verifier = cursor_runtime()
    first = verifier.require_current(
        "journal",
        journal,
    )
    second = verifier.require_current(
        "journal",
        journal,
    )
    assert not second.published
    assert (
        second.report.status
        is DurableVerificationStatus.CURRENT
    )
    assert (
        second.cursor.cursor.digest
        == first.cursor.cursor.digest
    )


def test_incremental_verification_publishes_tail_cursor():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    _, _, _, verifier = cursor_runtime()
    first = verifier.require_current(
        "journal",
        journal,
    )
    second_event = append_event(
        journal,
        "two",
    )
    second = verifier.require_current(
        "journal",
        journal,
    )
    assert second.published
    assert (
        second.report.status
        is DurableVerificationStatus.TAIL_VERIFIED
    )
    assert second.report.tail_items == 1
    assert second.cursor.cursor.sequence == 2
    assert (
        second.cursor.cursor.root_hash
        == second_event.event_hash
    )
    assert (
        second.cursor.cursor.previous_cursor_digest
        == first.cursor.cursor.digest
    )
    assert (
        second.cursor.cursor.mode
        is DurableVerificationMode.INCREMENTAL
    )
    assert second.cursor.cursor.segment_items == 1


def test_incremental_receipt_verification():
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    chain.append(receipt("one"))
    _, _, _, verifier = cursor_runtime()
    first = verifier.require_current(
        "receipts",
        chain,
    )
    chain.append(receipt("two", attempt=2))
    second = verifier.require_current(
        "receipts",
        chain,
    )
    assert second.valid
    assert second.published
    assert second.report.tail_items == 1
    assert (
        second.cursor.cursor.previous_cursor_digest
        == first.cursor.cursor.digest
    )


class CountingChain:
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


def test_incremental_path_does_not_full_replay():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    counted = CountingChain(journal)
    _, _, _, verifier = cursor_runtime()
    verifier.require_current(
        "journal",
        counted,
    )
    assert counted.verify_calls == 1
    append_event(journal, "two")
    verifier.require_current(
        "journal",
        counted,
    )
    assert counted.verify_calls == 1
    assert counted.segment_calls == 1


def test_periodic_age_forces_full_refresh_at_same_head():
    clock = [10.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
    )
    _, _, store, verifier = cursor_runtime(
        clock=lambda: clock[0],
        policy=policy,
    )
    first = verifier.require_current(
        "journal",
        journal,
    )
    clock[0] = 20.0
    inspected = verifier.inspect(
        "journal",
        journal,
    )
    assert (
        inspected.status
        is DurableVerificationStatus.FULL_REQUIRED
    )
    refreshed = verifier.require_current(
        "journal",
        journal,
    )
    assert refreshed.published
    assert (
        refreshed.report.status
        is DurableVerificationStatus.FULL_VERIFIED
    )
    assert (
        refreshed.cursor.cursor.sequence
        == first.cursor.cursor.sequence
    )
    assert (
        refreshed.cursor.cursor.root_hash
        == first.cursor.cursor.root_hash
    )
    assert (
        refreshed.cursor.cursor.previous_cursor_digest
        == first.cursor.cursor.digest
    )
    assert (
        refreshed.cursor.cursor.digest
        != first.cursor.cursor.digest
    )
    assert (
        store.latest("journal").item.cursor.digest
        == refreshed.cursor.cursor.digest
    )


def test_item_count_forces_full_refresh():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    policy = DurableVerificationPolicy(
        max_tail_items=2,
        max_items_between_full_verification=2,
    )
    _, _, _, verifier = cursor_runtime(
        policy=policy,
    )
    verifier.require_current(
        "journal",
        journal,
    )
    append_event(journal, "two")
    append_event(journal, "three")
    append_event(journal, "four")
    report = verifier.inspect(
        "journal",
        journal,
    )
    assert (
        report.status
        is DurableVerificationStatus.FULL_REQUIRED
    )
    result = verifier.require_current(
        "journal",
        journal,
    )
    assert (
        result.report.status
        is DurableVerificationStatus.FULL_VERIFIED
    )
    assert result.cursor.cursor.sequence == 4


def test_full_refresh_can_be_disabled():
    clock = [10.0]
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
        allow_full_refresh=False,
    )
    _, _, _, verifier = cursor_runtime(
        clock=lambda: clock[0],
        policy=policy,
    )
    verifier.require_current(
        "journal",
        journal,
    )
    clock[0] = 20.0
    result = verifier.ensure_current(
        "journal",
        journal,
    )
    assert not result.valid
    assert not result.published
    assert (
        result.report.status
        is DurableVerificationStatus.FULL_REQUIRED
    )


def test_full_bootstrap_can_be_disabled():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    policy = DurableVerificationPolicy(
        allow_full_bootstrap=False,
    )
    _, _, _, verifier = cursor_runtime(
        policy=policy,
    )
    result = verifier.ensure_current(
        "journal",
        journal,
    )
    assert not result.valid
    assert result.cursor is None
    assert (
        result.report.status
        is DurableVerificationStatus.NO_CURSOR
    )
    with pytest.raises(
        DurableVerificationCursorError,
    ):
        verifier.require_current(
            "journal",
            journal,
        )


def test_policy_change_invalidates_old_cursor():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    backend = InMemoryFencedStore()
    signer = ArtifactSigner(
        "verification",
        b"v" * 32,
        clock=lambda: 10.0,
    )
    store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace="cursors",
    )
    first = DurableIncrementalVerifier(
        store,
        DurableVerificationPolicy(
            max_tail_items=8,
            max_items_between_full_verification=8,
        ),
        clock=lambda: 10.0,
    )
    first.require_current(
        "journal",
        journal,
    )
    changed = DurableIncrementalVerifier(
        store,
        DurableVerificationPolicy(
            max_tail_items=9,
            max_items_between_full_verification=9,
        ),
        clock=lambda: 10.0,
    )
    report = changed.inspect(
        "journal",
        journal,
    )
    assert (
        report.status
        is DurableVerificationStatus.INVALID
    )
    assert any(
        "policy differs" in reason
        for reason in report.reasons
    )


def test_verifier_version_change_invalidates_cursor():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    backend, signer, store, _ = cursor_runtime()
    first = DurableIncrementalVerifier(
        store,
        clock=lambda: 10.0,
        verifier_version="1",
    )
    first.require_current(
        "journal",
        journal,
    )
    second = DurableIncrementalVerifier(
        store,
        clock=lambda: 10.0,
        verifier_version="2",
    )
    report = second.inspect(
        "journal",
        journal,
    )
    assert (
        report.status
        is DurableVerificationStatus.INVALID
    )
    assert any(
        "version differs" in reason
        for reason in report.reasons
    )


class HeadOverrideChain(CountingChain):
    def __init__(
        self,
        delegate,
        *,
        sequence,
        root_hash,
    ):
        super().__init__(delegate)
        self.override = DistributedJournalHead(
            sequence,
            root_hash,
        )

    def head(self):
        return self.override


def test_chain_regression_behind_cursor_is_invalid():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    one = append_event(journal, "one")
    append_event(journal, "two")
    _, _, _, verifier = cursor_runtime()
    verifier.require_current(
        "journal",
        journal,
    )
    regressed = HeadOverrideChain(
        journal,
        sequence=1,
        root_hash=one.event_hash,
    )
    report = verifier.inspect(
        "journal",
        regressed,
    )
    assert (
        report.status
        is DurableVerificationStatus.INVALID
    )
    assert any(
        "regressed" in reason
        for reason in report.reasons
    )


def test_equal_sequence_fork_is_invalid():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    _, _, _, verifier = cursor_runtime()
    verifier.require_current(
        "journal",
        journal,
    )
    forked = HeadOverrideChain(
        journal,
        sequence=1,
        root_hash=fp("f"),
    )
    report = verifier.inspect(
        "journal",
        forked,
    )
    assert (
        report.status
        is DurableVerificationStatus.INVALID
    )
    assert any(
        "forked" in reason
        for reason in report.reasons
    )


class AppendDuringSegment(CountingChain):
    def __init__(self, delegate):
        super().__init__(delegate)
        self.injected = False

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        result = super().snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )
        if not self.injected:
            self.injected = True
            append_event(
                self.delegate,
                "racing",
            )
        return result


def test_moving_head_during_incremental_verification_retries():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    _, _, _, verifier = cursor_runtime()
    verifier.require_current(
        "journal",
        journal,
    )
    append_event(journal, "two")
    racing = AppendDuringSegment(journal)
    result = verifier.require_current(
        "journal",
        racing,
    )
    assert result.valid
    assert result.cursor.cursor.sequence == 3
    assert result.report.head_retries == 1
    assert racing.segment_calls == 2


class AppendDuringFull(CountingChain):
    def __init__(self, delegate):
        super().__init__(delegate)
        self.injected = False

    def verify(self):
        result = super().verify()
        if not self.injected:
            self.injected = True
            append_event(
                self.delegate,
                "during-full",
            )
        return result


def test_moving_head_during_full_verification_retries():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    moving = AppendDuringFull(journal)
    _, _, _, verifier = cursor_runtime()
    result = verifier.require_current(
        "journal",
        moving,
    )
    assert result.valid
    assert result.cursor.cursor.sequence == 2
    assert result.report.head_retries == 1
    assert moving.verify_calls == 2


def test_fresh_store_reader_resolves_latest_cursor():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    backend = InMemoryFencedStore()
    signer = ArtifactSigner(
        "verification",
        b"v" * 32,
        clock=lambda: 10.0,
    )
    store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace="cursors",
    )
    verifier = DurableIncrementalVerifier(
        store,
        clock=lambda: 10.0,
    )
    first = verifier.require_current(
        "journal",
        journal,
    )
    fresh_store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace="cursors",
    )
    fresh = fresh_store.latest(
        "journal"
    )
    assert fresh is not None
    assert (
        fresh.item.cursor.digest
        == first.cursor.cursor.digest
    )


def test_signature_tamper_is_rejected_on_read():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    backend, _, store, verifier = cursor_runtime()
    first = verifier.require_current(
        "journal",
        journal,
    )
    key = store._cursor_key(
        first.cursor.cursor.digest
    )
    record = backend.get(
        store.namespace,
        key,
    )
    tampered_signature = replace(
        first.cursor.signature,
        signature="f" * 64,
    )
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=SignedDurableVerificationCursor(
            first.cursor.cursor,
            tampered_signature,
        ),
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="signature",
    ):
        store.latest("journal")


def test_head_to_missing_cursor_is_rejected():
    backend, _, store, _ = cursor_runtime()
    backend.put_if_absent(
        store.namespace,
        store._head_key("journal"),
        DurableVerificationCursorHead(
            "journal",
            fp("f"),
            1,
            fp("a"),
        ),
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="missing",
    ):
        store.latest("journal")


def manual_cursor(
    *,
    chain_id="journal",
    sequence=1,
    root_hash=None,
    previous="",
    mode=DurableVerificationMode.FULL,
    verified_at=10.0,
    full_verified_at=10.0,
    full_sequence=None,
    segment_items=None,
    policy=None,
):
    policy = policy or DurableVerificationPolicy()
    full_sequence = (
        sequence
        if full_sequence is None
        else full_sequence
    )
    if segment_items is None:
        segment_items = (
            sequence
            if mode is DurableVerificationMode.FULL
            else 1
        )
    return DurableVerificationCursor(
        1,
        chain_id,
        sequence,
        root_hash or fp("a"),
        previous,
        mode,
        verified_at,
        full_verified_at,
        full_sequence,
        fp("b"),
        segment_items,
        fp("c"),
        policy.digest,
        "1",
    )


def test_store_rejects_stale_predecessor():
    _, _, store, _ = cursor_runtime()
    first = store.sign(
        manual_cursor()
    )
    store.publish(first)
    stale = store.sign(
        manual_cursor(
            sequence=2,
            root_hash=fp("d"),
            previous=fp("e"),
            mode=DurableVerificationMode.INCREMENTAL,
            full_sequence=1,
            segment_items=1,
        )
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="predecessor",
    ):
        store.publish(stale)


def test_store_rejects_equal_sequence_fork():
    _, _, store, _ = cursor_runtime()
    first = store.sign(
        manual_cursor()
    )
    store.publish(first)
    fork = store.sign(
        manual_cursor(
            sequence=1,
            root_hash=fp("f"),
            previous=first.cursor.digest,
            verified_at=11.0,
            full_verified_at=11.0,
        )
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="fork",
    ):
        store.publish(fork)


def test_store_allows_equal_sequence_same_root_refresh():
    _, _, store, _ = cursor_runtime()
    first = store.sign(
        manual_cursor()
    )
    stored_first = store.publish(first)
    refresh = store.sign(
        manual_cursor(
            sequence=1,
            root_hash=first.cursor.root_hash,
            previous=first.cursor.digest,
            verified_at=20.0,
            full_verified_at=20.0,
        )
    )
    stored_refresh = store.publish(
        refresh
    )
    assert (
        stored_refresh.head_revision
        > stored_first.head_revision
    )
    assert (
        store.latest("journal").item.cursor.digest
        == refresh.cursor.digest
    )


def test_store_rejects_sequence_regression():
    _, _, store, _ = cursor_runtime()
    first = store.sign(
        manual_cursor(
            sequence=2,
        )
    )
    store.publish(first)
    regressed = store.sign(
        manual_cursor(
            sequence=1,
            previous=first.cursor.digest,
            verified_at=11.0,
            full_verified_at=11.0,
        )
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="regress",
    ):
        store.publish(regressed)


def test_incremental_cursor_requires_predecessor():
    with pytest.raises(
        ValueError,
        match="previous",
    ):
        manual_cursor(
            mode=DurableVerificationMode.INCREMENTAL,
            previous="",
            full_sequence=0,
            segment_items=1,
        )


def test_incremental_cursor_requires_nonempty_segment():
    with pytest.raises(
        ValueError,
        match="non-empty",
    ):
        manual_cursor(
            mode=DurableVerificationMode.INCREMENTAL,
            previous=fp("p"),
            full_sequence=0,
            segment_items=0,
        )


def test_full_cursor_requires_matching_full_sequence():
    with pytest.raises(
        ValueError,
        match="full-verify",
    ):
        manual_cursor(
            sequence=2,
            full_sequence=1,
        )


def test_full_cursor_requires_matching_full_timestamp():
    with pytest.raises(
        ValueError,
        match="timestamps",
    ):
        manual_cursor(
            verified_at=10.0,
            full_verified_at=9.0,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tail_items": 0},
        {"max_items_between_full_verification": 0},
        {"max_head_retries": 0},
        {"max_full_verification_age_seconds": 0.0},
        {"allow_full_bootstrap": "yes"},
        {"allow_full_refresh": "yes"},
    ],
)
def test_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableVerificationPolicy(**kwargs)


def test_policy_rejects_tail_larger_than_full_interval():
    with pytest.raises(
        ValueError,
        match="may not exceed",
    ):
        DurableVerificationPolicy(
            max_tail_items=10,
            max_items_between_full_verification=9,
        )


def test_policy_digest_is_stable():
    first = DurableVerificationPolicy()
    second = DurableVerificationPolicy()
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()


def test_cursor_digest_is_stable():
    first = manual_cursor()
    second = manual_cursor()
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()


def test_cursor_head_validation():
    with pytest.raises(ValueError):
        DurableVerificationCursorHead(
            "",
            fp("a"),
            1,
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableVerificationCursorHead(
            "chain",
            "bad",
            1,
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableVerificationCursorHead(
            "chain",
            fp("a"),
            -1,
            fp("b"),
        )


def test_cursor_store_constructor_validation():
    with pytest.raises(ValueError, match="namespace"):
        DurableVerificationCursorStore(
            InMemoryFencedStore(),
            ArtifactSigner(
                "key",
                b"k" * 32,
            ),
            namespace="",
        )
    with pytest.raises(TypeError, match="signer"):
        DurableVerificationCursorStore(
            InMemoryFencedStore(),
            object(),
        )


def test_verifier_constructor_validation():
    _, _, store, _ = cursor_runtime()
    with pytest.raises(TypeError, match="store"):
        DurableIncrementalVerifier(
            object()
        )
    with pytest.raises(TypeError, match="policy"):
        DurableIncrementalVerifier(
            store,
            object(),
        )
    with pytest.raises(ValueError, match="verifier_version"):
        DurableIncrementalVerifier(
            store,
            verifier_version="",
        )


def test_invalid_clock_is_rejected():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    _, _, store, _ = cursor_runtime()
    verifier = DurableIncrementalVerifier(
        store,
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="clock",
    ):
        verifier.inspect(
            "journal",
            journal,
        )


def test_old_prefix_tamper_is_caught_by_periodic_full_verification():
    clock = [10.0]
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    first_event = append_event(journal, "one")
    append_event(journal, "two")
    policy = DurableVerificationPolicy(
        max_full_verification_age_seconds=5.0,
    )
    _, _, _, verifier = cursor_runtime(
        clock=lambda: clock[0],
        policy=policy,
    )
    verifier.require_current(
        "journal",
        journal,
    )

    key = journal._event_key(
        first_event.event_hash
    )
    record = backend.get(
        "journal",
        key,
    )
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            first_event,
            summary="tampered-old-prefix",
        ),
    )
    append_event(journal, "three")

    incremental = verifier.require_current(
        "journal",
        journal,
    )
    assert incremental.valid
    assert (
        incremental.report.status
        is DurableVerificationStatus.TAIL_VERIFIED
    )

    clock[0] = 20.0
    with pytest.raises(
        DurableVerificationCursorError,
        match="full-verify",
    ):
        verifier.require_current(
            "journal",
            journal,
        )


def test_cursor_anchor_tamper_blocks_incremental_verification():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    anchor = append_event(journal, "two")
    _, _, _, verifier = cursor_runtime()
    verifier.require_current(
        "journal",
        journal,
    )
    key = journal._event_key(
        anchor.event_hash
    )
    record = backend.get(
        "journal",
        key,
    )
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            anchor,
            summary="tampered-anchor",
        ),
    )
    append_event(journal, "three")
    with pytest.raises(
        (
            DistributedJournalCorruption,
            DurableVerificationCursorError,
        )
    ):
        verifier.require_current(
            "journal",
            journal,
        )


class FailingVerifyChain(CountingChain):
    def verify(self):
        self.verify_calls += 1
        return False


def test_full_bootstrap_fails_closed_on_invalid_chain():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    failing = FailingVerifyChain(journal)
    policy = DurableVerificationPolicy(
        max_head_retries=2,
    )
    _, _, _, verifier = cursor_runtime(
        policy=policy,
    )
    with pytest.raises(
        DurableVerificationCursorError,
        match="stable chain head",
    ):
        verifier.require_current(
            "journal",
            failing,
        )
    assert failing.verify_calls == 2


class AlwaysMovingSegment(CountingChain):
    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        result = super().snapshot_segment(
            start_exclusive_root,
            end_inclusive_root,
            max_items=max_items,
        )
        append_event(
            self.delegate,
            f"move-{self.segment_calls}",
        )
        return result


def test_incremental_moving_head_honors_retry_bound():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    policy = DurableVerificationPolicy(
        max_head_retries=2,
    )
    _, _, _, verifier = cursor_runtime(
        policy=policy,
    )
    verifier.require_current(
        "journal",
        journal,
    )
    append_event(journal, "two")
    moving = AlwaysMovingSegment(journal)
    with pytest.raises(
        DurableVerificationCursorError,
        match="stable chain head",
    ):
        verifier.require_current(
            "journal",
            moving,
        )
    assert moving.segment_calls == 2


class ConflictOnceBackend:
    def __init__(self):
        self.store = InMemoryFencedStore()
        self.conflict = True

    def get(self, namespace, key):
        return self.store.get(namespace, key)

    def put_if_absent(self, namespace, key, value):
        if (
            key.startswith("head:")
            and self.conflict
        ):
            self.conflict = False
            raise DistributedStateConflict(
                "synthetic cursor head race"
            )
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


def test_cursor_store_retries_initial_head_race():
    backend = ConflictOnceBackend()
    signer = ArtifactSigner(
        "verification",
        b"v" * 32,
    )
    store = DurableVerificationCursorStore(
        backend,
        signer,
        max_cas_retries=2,
    )
    item = store.sign(
        manual_cursor()
    )
    stored = store.publish(item)
    assert stored.item == item


def test_report_serialization():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    _, _, _, verifier = cursor_runtime()
    result = verifier.require_current(
        "journal",
        journal,
    )
    data = result.to_dict()
    assert data["valid"] is True
    assert data["published"] is True
    assert (
        data["report"]["status"]
        == "full_verified"
    )
    assert data["report"]["digest"] == result.report.digest
    assert data["cursor"]["cursor_digest"] == (
        result.cursor.cursor.digest
    )


def test_fresh_verifier_continues_incrementally_from_shared_store():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 1.0,
    )
    append_event(journal, "one")
    backend = InMemoryFencedStore()
    signer = ArtifactSigner(
        "verification",
        b"v" * 32,
        clock=lambda: 10.0,
    )
    first_store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace="cursors",
    )
    first_verifier = DurableIncrementalVerifier(
        first_store,
        clock=lambda: 10.0,
    )
    first_verifier.require_current(
        "journal",
        journal,
    )
    append_event(journal, "two")

    fresh_store = DurableVerificationCursorStore(
        backend,
        signer,
        namespace="cursors",
    )
    fresh_verifier = DurableIncrementalVerifier(
        fresh_store,
        clock=lambda: 10.0,
    )
    result = fresh_verifier.require_current(
        "journal",
        journal,
    )
    assert (
        result.report.status
        is DurableVerificationStatus.TAIL_VERIFIED
    )
    assert result.cursor.cursor.sequence == 2

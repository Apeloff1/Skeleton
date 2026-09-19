"""Signed durable destruction ledger adversarial tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_destruction import (
    DESTRUCTION_ARTIFACT_TYPE,
    GENESIS_DIGEST,
    DurableDestructionConflict,
    DurableDestructionCorruption,
    DurableDestructionHead,
    DurableDestructionItem,
    DurableDestructionItemState,
    DurableDestructionKind,
    DurableDestructionLedger,
    DurableDestructionOperationIndex,
    DurableDestructionRecord,
    DurableDestructionVerification,
    SignedDurableDestructionRecord,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner, SignedArtifact


def fp(char: str) -> str:
    return char * 64


class Clock:
    def __init__(self, value: float = 100.0):
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def signer(clock=None):
    return ArtifactSigner(
        "destruction",
        b"d" * 32,
        clock=clock or (lambda: 100.0),
    )


def ledger(
    backend=None,
    *,
    clock=None,
    namespace="destruction",
    max_records=100,
    max_items_per_record=100,
):
    return DurableDestructionLedger(
        backend or InMemoryFencedStore(),
        signer(clock),
        namespace=namespace,
        max_records=max_records,
        max_items_per_record=max_items_per_record,
        clock=clock or (lambda: 100.0),
    )


def item(
    name: str,
    *,
    state=DurableDestructionItemState.DELETED,
    archived=True,
    sequence=1,
    expected_revision=1,
    receipt_id="",
):
    return DurableDestructionItem(
        "journal_event",
        "journal",
        f"event:{name}",
        fp(name[0] if name else "a"),
        state,
        expected_revision,
        sequence,
        receipt_id,
        archived,
    )


def append_pruning(
    store: DurableDestructionLedger,
    *,
    chain_id="journal",
    operation_id=None,
    authority_id=None,
    authority_digest=None,
    manifest_digest=None,
    before_sequence=10,
    before_root=None,
    before_floor_sequence=0,
    before_floor_root=GENESIS_DIGEST,
    after_sequence=10,
    after_root=None,
    after_floor_sequence=5,
    after_floor_root=None,
    items=None,
    archive_id="archive-1",
    archive_manifest_digest=None,
    post_verify_digest=None,
    fencing_token=1,
    completed_at=100.0,
):
    return store.append(
        chain_id=chain_id,
        operation_kind=DurableDestructionKind.PRUNING,
        operation_id=operation_id or fp("o"),
        authority_id=authority_id or fp("a"),
        authority_digest=authority_digest or fp("b"),
        manifest_digest=manifest_digest or fp("m"),
        before_sequence=before_sequence,
        before_root=before_root or fp("h"),
        before_floor_sequence=before_floor_sequence,
        before_floor_root=before_floor_root,
        after_sequence=after_sequence,
        after_root=after_root or fp("h"),
        after_floor_sequence=after_floor_sequence,
        after_floor_root=after_floor_root or fp("f"),
        items=items or (item("alpha"),),
        archive_id=archive_id,
        archive_manifest_digest=(
            archive_manifest_digest or fp("c")
        ),
        post_verify_digest=post_verify_digest or fp("v"),
        post_verified=True,
        fencing_token=fencing_token,
        completed_at=completed_at,
    )


def append_gc(
    store: DurableDestructionLedger,
    *,
    chain_id="journal",
    operation_id=None,
    authority_id=None,
    authority_digest=None,
    manifest_digest=None,
    before_sequence=10,
    before_root=None,
    before_floor_sequence=0,
    before_floor_root=GENESIS_DIGEST,
    after_sequence=10,
    after_root=None,
    after_floor_sequence=0,
    after_floor_root=GENESIS_DIGEST,
    items=None,
    post_verify_digest=None,
    fencing_token=1,
    completed_at=100.0,
):
    gc_item = DurableDestructionItem(
        "journal_event",
        "journal",
        "event:orphan",
        fp("e"),
        DurableDestructionItemState.DELETED,
        1,
        1,
        "",
        False,
    )
    return store.append(
        chain_id=chain_id,
        operation_kind=DurableDestructionKind.ORPHAN_GC,
        operation_id=operation_id or fp("g"),
        authority_id=authority_id or fp("z"),
        authority_digest=authority_digest or fp("y"),
        manifest_digest=manifest_digest or fp("x"),
        before_sequence=before_sequence,
        before_root=before_root or fp("h"),
        before_floor_sequence=before_floor_sequence,
        before_floor_root=before_floor_root,
        after_sequence=after_sequence,
        after_root=after_root or fp("h"),
        after_floor_sequence=after_floor_sequence,
        after_floor_root=after_floor_root,
        items=items or (gc_item,),
        post_verify_digest=post_verify_digest or fp("v"),
        post_verified=True,
        fencing_token=fencing_token,
        completed_at=completed_at,
    )


def test_empty_ledger_has_no_head_and_verifies():
    store = ledger()
    assert store.head("journal") is None
    assert store.snapshot("journal") == ()
    report = store.verify("journal")
    assert report.ok
    assert report.sequence == 0
    assert report.records == 0
    assert report.issues == ()


def test_append_pruning_record_is_signed_and_committed():
    store = ledger()
    signed = append_pruning(store)
    assert signed.record.sequence == 1
    assert signed.record.previous_record_digest == GENESIS_DIGEST
    assert signed.signature.artifact_type == DESTRUCTION_ARTIFACT_TYPE
    assert signed.signature.artifact_digest == signed.record.digest
    assert signed.record.deleted_count == 1
    assert signed.record.already_absent_count == 0
    assert store.head("journal").record_id == signed.record_id
    assert store.snapshot("journal") == (signed,)
    assert store.require_verified("journal").ok


def test_second_record_links_first_digest():
    store = ledger()
    first = append_pruning(store)
    second = append_gc(
        store,
        operation_id=fp("q"),
        authority_id=fp("r"),
        authority_digest=fp("s"),
        manifest_digest=fp("t"),
        fencing_token=2,
        completed_at=101.0,
    )
    assert second.record.sequence == 2
    assert second.record.previous_record_digest == first.record.digest
    assert store.snapshot("journal") == (first, second)
    assert store.head("journal").record_digest == second.record.digest
    assert store.require_verified("journal").ok


def test_per_chain_histories_are_isolated():
    store = ledger()
    first = append_pruning(store, chain_id="journal")
    second = append_pruning(
        store,
        chain_id="receipts",
        operation_id=fp("q"),
        authority_id=fp("r"),
        manifest_digest=fp("s"),
    )
    assert store.snapshot("journal") == (first,)
    assert store.snapshot("receipts") == (second,)
    assert store.head("journal").sequence == 1
    assert store.head("receipts").sequence == 1


def test_operation_lookup_returns_committed_record():
    store = ledger()
    signed = append_pruning(store)
    found = store.find_operation(
        "journal",
        DurableDestructionKind.PRUNING,
        fp("o"),
    )
    assert found == signed


def test_operation_lookup_missing_returns_none():
    store = ledger()
    assert (
        store.find_operation(
            "journal",
            DurableDestructionKind.PRUNING,
            fp("o"),
        )
        is None
    )


def test_exact_retry_is_idempotent():
    store = ledger()
    first = append_pruning(store)
    second = append_pruning(store)
    assert second == first
    assert store.head("journal").sequence == 1
    assert len(store.snapshot("journal")) == 1


def test_retry_can_reuse_original_completion_timestamp():
    clock = Clock(100.0)
    store = ledger(clock=clock)
    first = append_pruning(
        store,
        completed_at=100.0,
    )
    clock.advance(50)
    second = append_pruning(
        store,
        completed_at=999.0,
    )
    # append() normalizes a retry against the original committed timestamp.
    assert second == first
    assert second.record.completed_at == 100.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority_id", fp("z")),
        ("authority_digest", fp("z")),
        ("manifest_digest", fp("z")),
        ("before_root", fp("z")),
        ("after_floor_root", fp("z")),
        ("post_verify_digest", fp("z")),
        ("fencing_token", 9),
    ],
)
def test_retry_with_different_evidence_conflicts(field, value):
    store = ledger()
    append_pruning(store)
    kwargs = {field: value}
    with pytest.raises(
        DurableDestructionConflict,
        match="different evidence",
    ):
        append_pruning(store, **kwargs)


def test_retry_with_different_items_conflicts():
    store = ledger()
    append_pruning(store)
    with pytest.raises(
        DurableDestructionConflict,
        match="different evidence",
    ):
        append_pruning(
            store,
            items=(item("beta"),),
        )


def test_operation_index_repairs_after_post_head_crash_window():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    index_key = store._operation_index_key(
        signed.operation_key
    )
    index_record = backend.get(
        store.namespace,
        index_key,
    )
    assert index_record is not None
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    assert backend.get(
        store.namespace,
        index_key,
    ) is None

    fresh = DurableDestructionLedger(
        backend,
        signer(),
        namespace=store.namespace,
    )
    repaired = fresh.find_operation(
        "journal",
        DurableDestructionKind.PRUNING,
        fp("o"),
    )
    assert repaired.record.digest == signed.record.digest
    assert backend.get(
        store.namespace,
        index_key,
    ) is not None


def test_missing_index_is_repaired_by_verify():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._operation_index_key(
        signed.operation_key
    )
    record = backend.get(
        store.namespace,
        key,
    )
    backend.delete(
        store.namespace,
        key,
        expected_revision=record.revision,
    )
    report = store.verify("journal")
    assert report.ok
    assert backend.get(
        store.namespace,
        key,
    ) is not None


def test_unreachable_candidate_is_not_authoritative():
    store = ledger()
    first = append_pruning(store)
    orphan_record = DurableDestructionRecord(
        1,
        "journal",
        2,
        first.record.digest,
        DurableDestructionKind.ORPHAN_GC,
        fp("u"),
        fp("v"),
        fp("w"),
        fp("x"),
        10,
        fp("h"),
        5,
        fp("f"),
        10,
        fp("h"),
        5,
        fp("f"),
        (
            DurableDestructionItem(
                "journal_event",
                "journal",
                "event:unreachable",
                fp("e"),
                DurableDestructionItemState.DELETED,
                2,
                2,
                "",
                False,
            ),
        ),
        "",
        "",
        fp("p"),
        True,
        102.0,
        2,
    )
    orphan = SignedDurableDestructionRecord(
        orphan_record,
        store.signer.sign(
            DESTRUCTION_ARTIFACT_TYPE,
            orphan_record.digest,
            metadata={
                "chain_id": "journal",
                "operation_kind": "orphan_gc",
                "operation_id": fp("u"),
                "sequence": "2",
                "authority": "post-destruction-evidence",
            },
        ),
    )
    store._put_record(orphan)
    assert len(store.snapshot("journal")) == 1
    assert (
        store.find_operation(
            "journal",
            DurableDestructionKind.ORPHAN_GC,
            fp("u"),
        )
        is None
    )


def test_operation_index_to_unreachable_record_is_corruption():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    first = append_pruning(store)
    orphan_record = DurableDestructionRecord(
        1,
        "journal",
        2,
        first.record.digest,
        DurableDestructionKind.ORPHAN_GC,
        fp("u"),
        fp("v"),
        fp("w"),
        fp("x"),
        10,
        fp("h"),
        5,
        fp("f"),
        10,
        fp("h"),
        5,
        fp("f"),
        (
            DurableDestructionItem(
                "journal_event",
                "journal",
                "event:unreachable",
                fp("e"),
                DurableDestructionItemState.DELETED,
                2,
                2,
                "",
                False,
            ),
        ),
        "",
        "",
        fp("p"),
        True,
        102.0,
        2,
    )
    orphan = SignedDurableDestructionRecord(
        orphan_record,
        store.signer.sign(
            DESTRUCTION_ARTIFACT_TYPE,
            orphan_record.digest,
            metadata={
                "chain_id": "journal",
                "operation_kind": "orphan_gc",
                "operation_id": fp("u"),
                "sequence": "2",
                "authority": "post-destruction-evidence",
            },
        ),
    )
    store._put_record(orphan)
    index = DurableDestructionOperationIndex(
        "journal",
        orphan.operation_key,
        orphan.record_id,
        orphan.record.digest,
        2,
    )
    backend.put_if_absent(
        store.namespace,
        store._operation_index_key(
            orphan.operation_key
        ),
        index.to_dict(),
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="uncommitted",
    ):
        store.find_operation(
            "journal",
            DurableDestructionKind.ORPHAN_GC,
            fp("u"),
        )


def test_signature_tamper_is_detected():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._record_key(
        signed.record_id
    )
    stored = backend.get(
        store.namespace,
        key,
    )
    raw = dict(stored.value)
    signature = dict(raw["signature"])
    signature["signature"] = "f" * 64
    raw["signature"] = signature
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="signature",
    ):
        store.get(signed.record_id)
    report = store.verify("journal")
    assert not report.ok
    assert not report.signatures_valid or not report.linkage_valid


def test_record_payload_tamper_is_detected():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._record_key(
        signed.record_id
    )
    stored = backend.get(
        store.namespace,
        key,
    )
    raw = dict(stored.value)
    record = dict(raw["record"])
    record["manifest_digest"] = fp("z")
    raw["record"] = record
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    with pytest.raises(
        DurableDestructionCorruption,
    ):
        store.get(signed.record_id)


def test_missing_committed_record_is_corruption():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._record_key(
        signed.record_id
    )
    record = backend.get(
        store.namespace,
        key,
    )
    backend.delete(
        store.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="missing",
    ):
        store.snapshot("journal")
    assert not store.verify("journal").ok


def test_wrong_head_type_is_corruption():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    backend.put_if_absent(
        store.namespace,
        store._head_key("journal"),
        {"chain_id": "journal", "bad": True},
    )
    with pytest.raises(Exception):
        store.head("journal")


def test_head_chain_binding_mismatch_is_corruption():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    head = DurableDestructionHead(
        "other",
        1,
        fp("a"),
        fp("a"),
        fp("b"),
        1.0,
    )
    backend.put_if_absent(
        store.namespace,
        store._head_key("journal"),
        head.to_dict(),
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="binding",
    ):
        store.head("journal")


def test_wrong_operation_index_type_is_corruption():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._operation_index_key(
        signed.operation_key
    )
    record = backend.get(
        store.namespace,
        key,
    )
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(Exception):
        store.find_operation(
            "journal",
            DurableDestructionKind.PRUNING,
            fp("o"),
        )


def test_operation_index_record_digest_substitution_is_corruption():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._operation_index_key(
        signed.operation_key
    )
    record = backend.get(
        store.namespace,
        key,
    )
    raw = dict(record.value)
    raw["record_digest"] = fp("z")
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="differs",
    ):
        store.find_operation(
            "journal",
            DurableDestructionKind.PRUNING,
            fp("o"),
        )


def test_capacity_exhaustion():
    store = ledger(max_records=1)
    append_pruning(store)
    with pytest.raises(RuntimeError, match="capacity"):
        append_gc(
            store,
            operation_id=fp("q"),
            authority_id=fp("r"),
            authority_digest=fp("s"),
            manifest_digest=fp("t"),
            fencing_token=2,
            completed_at=101.0,
        )


def test_item_bound_exhaustion():
    store = ledger(max_items_per_record=1)
    with pytest.raises(ValueError, match="item bound"):
        append_pruning(
            store,
            items=(
                item("alpha"),
                item("beta", sequence=2),
            ),
        )


def test_pruning_requires_archive_binding():
    store = ledger()
    with pytest.raises(ValueError, match="archive"):
        store.append(
            chain_id="journal",
            operation_kind=DurableDestructionKind.PRUNING,
            operation_id=fp("o"),
            authority_id=fp("a"),
            authority_digest=fp("b"),
            manifest_digest=fp("m"),
            before_sequence=10,
            before_root=fp("h"),
            before_floor_sequence=0,
            before_floor_root=GENESIS_DIGEST,
            after_sequence=10,
            after_root=fp("h"),
            after_floor_sequence=5,
            after_floor_root=fp("f"),
            items=(item("alpha"),),
            post_verify_digest=fp("v"),
            post_verified=True,
            fencing_token=1,
            completed_at=100.0,
        )


def test_pruning_requires_archived_items():
    store = ledger()
    with pytest.raises(ValueError, match="archived"):
        append_pruning(
            store,
            items=(
                item(
                    "alpha",
                    archived=False,
                ),
            ),
        )


def test_orphan_gc_allows_non_archived_items():
    store = ledger()
    signed = append_gc(store)
    assert not signed.record.items[0].archived
    assert signed.record.archive_id == ""
    assert store.require_verified("journal").ok


def test_after_head_may_advance_monotonically():
    store = ledger()
    signed = append_pruning(
        store,
        before_sequence=10,
        before_root=fp("a"),
        after_sequence=12,
        after_root=fp("b"),
    )
    assert signed.record.after_sequence == 12
    assert signed.record.after_root == fp("b")


def test_after_head_may_not_move_backward():
    store = ledger()
    with pytest.raises(ValueError, match="backward"):
        append_pruning(
            store,
            before_sequence=10,
            after_sequence=9,
        )


def test_same_head_sequence_may_not_change_root():
    store = ledger()
    with pytest.raises(ValueError, match="same committed"):
        append_pruning(
            store,
            before_sequence=10,
            before_root=fp("a"),
            after_sequence=10,
            after_root=fp("b"),
        )


def test_floor_may_not_move_backward():
    store = ledger()
    with pytest.raises(ValueError, match="floor backward"):
        append_gc(
            store,
            before_floor_sequence=5,
            before_floor_root=fp("a"),
            after_floor_sequence=4,
            after_floor_root=fp("a"),
        )


def test_same_floor_sequence_may_not_change_root():
    store = ledger()
    with pytest.raises(ValueError, match="same hot floor"):
        append_gc(
            store,
            before_floor_sequence=5,
            before_floor_root=fp("a"),
            after_floor_sequence=5,
            after_floor_root=fp("b"),
        )


def test_duplicate_backend_keys_are_rejected():
    duplicate = item("alpha")
    with pytest.raises(ValueError, match="duplicate"):
        DurableDestructionRecord(
            1,
            "journal",
            1,
            GENESIS_DIGEST,
            DurableDestructionKind.PRUNING,
            fp("o"),
            fp("a"),
            fp("b"),
            fp("m"),
            10,
            fp("h"),
            0,
            GENESIS_DIGEST,
            10,
            fp("h"),
            5,
            fp("f"),
            (duplicate, duplicate),
            "archive",
            fp("c"),
            fp("v"),
            True,
            100.0,
            1,
        )


def test_verified_record_requires_verification_digest():
    with pytest.raises(ValueError, match="verification digest"):
        DurableDestructionRecord(
            1,
            "journal",
            1,
            GENESIS_DIGEST,
            DurableDestructionKind.ORPHAN_GC,
            fp("o"),
            fp("a"),
            fp("b"),
            fp("m"),
            10,
            fp("h"),
            0,
            GENESIS_DIGEST,
            10,
            fp("h"),
            0,
            GENESIS_DIGEST,
            (
                DurableDestructionItem(
                    "journal_event",
                    "journal",
                    "event:a",
                    fp("a"),
                    DurableDestructionItemState.DELETED,
                    1,
                    1,
                    "",
                    False,
                ),
            ),
            "",
            "",
            "",
            True,
            100.0,
            1,
        )


def test_unverified_record_may_not_carry_verification_digest():
    with pytest.raises(ValueError, match="unverified"):
        DurableDestructionRecord(
            1,
            "journal",
            1,
            GENESIS_DIGEST,
            DurableDestructionKind.ORPHAN_GC,
            fp("o"),
            fp("a"),
            fp("b"),
            fp("m"),
            10,
            fp("h"),
            0,
            GENESIS_DIGEST,
            10,
            fp("h"),
            0,
            GENESIS_DIGEST,
            (
                DurableDestructionItem(
                    "journal_event",
                    "journal",
                    "event:a",
                    fp("a"),
                    DurableDestructionItemState.DELETED,
                    1,
                    1,
                    "",
                    False,
                ),
            ),
            "",
            "",
            fp("v"),
            False,
            100.0,
            1,
        )


@pytest.mark.parametrize(
    "state",
    [
        DurableDestructionItemState.DELETED,
        DurableDestructionItemState.ALREADY_ABSENT,
    ],
)
def test_item_states_are_serialized(state):
    value = item(
        "alpha",
        state=state,
    )
    assert value.to_dict()["state"] == state.value
    assert len(value.digest) == 64


@pytest.mark.parametrize(
    "kwargs",
    [
        {"item_kind": ""},
        {"backend_namespace": ""},
        {"backend_key": ""},
        {"node_hash": "bad"},
        {"expected_revision": 0},
        {"sequence": 0},
        {"receipt_id": "x" * 129},
        {"archived": "yes"},
    ],
)
def test_item_validation(kwargs):
    values = dict(
        item_kind="journal_event",
        backend_namespace="journal",
        backend_key="event:key",
        node_hash=fp("a"),
        state=DurableDestructionItemState.DELETED,
        expected_revision=1,
        sequence=1,
        receipt_id="",
        archived=True,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableDestructionItem(**values)


def test_record_items_digest_is_order_sensitive():
    first = append_pruning(
        ledger(),
        items=(
            item("alpha"),
            item("beta", sequence=2),
        ),
    ).record
    second_store = ledger(
        namespace="other",
    )
    second = append_pruning(
        second_store,
        items=(
            item("beta", sequence=2),
            item("alpha"),
        ),
    ).record
    assert first.items_digest != second.items_digest
    assert first.digest != second.digest


def test_operation_key_is_stable_across_record_sequence():
    store = ledger()
    first = append_pruning(store)
    second = append_gc(
        store,
        operation_id=fp("q"),
        authority_id=fp("r"),
        authority_digest=fp("s"),
        manifest_digest=fp("t"),
        fencing_token=2,
        completed_at=101.0,
    )
    assert first.operation_key == store.operation_key(
        "journal",
        DurableDestructionKind.PRUNING,
        fp("o"),
    )
    assert second.operation_key == store.operation_key(
        "journal",
        DurableDestructionKind.ORPHAN_GC,
        fp("q"),
    )


def test_head_serialization():
    value = DurableDestructionHead(
        "journal",
        2,
        fp("a"),
        fp("a"),
        fp("b"),
        100.0,
    )
    assert value.to_dict() == {
        "chain_id": "journal",
        "sequence": 2,
        "record_id": fp("a"),
        "record_digest": fp("a"),
        "operation_key": fp("b"),
        "completed_at": 100.0,
    }


def test_operation_index_serialization():
    value = DurableDestructionOperationIndex(
        "journal",
        fp("a"),
        fp("b"),
        fp("b"),
        2,
    )
    assert value.to_dict()["sequence"] == 2
    assert value.to_dict()["chain_id"] == "journal"


def test_verification_serialization():
    value = DurableDestructionVerification(
        "journal",
        1,
        1,
        True,
        True,
        True,
        (),
    )
    assert value.ok
    assert value.to_dict()["ok"] is True


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_ledger_namespace_validation(namespace):
    with pytest.raises(ValueError, match="namespace"):
        DurableDestructionLedger(
            InMemoryFencedStore(),
            signer(),
            namespace=namespace,
        )


@pytest.mark.parametrize(
    "name,value",
    [
        ("max_records", 0),
        ("max_records", True),
        ("max_items_per_record", 0),
        ("max_items_per_record", True),
    ],
)
def test_ledger_capacity_validation(name, value):
    kwargs = {name: value}
    with pytest.raises(ValueError):
        DurableDestructionLedger(
            InMemoryFencedStore(),
            signer(),
            **kwargs,
        )


@pytest.mark.parametrize("retries", [0, 129, True])
def test_ledger_retry_bound_validation(retries):
    with pytest.raises(ValueError, match="max_cas_retries"):
        DurableDestructionLedger(
            InMemoryFencedStore(),
            signer(),
            max_cas_retries=retries,
        )


def test_ledger_signer_type_validation():
    with pytest.raises(TypeError, match="signer"):
        DurableDestructionLedger(
            InMemoryFencedStore(),
            object(),
        )


def test_ledger_clock_validation():
    with pytest.raises(TypeError, match="clock"):
        DurableDestructionLedger(
            InMemoryFencedStore(),
            signer(),
            clock=object(),
        )


def test_get_missing_record_returns_none():
    store = ledger()
    assert store.get(fp("x")) is None


def test_get_rejects_wrong_record_value_type():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    backend.put_if_absent(
        store.namespace,
        store._record_key(fp("x")),
        {"bad": True},
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="record",
    ):
        store.get(fp("x"))


def test_record_key_validation():
    with pytest.raises(ValueError):
        DurableDestructionLedger._record_key("bad")


def test_operation_index_key_validation():
    with pytest.raises(ValueError):
        DurableDestructionLedger._operation_index_key("bad")


def test_operation_key_changes_with_operation_kind():
    pruning = DurableDestructionLedger.operation_key(
        "journal",
        DurableDestructionKind.PRUNING,
        fp("o"),
    )
    gc = DurableDestructionLedger.operation_key(
        "journal",
        DurableDestructionKind.ORPHAN_GC,
        fp("o"),
    )
    assert pruning != gc


def test_operation_key_changes_with_chain():
    first = DurableDestructionLedger.operation_key(
        "journal",
        DurableDestructionKind.PRUNING,
        fp("o"),
    )
    second = DurableDestructionLedger.operation_key(
        "receipts",
        DurableDestructionKind.PRUNING,
        fp("o"),
    )
    assert first != second


def test_already_absent_items_are_counted():
    store = ledger()
    signed = append_gc(
        store,
        items=(
            DurableDestructionItem(
                "journal_event",
                "journal",
                "event:missing",
                fp("e"),
                DurableDestructionItemState.ALREADY_ABSENT,
                1,
                1,
                "",
                False,
            ),
        ),
    )
    assert signed.record.deleted_count == 0
    assert signed.record.already_absent_count == 1


def test_record_to_dict_exposes_authority_and_counts():
    signed = append_pruning(ledger())
    data = signed.record.to_dict()
    assert data["authority"] == "post-destruction-evidence"
    assert data["deleted_count"] == 1
    assert data["already_absent_count"] == 0
    assert data["items_digest"] == signed.record.items_digest
    assert data["digest"] == signed.record.digest
    assert data["operation_key"] == signed.record.operation_key


def test_signed_record_to_dict_contains_signature():
    signed = append_pruning(ledger())
    data = signed.to_dict()
    assert data["record"]["digest"] == signed.record.digest
    assert data["signature"]["artifact_type"] == DESTRUCTION_ARTIFACT_TYPE


def test_fresh_reader_verifies_existing_history():
    backend = InMemoryFencedStore()
    writer = ledger(backend)
    first = append_pruning(writer)
    second = append_gc(
        writer,
        operation_id=fp("q"),
        authority_id=fp("r"),
        authority_digest=fp("s"),
        manifest_digest=fp("t"),
        fencing_token=2,
        completed_at=101.0,
    )
    reader = DurableDestructionLedger(
        backend,
        signer(),
        namespace=writer.namespace,
    )
    assert reader.snapshot("journal") == (first, second)
    assert reader.require_verified("journal").ok


def test_wrong_signing_key_fails_fresh_reader():
    backend = InMemoryFencedStore()
    writer = ledger(backend)
    signed = append_pruning(writer)
    reader = DurableDestructionLedger(
        backend,
        ArtifactSigner(
            "other-key",
            b"x" * 32,
        ),
        namespace=writer.namespace,
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="key_id",
    ):
        reader.get(signed.record_id)


def test_signature_metadata_substitution_is_detected():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._record_key(
        signed.record_id
    )
    stored = backend.get(
        store.namespace,
        key,
    )
    raw = dict(stored.value)
    signature = dict(raw["signature"])
    signature["metadata"] = {
        **dict(signature["metadata"]),
        "chain_id": "other",
    }
    raw["signature"] = signature
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    with pytest.raises(
        DurableDestructionCorruption,
        match="metadata",
    ):
        store.get(signed.record_id)


def test_record_chain_detects_previous_digest_tamper():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    first = append_pruning(store)
    second = append_gc(
        store,
        operation_id=fp("q"),
        authority_id=fp("r"),
        authority_digest=fp("s"),
        manifest_digest=fp("t"),
        fencing_token=2,
        completed_at=101.0,
    )
    key = store._record_key(
        second.record_id
    )
    stored = backend.get(
        store.namespace,
        key,
    )
    raw = dict(stored.value)
    record = dict(raw["record"])
    record["previous_record_digest"] = fp("z")
    raw["record"] = record
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    report = store.verify("journal")
    assert not report.ok
    assert first.record.digest != fp("z")


def test_require_verified_raises_on_corrupt_history():
    backend = InMemoryFencedStore()
    store = ledger(backend)
    signed = append_pruning(store)
    key = store._record_key(
        signed.record_id
    )
    stored = backend.get(
        store.namespace,
        key,
    )
    raw = dict(stored.value)
    signature = dict(raw["signature"])
    signature["signature"] = fp("f")
    raw["signature"] = signature
    backend.compare_and_swap(
        store.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    with pytest.raises(
        DurableDestructionCorruption,
    ):
        store.require_verified("journal")


def test_canonical_stored_signature_wins_same_record_race():
    backend = InMemoryFencedStore()
    clock = Clock(100.0)
    store = ledger(
        backend,
        clock=clock,
    )
    first = append_pruning(
        store,
        completed_at=100.0,
    )
    # Remove only the head and index so the same content-addressed record is
    # encountered as an immutable candidate on reconstruction.
    head_key = store._head_key("journal")
    head_record = backend.get(
        store.namespace,
        head_key,
    )
    backend.delete(
        store.namespace,
        head_key,
        expected_revision=head_record.revision,
    )
    index_key = store._operation_index_key(
        first.operation_key
    )
    index_record = backend.get(
        store.namespace,
        index_key,
    )
    backend.delete(
        store.namespace,
        index_key,
        expected_revision=index_record.revision,
    )
    clock.advance(5)
    rebuilt = append_pruning(
        store,
        completed_at=100.0,
    )
    # The stored signature issued at t=100 remains canonical.
    assert rebuilt.signature.issued_at == 100.0
    assert rebuilt.record == first.record
    assert store.require_verified("journal").ok

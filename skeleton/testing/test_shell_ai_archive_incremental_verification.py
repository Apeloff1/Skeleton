"""Archive-backed bounded segment and incremental verification tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_archive import (
    DurableArchiveManifestBuilder,
)
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchiveRepository,
    DurableArchiveRootIndex,
    DurableArchiveRootReplica,
    DurableArchiveStoreError,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_verification_cursor import (
    DurableIncrementalVerifier,
    DurableVerificationCursorStore,
    DurableVerificationMode,
    DurableVerificationPolicy,
    DurableVerificationStatus,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


GENESIS = "0" * 64


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def checkpoint_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def archive_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "archive",
        b"a" * 32,
        clock=lambda: 200.0,
    )


def verification_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "verification",
        b"v" * 32,
        clock=lambda: 300.0,
    )


def environment():
    backend = InMemoryFencedStore()
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer(),
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer(),
        clock=lambda: 200.0,
    )
    archives = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace="archives",
        clock=lambda: 250.0,
    )
    cursors = DurableVerificationCursorStore(
        backend,
        verification_signer(),
        namespace="verification-cursors",
    )
    verifier = DurableIncrementalVerifier(
        cursors,
        DurableVerificationPolicy(
            max_tail_items=32,
            max_items_between_full_verification=128,
            max_full_verification_age_seconds=10_000,
        ),
        clock=lambda: 300.0,
    )
    return (
        backend,
        checkpoints,
        builder,
        archives,
        cursors,
        verifier,
    )


def journal(backend):
    return DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
        clock=lambda: 10.0,
    )


def receipts(backend):
    return DistributedReceiptChain(
        backend,
        namespace="receipts",
        max_receipts=100,
    )


def append_events(chain, count, *, start=0):
    result = []
    for index in range(start, start + count):
        result.append(
            chain.append(
                "archive.incremental",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
                data={"index": index},
            )
        )
    return tuple(result)


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
        stdout_bytes=index + 1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
        metadata={"index": index},
    )


def append_receipts(chain, count, *, start=0):
    result = []
    for index in range(start, start + count):
        result.append(chain.append(make_receipt(index)))
    return tuple(result)


def archive_current(
    chain_id,
    chain,
    checkpoints,
    builder,
    archives,
):
    checkpoint = checkpoints.publish(
        chain_id,
        chain,
    )
    manifest = builder.build(
        checkpoint,
        chain,
    )
    report = archives.put(
        manifest,
        checkpoint,
        chain,
    )
    return checkpoint, manifest, report


class NoHistoricalSegments:
    """Live facade that refuses historical segment reads.

    Current head and full integrity remain available, modelling a future
    compacted live store whose archived prefix is no longer locally readable.
    """

    def __init__(self, chain):
        self.chain = chain
        self.segment_calls = 0
        self.sequence_calls = 0

    def head(self):
        return self.chain.head()

    def verify(self):
        return self.chain.verify()

    def snapshot(self):
        return self.chain.snapshot()

    def root_hash(self):
        return self.chain.root_hash()

    def length(self):
        return self.chain.length()

    def snapshot_at(self, root_hash):
        if root_hash == self.chain.root_hash():
            return self.chain.snapshot()
        raise RuntimeError("historical live prefix unavailable")

    def verify_root(self, root_hash):
        return root_hash == self.chain.root_hash() and self.chain.verify()

    def root_is_ancestor(self, root_hash):
        return root_hash == self.chain.root_hash()

    def sequence_for_root(self, root_hash):
        self.sequence_calls += 1
        if root_hash == self.chain.root_hash():
            return self.chain.head().sequence
        raise RuntimeError("historical sequence unavailable")

    def snapshot_segment(
        self,
        start_exclusive_root,
        end_inclusive_root="",
        *,
        max_items=4096,
    ):
        self.segment_calls += 1
        raise RuntimeError("historical live segment unavailable")


def test_root_replica_dataclass_has_no_recursive_replica_field():
    replica = DurableArchiveRootReplica(
        "archive",
        fp("manifest"),
    )
    assert replica.archive_id == "archive"
    assert replica.archive_manifest_digest == fp("manifest")
    assert replica.to_dict() == {
        "archive_id": "archive",
        "archive_manifest_digest": fp("manifest"),
    }
    assert not hasattr(replica, "replicas")


def test_root_index_defaults_to_primary_replica():
    index = DurableArchiveRootIndex(
        "chain",
        fp("root"),
        1,
        "archive",
        fp("manifest"),
    )
    assert len(index.replicas) == 1
    assert index.replicas[0] == DurableArchiveRootReplica(
        "archive",
        fp("manifest"),
    )


def test_root_index_accepts_explicit_replica_list():
    primary = DurableArchiveRootReplica(
        "a",
        fp("a-manifest"),
    )
    secondary = DurableArchiveRootReplica(
        "b",
        fp("b-manifest"),
    )
    index = DurableArchiveRootIndex(
        "chain",
        fp("root"),
        1,
        "a",
        fp("a-manifest"),
        (primary, secondary),
    )
    assert index.replicas == (primary, secondary)
    assert len(index.to_dict()["replicas"]) == 2


def test_root_index_rejects_replica_list_not_starting_with_primary():
    with pytest.raises(ValueError, match="primary"):
        DurableArchiveRootIndex(
            "chain",
            fp("root"),
            1,
            "a",
            fp("a-manifest"),
            (
                DurableArchiveRootReplica(
                    "b",
                    fp("b-manifest"),
                ),
            ),
        )


def test_root_index_rejects_duplicate_archive_ids():
    primary = DurableArchiveRootReplica(
        "a",
        fp("a-manifest"),
    )
    duplicate = DurableArchiveRootReplica(
        "a",
        fp("other"),
    )
    with pytest.raises(ValueError, match="duplicate"):
        DurableArchiveRootIndex(
            "chain",
            fp("root"),
            1,
            "a",
            fp("a-manifest"),
            (primary, duplicate),
        )


def test_archive_sequence_for_genesis_is_zero():
    _, _, _, archives, _, _ = environment()
    assert archives.sequence_for_root(
        "journal",
        GENESIS,
    ) == 0


def test_archive_sequence_for_historical_journal_root():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 4)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    assert archives.sequence_for_root(
        "journal",
        events[2].event_hash,
    ) == 3


def test_archive_sequence_for_unknown_root_fails_closed():
    _, _, _, archives, _, _ = environment()
    with pytest.raises(
        DurableArchiveStoreError,
        match="not archived",
    ):
        archives.sequence_for_root(
            "journal",
            fp("missing"),
        )


def test_archive_segment_from_genesis():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 4)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    assert archives.snapshot_segment(
        "journal",
        GENESIS,
        events[2].event_hash,
    ) == events[:3]


def test_archive_segment_between_historical_roots():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 6)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    assert archives.snapshot_segment(
        "journal",
        events[1].event_hash,
        events[4].event_hash,
    ) == events[2:5]


def test_archive_segment_same_root_is_empty():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    assert archives.snapshot_segment(
        "journal",
        events[0].event_hash,
        events[0].event_hash,
    ) == ()


@pytest.mark.parametrize("bound", [0, -1, True, 1.5])
def test_archive_segment_bound_validation(bound):
    _, _, _, archives, _, _ = environment()
    with pytest.raises(ValueError, match="max_items"):
        archives.snapshot_segment(
            "journal",
            GENESIS,
            fp("end"),
            max_items=bound,
        )


def test_archive_segment_enforces_bound_before_node_reads():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 6)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        archives.snapshot_segment(
            "journal",
            GENESIS,
            events[-1].event_hash,
            max_items=5,
        )


def test_archive_segment_rejects_end_genesis_after_non_genesis_start():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 1)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="end precedes",
    ):
        archives.snapshot_segment(
            "journal",
            events[0].event_hash,
            GENESIS,
        )


def test_archive_segment_rejects_unknown_end_root():
    _, _, _, archives, _, _ = environment()
    with pytest.raises(
        DurableArchiveStoreError,
        match="end root is not indexed",
    ):
        archives.snapshot_segment(
            "journal",
            GENESIS,
            fp("unknown"),
        )


def test_archive_segment_rejects_start_not_ancestor_of_end():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 4)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        archives.snapshot_segment(
            "journal",
            events[3].event_hash,
            events[1].event_hash,
        )


def test_archive_segment_uses_later_archive_replica_for_shared_root():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    first = append_events(chain, 2)
    _, first_archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    later = append_events(chain, 3, start=2)
    _, second_archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    root = first[0].event_hash
    index = archives.root_index(
        "journal",
        root,
    )
    assert tuple(
        item.archive_id
        for item in index.replicas
    ) == (
        first_archive.manifest.archive_id,
        second_archive.manifest.archive_id,
    )
    assert archives.snapshot_segment(
        "journal",
        root,
        later[-1].event_hash,
    ) == first[1:] + later


def test_archive_segment_fails_over_when_primary_archive_record_missing():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    first = append_events(chain, 2)
    _, first_archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    later = append_events(chain, 2, start=2)
    _, second_archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    start = first[0].event_hash
    end = first[1].event_hash
    index = archives.root_index(
        "journal",
        end,
    )
    assert len(index.replicas) == 2

    key = archives._archive_key(
        first_archive.manifest.archive_id
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.delete(
        archives.namespace,
        key,
        expected_revision=record.revision,
    )

    assert archives.snapshot_segment(
        "journal",
        start,
        end,
    ) == first[1:]
    resolution = archives.resolve_root(
        "journal",
        end,
    )
    assert resolution.archive_id == (
        second_archive.manifest.archive_id
    )
    assert later


def test_archive_segment_fails_if_all_archive_records_missing():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 2)
    _, first_archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    append_events(chain, 1, start=2)
    _, second_archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    for archive in (
        first_archive,
        second_archive,
    ):
        key = archives._archive_key(
            archive.manifest.archive_id
        )
        record = backend.get(
            archives.namespace,
            key,
        )
        backend.delete(
            archives.namespace,
            key,
            expected_revision=record.revision,
        )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        archives.snapshot_segment(
            "journal",
            GENESIS,
            events[-1].event_hash,
        )


def test_archive_segment_detects_archived_node_payload_tamper():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 3)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    key = archives._node_key(
        "journal",
        events[1].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered"
    raw["payload"] = payload
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        archives.snapshot_segment(
            "journal",
            events[0].event_hash,
            events[2].event_hash,
        )


def test_archive_segment_detects_manifest_entry_mismatch():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 3)
    _, archive, _ = archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    key = archives._archive_key(
        archive.manifest.archive_id
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    raw = dict(record.value)
    node_hashes = list(raw["node_hashes"])
    node_hashes[1] = events[0].event_hash
    raw["node_hashes"] = node_hashes
    # Leave record_digest unchanged; record admission must fail before nodes.
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        archives.snapshot_segment(
            "journal",
            events[0].event_hash,
            events[-1].event_hash,
        )


def test_receipt_archive_segment_between_roots():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = receipts(backend)
    items = append_receipts(chain, 5)
    archive_current(
        "receipts",
        chain,
        checkpoints,
        builder,
        archives,
    )
    assert archives.snapshot_segment(
        "receipts",
        items[0].receipt_hash,
        items[3].receipt_hash,
    ) == items[1:4]


def test_receipt_archive_segment_from_genesis():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = receipts(backend)
    items = append_receipts(chain, 3)
    archive_current(
        "receipts",
        chain,
        checkpoints,
        builder,
        archives,
    )
    assert archives.snapshot_segment(
        "receipts",
        GENESIS,
        items[-1].receipt_hash,
    ) == items


def test_archive_backed_segment_prefers_live_history():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 3)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    historical = ArchiveBackedHistoricalChain(
        "journal",
        chain,
        archives,
    )
    assert historical.snapshot_segment(
        events[0].event_hash,
        events[-1].event_hash,
    ) == events[1:]


def test_archive_backed_segment_falls_back_to_archive():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 4)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    facade = NoHistoricalSegments(chain)
    historical = ArchiveBackedHistoricalChain(
        "journal",
        facade,
        archives,
    )
    assert historical.snapshot_segment(
        events[0].event_hash,
        events[-1].event_hash,
    ) == events[1:]
    assert facade.segment_calls == 1


def test_archive_backed_sequence_falls_back_to_archive():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 4)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    facade = NoHistoricalSegments(chain)
    historical = ArchiveBackedHistoricalChain(
        "journal",
        facade,
        archives,
    )
    assert historical.sequence_for_root(
        events[1].event_hash,
    ) == 2
    assert facade.sequence_calls == 1


def test_archive_backed_segment_fails_closed_when_neither_source_has_root():
    (
        backend,
        _,
        _,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    append_events(chain, 1)
    facade = NoHistoricalSegments(chain)
    historical = ArchiveBackedHistoricalChain(
        "journal",
        facade,
        archives,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="unavailable",
    ):
        historical.snapshot_segment(
            fp("missing-start"),
            fp("missing-end"),
        )


def test_incremental_verifier_uses_archive_backed_journal_tail():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        verifier,
    ) = environment()
    chain = journal(backend)
    first = append_events(chain, 2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    facade = NoHistoricalSegments(chain)
    historical = ArchiveBackedHistoricalChain(
        "journal",
        facade,
        archives,
    )
    initial = verifier.ensure_current(
        "journal",
        historical,
    )
    assert initial.item.cursor.mode is DurableVerificationMode.FULL
    assert initial.item.cursor.sequence == 2
    assert initial.item.cursor.root_hash == first[-1].event_hash

    later = append_events(chain, 3, start=2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    updated = verifier.ensure_current(
        "journal",
        historical,
    )
    assert updated.item.cursor.mode is DurableVerificationMode.INCREMENTAL
    assert updated.item.cursor.sequence == 5
    assert updated.item.cursor.root_hash == later[-1].event_hash
    assert updated.item.cursor.verified_item_count == 3
    assert facade.segment_calls >= 1


def test_incremental_verifier_uses_archive_backed_receipt_tail():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        verifier,
    ) = environment()
    chain = receipts(backend)
    first = append_receipts(chain, 2)
    archive_current(
        "receipts",
        chain,
        checkpoints,
        builder,
        archives,
    )
    facade = NoHistoricalSegments(chain)
    historical = ArchiveBackedHistoricalChain(
        "receipts",
        facade,
        archives,
    )
    initial = verifier.ensure_current(
        "receipts",
        historical,
    )
    assert initial.item.cursor.sequence == 2
    assert initial.item.cursor.root_hash == first[-1].receipt_hash

    later = append_receipts(chain, 2, start=2)
    archive_current(
        "receipts",
        chain,
        checkpoints,
        builder,
        archives,
    )
    updated = verifier.ensure_current(
        "receipts",
        historical,
    )
    assert updated.item.cursor.mode is DurableVerificationMode.INCREMENTAL
    assert updated.item.cursor.sequence == 4
    assert updated.item.cursor.root_hash == later[-1].receipt_hash
    assert updated.item.cursor.verified_item_count == 2


def test_incremental_verifier_report_is_current_after_archive_tail():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        verifier,
    ) = environment()
    chain = journal(backend)
    append_events(chain, 2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    historical = ArchiveBackedHistoricalChain(
        "journal",
        NoHistoricalSegments(chain),
        archives,
    )
    verifier.ensure_current(
        "journal",
        historical,
    )
    append_events(chain, 1, start=2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    verifier.ensure_current(
        "journal",
        historical,
    )
    report = verifier.inspect(
        "journal",
        historical,
    )
    assert report.status is DurableVerificationStatus.CURRENT
    assert report.unverified_tail_items == 0


def test_archive_tail_respects_incremental_policy_bound():
    (
        backend,
        checkpoints,
        builder,
        archives,
        cursors,
        _,
    ) = environment()
    chain = journal(backend)
    append_events(chain, 1)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    historical = ArchiveBackedHistoricalChain(
        "journal",
        NoHistoricalSegments(chain),
        archives,
    )
    verifier = DurableIncrementalVerifier(
        cursors,
        DurableVerificationPolicy(
            max_tail_items=2,
            max_items_between_full_verification=128,
            max_full_verification_age_seconds=10_000,
        ),
        clock=lambda: 300.0,
    )
    verifier.ensure_current(
        "journal",
        historical,
    )
    append_events(chain, 3, start=1)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    report = verifier.inspect(
        "journal",
        historical,
    )
    assert report.status is DurableVerificationStatus.FULL_REQUIRED


def test_archive_backed_historical_snapshot_still_resolves_archived_root():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 3)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    historical = ArchiveBackedHistoricalChain(
        "journal",
        NoHistoricalSegments(chain),
        archives,
    )
    assert historical.snapshot_at(
        events[1].event_hash,
    ) == events[:2]
    assert historical.verify_root(
        events[1].event_hash,
    )
    assert historical.root_is_ancestor(
        events[1].event_hash,
    )


def test_archive_segment_replica_metadata_survives_fresh_repository_reader():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    first = append_events(chain, 2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    later = append_events(chain, 2, start=2)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    fresh = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer(),
        namespace=archives.namespace,
        clock=lambda: 999.0,
    )
    index = fresh.root_index(
        "journal",
        first[0].event_hash,
    )
    assert len(index.replicas) == 2
    assert fresh.snapshot_segment(
        "journal",
        first[0].event_hash,
        later[-1].event_hash,
    ) == first[1:] + later


def test_archive_segment_end_position_is_derived_from_signed_archive_not_index():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = journal(backend)
    events = append_events(chain, 3)
    archive_current(
        "journal",
        chain,
        checkpoints,
        builder,
        archives,
    )
    root = events[-1].event_hash
    key = archives._root_key(
        "journal",
        root,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    raw = dict(record.value)
    raw["sequence"] = 1
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    # The tampered index is rejected by identity/position checks rather than
    # being trusted to choose a node slice.
    with pytest.raises(
        DurableArchiveStoreError,
    ):
        archives.snapshot_segment(
            "journal",
            GENESIS,
            root,
        )


def test_archive_segment_validates_signed_object_digest():
    (
        backend,
        checkpoints,
        builder,
        archives,
        _,
        _,
    ) = environment()
    chain = receipts(backend)
    items = append_receipts(chain, 2)
    archive_current(
        "receipts",
        chain,
        checkpoints,
        builder,
        archives,
    )
    node_key = archives._node_key(
        "receipts",
        items[1].receipt_hash,
    )
    record = backend.get(
        archives.namespace,
        node_key,
    )
    raw = dict(record.value)
    raw["object_digest"] = fp("wrong-object")
    backend.compare_and_swap(
        archives.namespace,
        node_key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="all archive replicas",
    ):
        archives.snapshot_segment(
            "receipts",
            items[0].receipt_hash,
            items[1].receipt_hash,
        )

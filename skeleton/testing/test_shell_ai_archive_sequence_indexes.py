"""Indexed hot/cold durable archive lookup and readiness tests."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import (
    ArchiveBackedHistoricalChain,
    DurableArchiveRepository,
    DurableArchiveSequenceIndex,
    DurableArchiveSequenceIndexHealth,
    DurableArchiveStoreError,
)
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_hot_floor import DurableHotFloorStore
from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexOperator,
    DurableSequenceIndexPolicy,
    DurableSequenceIndexState,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.sequence_index import SequenceIndexBackfillableChain


GENESIS = "0" * 64


def fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def signer(
    key_id: str,
    byte: bytes,
    *,
    clock=lambda: 100.0,
):
    return ArtifactSigner(
        key_id,
        byte * 32,
        clock=clock,
    )


def receipt(index: int) -> ExecutionReceipt:
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


def node_hash(item) -> str:
    return str(
        getattr(
            item,
            "event_hash",
            getattr(item, "receipt_hash", ""),
        )
    )


class Fixture:
    def __init__(
        self,
        *,
        kind: str,
        archived: int = 6,
        tail: int = 3,
    ) -> None:
        self.kind = kind
        self.archived = archived
        self.tail = tail
        self.backend = InMemoryFencedStore()
        self.floor_store = DurableHotFloorStore(
            self.backend,
            signer("floor", b"f"),
            namespace=f"{kind}-floor",
            clock=lambda: 400.0,
        )
        if kind == "journal":
            self.chain = DistributedAIDecisionJournal(
                self.backend,
                namespace="journal",
                max_events=100,
                clock=lambda: 10.0,
                hot_floor_store=self.floor_store,
                hot_floor_chain_id="journal",
            )
            self.chain_id = "journal"
            self.prefix = tuple(
                self.chain.append(
                    "archive.sequence.test",
                    session_id=f"session-{index}",
                    intent_id=f"intent-{index}",
                    proposal_id=f"proposal-{index}",
                    summary=f"event {index}",
                    data={"index": index},
                )
                for index in range(archived)
            )
        elif kind == "receipts":
            self.chain = DistributedReceiptChain(
                self.backend,
                namespace="receipts",
                max_receipts=100,
                hot_floor_store=self.floor_store,
                hot_floor_chain_id="receipts",
            )
            self.chain_id = "receipts"
            self.prefix = tuple(
                self.chain.append(receipt(index))
                for index in range(archived)
            )
        else:
            raise ValueError("unknown fixture kind")

        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            signer("checkpoint", b"c"),
            namespace=f"{kind}-checkpoints",
            clock=lambda: 100.0,
        )
        self.archive_signer = signer(
            "archive",
            b"a",
            clock=lambda: 200.0,
        )
        self.builder = DurableArchiveManifestBuilder(
            self.checkpoints,
            self.archive_signer,
            clock=lambda: 200.0,
        )
        self.repository = DurableArchiveRepository(
            self.backend,
            self.checkpoints,
            self.archive_signer,
            namespace=f"{kind}-archive",
            clock=lambda: 300.0,
        )
        self.checkpoint = self.checkpoints.publish(
            self.chain_id,
            self.chain,
        )
        self.archive = self.builder.build(
            self.checkpoint,
            self.chain,
        )
        self.repository.put(
            self.archive,
            self.checkpoint,
            self.chain,
        )

        if kind == "journal":
            self.suffix = tuple(
                self.chain.append(
                    "archive.sequence.tail",
                    session_id=f"tail-session-{index}",
                    intent_id=f"tail-intent-{index}",
                    proposal_id=f"tail-proposal-{index}",
                    summary=f"tail {index}",
                    data={"index": index},
                )
                for index in range(
                    archived,
                    archived + tail,
                )
            )
        else:
            self.suffix = tuple(
                self.chain.append(receipt(index))
                for index in range(
                    archived,
                    archived + tail,
                )
            )
        self.historical = ArchiveBackedHistoricalChain(
            self.chain_id,
            self.chain,
            self.repository,
        )

    @property
    def floor_root(self) -> str:
        return node_hash(self.prefix[-1])

    def activate_floor(self) -> None:
        self.floor_store.advance(
            chain_id=self.chain_id,
            sequence=self.archived,
            root_hash=self.floor_root,
            archive_id=self.archive.manifest.archive_id,
            archive_manifest_digest=self.archive.manifest.digest,
            compaction_certificate_id=fp(
                f"{self.kind}:certificate"
            ),
            pruning_authorization_id=fp(
                f"{self.kind}:authorization"
            ),
            operation_id=fp(
                f"{self.kind}:operation"
            ),
            fencing_token=1,
        )
        for sequence in range(
            self.archived,
            0,
            -1,
        ):
            item = self.chain.get_by_sequence(sequence)
            digest = node_hash(item)
            key = (
                self.chain._event_key(digest)
                if self.kind == "journal"
                else self.chain._node_key(digest)
            )
            record = self.backend.get(
                self.chain.namespace,
                key,
            )
            self.backend.delete(
                self.chain.namespace,
                key,
                expected_revision=record.revision,
            )
            sequence_key = self.chain._sequence_key(
                sequence
            )
            index_record = self.backend.get(
                self.chain.namespace,
                sequence_key,
            )
            if index_record is not None:
                self.backend.delete(
                    self.chain.namespace,
                    sequence_key,
                    expected_revision=index_record.revision,
                )
            if self.kind == "receipts":
                receipt_key = self.chain._index_key(
                    item.receipt.receipt_id
                )
                receipt_record = self.backend.get(
                    self.chain.namespace,
                    receipt_key,
                )
                if receipt_record is not None:
                    self.backend.delete(
                        self.chain.namespace,
                        receipt_key,
                        expected_revision=receipt_record.revision,
                    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_put_creates_sequence_indexes(kind):
    fixture = Fixture(kind=kind)
    for sequence, expected in enumerate(
        fixture.prefix,
        start=1,
    ):
        index = fixture.repository.sequence_index(
            fixture.chain_id,
            sequence,
        )
        assert index is not None
        assert index.sequence == sequence
        assert index.root_hash == node_hash(expected)


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_zero_is_genesis(kind):
    fixture = Fixture(kind=kind)
    index = fixture.repository.sequence_index(
        fixture.chain_id,
        0,
    )
    assert index is not None
    assert index.sequence == 0
    assert index.root_hash == GENESIS
    assert (
        fixture.repository.root_for_sequence(
            fixture.chain_id,
            0,
        )
        == GENESIS
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_get_by_sequence_resolves_payload(kind):
    fixture = Fixture(kind=kind)
    for sequence, expected in enumerate(
        fixture.prefix,
        start=1,
    ):
        actual = fixture.repository.get_by_sequence(
            fixture.chain_id,
            sequence,
        )
        assert actual == expected


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_root_for_sequence_matches_root_index(kind):
    fixture = Fixture(kind=kind)
    for sequence in range(
        1,
        fixture.archived + 1,
    ):
        root = fixture.repository.root_for_sequence(
            fixture.chain_id,
            sequence,
        )
        root_index = fixture.repository.root_index(
            fixture.chain_id,
            root,
        )
        assert root_index is not None
        assert root_index.sequence == sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_lookup_beyond_head_rejected(kind):
    fixture = Fixture(kind=kind)
    with pytest.raises(IndexError):
        fixture.repository.root_for_sequence(
            fixture.chain_id,
            fixture.archived + 1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_index_missing_can_repair(kind):
    fixture = Fixture(kind=kind)
    sequence = 3
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    assert record is not None
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    assert (
        fixture.repository.sequence_index(
            fixture.chain_id,
            sequence,
        )
        is None
    )
    root = fixture.repository.root_for_sequence(
        fixture.chain_id,
        sequence,
        repair_missing=True,
    )
    assert root == node_hash(
        fixture.prefix[sequence - 1]
    )
    assert (
        fixture.repository.sequence_index(
            fixture.chain_id,
            sequence,
        )
        is not None
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_index_missing_fails_when_repair_disabled(kind):
    fixture = Fixture(kind=kind)
    sequence = 2
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="missing",
    ):
        fixture.repository.root_for_sequence(
            fixture.chain_id,
            sequence,
            repair_missing=False,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_index_conflict_is_fail_closed(kind):
    fixture = Fixture(kind=kind)
    sequence = 2
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    wrong = DurableArchiveSequenceIndex(
        fixture.chain_id,
        sequence,
        node_hash(fixture.prefix[sequence]),
    )
    fixture.backend.compare_and_swap(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
        value=wrong.to_dict(),
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="disagreement|unverifiable|root",
    ):
        fixture.repository.root_for_sequence(
            fixture.chain_id,
            sequence,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_index_wrong_value_type_is_corruption(kind):
    fixture = Fixture(kind=kind)
    sequence = 2
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    with pytest.raises(DurableArchiveStoreError):
        fixture.repository.sequence_index(
            fixture.chain_id,
            sequence,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_health_is_healthy_after_put(kind):
    fixture = Fixture(kind=kind)
    health = fixture.repository.inspect_sequence_indexes(
        fixture.chain_id,
    )
    assert health.healthy
    assert health.inspected == fixture.archived
    assert health.indexed == fixture.archived
    assert health.missing == 0
    assert health.corrupt == 0


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_health_detects_missing(kind):
    fixture = Fixture(kind=kind)
    sequence = 4
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    health = fixture.repository.inspect_sequence_indexes(
        fixture.chain_id,
    )
    assert not health.healthy
    assert health.missing == 1
    assert health.corrupt == 0
    assert health.first_missing_sequence == sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_health_detects_conflict(kind):
    fixture = Fixture(kind=kind)
    sequence = 4
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
        value=DurableArchiveSequenceIndex(
            fixture.chain_id,
            sequence,
            node_hash(fixture.prefix[0]),
        ).to_dict(),
    )
    health = fixture.repository.inspect_sequence_indexes(
        fixture.chain_id,
    )
    assert not health.healthy
    assert health.corrupt == 1
    assert health.first_corrupt_sequence == sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_repair_restores_missing_indexes(kind):
    fixture = Fixture(kind=kind)
    for sequence in (2, 4, 6):
        key = fixture.repository._sequence_key(
            fixture.chain_id,
            sequence,
        )
        record = fixture.backend.get(
            fixture.repository.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.repository.namespace,
            key,
            expected_revision=record.revision,
        )
    before = fixture.repository.inspect_sequence_indexes(
        fixture.chain_id,
    )
    assert before.missing == 3
    after = fixture.repository.repair_sequence_indexes(
        fixture.chain_id,
    )
    assert after.healthy
    assert after.missing == 0
    assert after.indexed == fixture.archived


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_repair_refuses_conflict(kind):
    fixture = Fixture(kind=kind)
    sequence = 3
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
        value=DurableArchiveSequenceIndex(
            fixture.chain_id,
            sequence,
            node_hash(fixture.prefix[0]),
        ).to_dict(),
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="different historical root",
    ):
        fixture.repository.repair_sequence_indexes(
            fixture.chain_id,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_health_respects_end_sequence(kind):
    fixture = Fixture(kind=kind)
    health = fixture.repository.inspect_sequence_indexes(
        fixture.chain_id,
        end_sequence=3,
    )
    assert health.inspected == 3
    assert health.indexed == 3
    assert health.head_sequence == fixture.archived


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_sequence_health_is_bounded(kind):
    fixture = Fixture(kind=kind)
    with pytest.raises(
        DurableArchiveStoreError,
        match="bounded",
    ):
        fixture.repository.inspect_sequence_indexes(
            fixture.chain_id,
            max_items=fixture.archived - 1,
        )
    with pytest.raises(
        DurableArchiveStoreError,
        match="bounded",
    ):
        fixture.repository.repair_sequence_indexes(
            fixture.chain_id,
            max_items=fixture.archived - 1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_get_by_sequence_before_pruning(kind):
    fixture = Fixture(kind=kind)
    for sequence in range(
        1,
        fixture.archived + fixture.tail + 1,
    ):
        expected = (
            fixture.prefix + fixture.suffix
        )[sequence - 1]
        assert (
            fixture.historical.get_by_sequence(
                sequence
            )
            == expected
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_root_for_sequence_before_pruning(kind):
    fixture = Fixture(kind=kind)
    expected = fixture.prefix + fixture.suffix
    for sequence, item in enumerate(
        expected,
        start=1,
    ):
        assert (
            fixture.historical.root_for_sequence(
                sequence
            )
            == node_hash(item)
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_sequence_lookup_after_pruning(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    assert fixture.chain.hot_length() == fixture.tail
    for sequence, expected in enumerate(
        fixture.prefix + fixture.suffix,
        start=1,
    ):
        actual = fixture.historical.get_by_sequence(
            sequence
        )
        assert actual == expected


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_root_lookup_after_pruning(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    for sequence, expected in enumerate(
        fixture.prefix + fixture.suffix,
        start=1,
    ):
        assert (
            fixture.historical.root_for_sequence(
                sequence
            )
            == node_hash(expected)
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_floor_boundary_lookup(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    assert (
        fixture.historical.root_for_sequence(
            fixture.archived
        )
        == fixture.floor_root
    )
    first_hot = fixture.historical.get_by_sequence(
        fixture.archived + 1
    )
    assert first_hot == fixture.suffix[0]
    assert (
        str(first_hot.previous_hash)
        == fixture.floor_root
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_snapshot_range_fully_archived(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    items = fixture.historical.snapshot_range(
        2,
        4,
        max_items=3,
    )
    assert items == fixture.prefix[1:4]


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_snapshot_range_fully_hot(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    start = fixture.archived + 1
    end = fixture.archived + fixture.tail
    items = fixture.historical.snapshot_range(
        start,
        end,
        max_items=fixture.tail,
    )
    assert items == fixture.suffix


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_snapshot_range_crosses_floor(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    start = fixture.archived - 1
    end = fixture.archived + 2
    items = fixture.historical.snapshot_range(
        start,
        end,
        max_items=4,
    )
    assert items == (
        fixture.prefix[-2:]
        + fixture.suffix[:2]
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_snapshot_range_is_bounded(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    with pytest.raises(
        DurableArchiveStoreError,
        match="bounded",
    ):
        fixture.historical.snapshot_range(
            1,
            fixture.archived + fixture.tail,
            max_items=2,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_snapshot_range_rejects_beyond_head(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    with pytest.raises(IndexError):
        fixture.historical.snapshot_range(
            1,
            fixture.archived + fixture.tail + 1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_index_health_before_pruning_uses_live_chain(kind):
    fixture = Fixture(kind=kind)
    health = fixture.historical.inspect_sequence_indexes(
        max_items=20,
    )
    assert health.healthy
    assert health.inspected == fixture.archived + fixture.tail
    assert health.head_sequence == fixture.archived + fixture.tail


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_index_health_after_pruning_merges_hot_and_cold(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    health = fixture.historical.inspect_sequence_indexes(
        max_items=20,
    )
    assert health.healthy
    assert health.head_sequence == fixture.archived + fixture.tail
    assert health.inspected == fixture.archived + fixture.tail
    assert health.indexed == fixture.archived + fixture.tail


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_health_detects_archived_missing_index(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = 2
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    health = fixture.historical.inspect_sequence_indexes(
        max_items=20,
    )
    assert not health.healthy
    assert health.missing == 1
    assert health.first_missing_sequence == sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_repair_restores_archived_missing_index(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = 2
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    health = fixture.historical.repair_sequence_indexes(
        max_items=20,
    )
    assert health.healthy
    assert (
        fixture.repository.sequence_index(
            fixture.chain_id,
            sequence,
        )
        is not None
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_health_detects_live_missing_index(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = fixture.archived + 1
    key = fixture.chain._sequence_key(
        sequence
    )
    record = fixture.backend.get(
        fixture.chain.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.chain.namespace,
        key,
        expected_revision=record.revision,
    )
    health = fixture.historical.inspect_sequence_indexes(
        max_items=20,
    )
    assert not health.healthy
    assert health.missing == 1
    assert health.first_missing_sequence == sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_repair_restores_live_missing_index(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = fixture.archived + 1
    key = fixture.chain._sequence_key(
        sequence
    )
    record = fixture.backend.get(
        fixture.chain.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.chain.namespace,
        key,
        expected_revision=record.revision,
    )
    health = fixture.historical.repair_sequence_indexes(
        max_items=20,
    )
    assert health.healthy
    assert fixture.chain.get_by_sequence(
        sequence,
        repair_missing=False,
    ) == fixture.suffix[0]


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_health_bound_applies_to_full_logical_chain(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    with pytest.raises(
        DurableArchiveStoreError,
        match="bounded",
    ):
        fixture.historical.inspect_sequence_indexes(
            max_items=fixture.archived + fixture.tail - 1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_durable_sequence_operator_accepts_archive_backed_chain(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            max_items_per_chain=20,
            max_chains=2,
            allow_missing_repair=True,
            require_healthy=True,
            verify_sample_windows=True,
            sample_window_items=2,
        )
    )
    report = operator.require_healthy(
        {
            fixture.chain_id: fixture.historical,
        }
    )
    assert report.ok
    assert report.healthy == 1
    assert (
        report.chains[0].state
        is DurableSequenceIndexState.HEALTHY
    )
    assert report.chains[0].sample_windows_verified >= 2


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_durable_sequence_operator_repairs_archive_backed_missing_index(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = 3
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            max_items_per_chain=20,
            allow_missing_repair=True,
            sample_window_items=2,
        )
    )
    before = operator.inspect(
        {fixture.chain_id: fixture.historical}
    )
    assert before.missing == 1
    after = operator.repair(
        {fixture.chain_id: fixture.historical}
    )
    assert after.ok
    assert after.repaired == 1


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_durable_sequence_operator_refuses_archive_conflict(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = 3
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
        value=DurableArchiveSequenceIndex(
            fixture.chain_id,
            sequence,
            node_hash(fixture.prefix[0]),
        ).to_dict(),
    )
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            max_items_per_chain=20,
            allow_missing_repair=True,
            sample_window_items=2,
        )
    )
    report = operator.inspect(
        {fixture.chain_id: fixture.historical}
    )
    assert report.corrupt == 1
    assert (
        report.chains[0].state
        is DurableSequenceIndexState.CORRUPT
    )
    repaired = operator.repair(
        {fixture.chain_id: fixture.historical}
    )
    assert not repaired.ok
    assert repaired.corrupt == 1


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_fresh_archive_reader_uses_persisted_sequence_indexes(kind):
    fixture = Fixture(kind=kind)
    fresh = DurableArchiveRepository(
        fixture.backend,
        fixture.checkpoints,
        fixture.archive_signer,
        namespace=fixture.repository.namespace,
        clock=lambda: 999.0,
    )
    for sequence in range(1, fixture.archived + 1):
        assert (
            fresh.root_for_sequence(
                fixture.chain_id,
                sequence,
                repair_missing=False,
            )
            == node_hash(
                fixture.prefix[sequence - 1]
            )
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_fresh_hot_cold_reader_uses_archive_indexes_after_pruning(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    fresh_archive = DurableArchiveRepository(
        fixture.backend,
        fixture.checkpoints,
        fixture.archive_signer,
        namespace=fixture.repository.namespace,
        clock=lambda: 999.0,
    )
    fresh = ArchiveBackedHistoricalChain(
        fixture.chain_id,
        fixture.chain,
        fresh_archive,
    )
    for sequence, expected in enumerate(
        fixture.prefix + fixture.suffix,
        start=1,
    ):
        assert fresh.get_by_sequence(
            sequence,
            repair_missing=False,
        ) == expected


def test_sequence_index_dataclass_validation():
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndex(
            "",
            1,
            fp("root"),
        )
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndex(
            "chain",
            -1,
            fp("root"),
        )
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndex(
            "chain",
            0,
            fp("root"),
        )
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndex(
            "chain",
            1,
            GENESIS,
        )
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndex(
            "chain",
            1,
            "bad",
        )


def test_sequence_index_health_validation():
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndexHealth(
            -1,
            0,
            0,
            0,
            0,
        )
    with pytest.raises(ValueError):
        DurableArchiveSequenceIndexHealth(
            1,
            1,
            1,
            0,
            0,
            first_missing_sequence=0,
        )
    health = DurableArchiveSequenceIndexHealth(
        5,
        5,
        5,
        0,
        0,
    )
    assert health.healthy
    assert health.to_dict()["healthy"] is True


@pytest.mark.parametrize(
    "sequence",
    [-1, True, 1.5],
)
def test_repository_sequence_validation(sequence):
    fixture = Fixture(kind="journal")
    with pytest.raises(ValueError):
        fixture.repository.sequence_index(
            fixture.chain_id,
            sequence,
        )


@pytest.mark.parametrize(
    "sequence",
    [-1, True, 1.5],
)
def test_archive_backed_root_sequence_validation(sequence):
    fixture = Fixture(kind="journal")
    with pytest.raises(ValueError):
        fixture.historical.root_for_sequence(
            sequence
        )


@pytest.mark.parametrize(
    "sequence",
    [0, -1, True, 1.5],
)
def test_archive_backed_get_sequence_validation(sequence):
    fixture = Fixture(kind="journal")
    with pytest.raises(ValueError):
        fixture.historical.get_by_sequence(
            sequence
        )


def test_archive_backed_range_validation():
    fixture = Fixture(kind="journal")
    with pytest.raises(ValueError):
        fixture.historical.snapshot_range(
            0,
            1,
        )
    with pytest.raises(ValueError):
        fixture.historical.snapshot_range(
            2,
            1,
        )
    with pytest.raises(ValueError):
        fixture.historical.snapshot_range(
            1,
            1,
            max_items=0,
        )

@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_batch_backfill_repairs_in_bounded_chunks(kind):
    fixture = Fixture(kind=kind)
    for sequence in range(1, fixture.archived + 1):
        key = fixture.repository._sequence_key(
            fixture.chain_id,
            sequence,
        )
        record = fixture.backend.get(
            fixture.repository.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.repository.namespace,
            key,
            expected_revision=record.revision,
        )

    first = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        max_items=2,
    )
    assert first.requested_end_sequence == fixture.archived
    assert first.covered_start_sequence == fixture.archived - 1
    assert first.covered_end_sequence == fixture.archived
    assert first.indexed == 2
    assert first.already_indexed == 0
    assert first.next_sequence == fixture.archived - 2
    assert not first.complete_to_genesis

    second = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        end_sequence=first.next_sequence,
        end_root=first.next_root,
        max_items=2,
    )
    assert second.covered_end_sequence == fixture.archived - 2
    assert second.indexed == 2
    assert second.next_sequence == fixture.archived - 4

    third = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        end_sequence=second.next_sequence,
        end_root=second.next_root,
        max_items=2,
    )
    assert third.indexed == 2
    assert third.next_sequence == 0
    assert third.next_root == GENESIS
    assert third.complete_to_genesis

    health = fixture.repository.inspect_sequence_indexes(
        fixture.chain_id,
    )
    assert health.healthy


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_batch_backfill_counts_existing_indexes(kind):
    fixture = Fixture(kind=kind)
    batch = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        max_items=3,
    )
    assert batch.indexed == 0
    assert batch.already_indexed == 3
    assert batch.covered_items == 3


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_batch_backfill_rejects_wrong_root(kind):
    fixture = Fixture(kind=kind)
    with pytest.raises(
        DurableArchiveStoreError,
        match="root/sequence mismatch",
    ):
        fixture.repository.backfill_sequence_indexes_batch(
            fixture.chain_id,
            end_sequence=3,
            end_root=node_hash(
                fixture.prefix[0]
            ),
            max_items=2,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_batch_backfill_zero_is_complete(kind):
    fixture = Fixture(kind=kind)
    batch = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        end_sequence=0,
        max_items=2,
    )
    assert batch.requested_end_sequence == 0
    assert batch.requested_end_root == GENESIS
    assert batch.covered_start_sequence is None
    assert batch.covered_end_sequence is None
    assert batch.covered_items == 0
    assert batch.next_sequence == 0
    assert batch.next_root == GENESIS
    assert batch.complete_to_genesis


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_batch_backfill_rejects_conflicting_locator(kind):
    fixture = Fixture(kind=kind)
    sequence = fixture.archived
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.compare_and_swap(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
        value=DurableArchiveSequenceIndex(
            fixture.chain_id,
            sequence,
            node_hash(fixture.prefix[0]),
        ).to_dict(),
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="conflicting sequence index",
    ):
        fixture.repository.backfill_sequence_indexes_batch(
            fixture.chain_id,
            max_items=1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_hot_cold_batch_backfill_can_cross_floor_in_one_call(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()

    # Remove all archive indexes.
    for sequence in range(1, fixture.archived + 1):
        key = fixture.repository._sequence_key(
            fixture.chain_id,
            sequence,
        )
        record = fixture.backend.get(
            fixture.repository.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.repository.namespace,
            key,
            expected_revision=record.revision,
        )

    # Remove the live suffix indexes.
    for sequence in range(
        fixture.archived + 1,
        fixture.archived + fixture.tail + 1,
    ):
        key = fixture.chain._sequence_key(
            sequence
        )
        record = fixture.backend.get(
            fixture.chain.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.chain.namespace,
            key,
            expected_revision=record.revision,
        )

    batch = fixture.historical.backfill_sequence_indexes_batch(
        max_items=fixture.tail + 2,
    )
    assert batch.requested_end_sequence == (
        fixture.archived + fixture.tail
    )
    assert batch.covered_items == fixture.tail + 2
    assert batch.indexed == fixture.tail + 2
    assert batch.next_sequence == fixture.archived - 2
    assert batch.next_root == node_hash(
        fixture.prefix[fixture.archived - 3]
    )
    assert not batch.complete_to_genesis

    # The live tail is now fully repaired.
    for sequence in range(
        fixture.archived + 1,
        fixture.archived + fixture.tail + 1,
    ):
        fixture.chain.get_by_sequence(
            sequence,
            repair_missing=False,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_hot_cold_batch_backfill_stops_exactly_at_floor_when_budget_matches_tail(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    for sequence in range(
        fixture.archived + 1,
        fixture.archived + fixture.tail + 1,
    ):
        key = fixture.chain._sequence_key(
            sequence
        )
        record = fixture.backend.get(
            fixture.chain.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.chain.namespace,
            key,
            expected_revision=record.revision,
        )
    batch = fixture.historical.backfill_sequence_indexes_batch(
        max_items=fixture.tail,
    )
    assert batch.covered_items == fixture.tail
    assert batch.next_sequence == fixture.archived
    assert batch.next_root == fixture.floor_root
    assert not batch.complete_to_genesis


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_hot_cold_batch_backfill_below_floor_uses_archive_only(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    sequence = fixture.archived - 1
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    batch = fixture.historical.backfill_sequence_indexes_batch(
        end_sequence=sequence,
        end_root=node_hash(
            fixture.prefix[sequence - 1]
        ),
        max_items=1,
    )
    assert batch.indexed == 1
    assert batch.covered_start_sequence == sequence
    assert batch.covered_end_sequence == sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_hot_cold_batch_backfill_requires_root_for_non_head_sequence(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    with pytest.raises(
        ValueError,
        match="explicit root",
    ):
        fixture.historical.backfill_sequence_indexes_batch(
            end_sequence=fixture.archived + 1,
            max_items=1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_hot_cold_batch_backfill_rejects_root_sequence_mismatch(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    with pytest.raises(
        DurableArchiveStoreError,
        match="root/sequence mismatch",
    ):
        fixture.historical.backfill_sequence_indexes_batch(
            end_sequence=fixture.archived + 1,
            end_root=node_hash(
                fixture.suffix[-1]
            ),
            max_items=1,
        )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_archive_backed_chain_satisfies_backfillable_protocol(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()
    assert isinstance(
        fixture.historical,
        SequenceIndexBackfillableChain,
    )


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_batch_backfill_fresh_reader_resumes_cursor(kind):
    fixture = Fixture(kind=kind)
    for sequence in range(1, fixture.archived + 1):
        key = fixture.repository._sequence_key(
            fixture.chain_id,
            sequence,
        )
        record = fixture.backend.get(
            fixture.repository.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.repository.namespace,
            key,
            expected_revision=record.revision,
        )
    first = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        max_items=2,
    )

    fresh = DurableArchiveRepository(
        fixture.backend,
        fixture.checkpoints,
        fixture.archive_signer,
        namespace=fixture.repository.namespace,
        clock=lambda: 999.0,
    )
    second = fresh.backfill_sequence_indexes_batch(
        fixture.chain_id,
        end_sequence=first.next_sequence,
        end_root=first.next_root,
        max_items=2,
    )
    assert second.indexed == 2
    assert second.covered_end_sequence == first.next_sequence


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_batch_backfill_is_idempotent_on_retry(kind):
    fixture = Fixture(kind=kind)
    sequence = fixture.archived
    key = fixture.repository._sequence_key(
        fixture.chain_id,
        sequence,
    )
    record = fixture.backend.get(
        fixture.repository.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.repository.namespace,
        key,
        expected_revision=record.revision,
    )
    first = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        max_items=1,
    )
    assert first.indexed == 1
    retry = fixture.repository.backfill_sequence_indexes_batch(
        fixture.chain_id,
        max_items=1,
    )
    assert retry.indexed == 0
    assert retry.already_indexed == 1


@pytest.mark.parametrize("kind", ["journal", "receipts"])
def test_hot_cold_batch_backfill_full_repair_with_cursor_loop(kind):
    fixture = Fixture(kind=kind)
    fixture.activate_floor()

    for sequence in range(1, fixture.archived + 1):
        key = fixture.repository._sequence_key(
            fixture.chain_id,
            sequence,
        )
        record = fixture.backend.get(
            fixture.repository.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.repository.namespace,
            key,
            expected_revision=record.revision,
        )
    for sequence in range(
        fixture.archived + 1,
        fixture.archived + fixture.tail + 1,
    ):
        key = fixture.chain._sequence_key(
            sequence
        )
        record = fixture.backend.get(
            fixture.chain.namespace,
            key,
        )
        fixture.backend.delete(
            fixture.chain.namespace,
            key,
            expected_revision=record.revision,
        )

    end_sequence = None
    end_root = ""
    batches = []
    while True:
        batch = fixture.historical.backfill_sequence_indexes_batch(
            end_sequence=end_sequence,
            end_root=end_root,
            max_items=2,
        )
        batches.append(batch)
        if batch.complete_to_genesis:
            break
        end_sequence = batch.next_sequence
        end_root = batch.next_root

    assert sum(
        item.indexed
        for item in batches
    ) == fixture.archived + fixture.tail
    assert fixture.historical.inspect_sequence_indexes(
        max_items=20,
    ).healthy
    assert batches[-1].next_sequence == 0
    assert batches[-1].next_root == GENESIS

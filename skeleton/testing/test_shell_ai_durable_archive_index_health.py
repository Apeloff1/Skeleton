"""Durable archive root-index health and repairability tests."""

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
    DurableArchiveHead,
    DurableArchiveIndexHealth,
    DurableArchiveIndexState,
    DurableArchiveRepository,
    DurableArchiveRootIndex,
    DurableArchiveRootReplica,
    DurableArchiveStoreError,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)


GENESIS = "0" * 64


def signer(
    key_id: str,
    byte: bytes,
    *,
    now: float,
) -> ArtifactSigner:
    return ArtifactSigner(
        key_id,
        byte * 32,
        clock=lambda: now,
    )


def fixture():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        max_events=100,
        clock=lambda: 10.0,
    )
    checkpoint_signer = signer(
        "checkpoint",
        b"c",
        now=100.0,
    )
    archive_signer = signer(
        "archive",
        b"a",
        now=200.0,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        checkpoint_signer,
        namespace="checkpoints",
        clock=lambda: 100.0,
    )
    builder = DurableArchiveManifestBuilder(
        checkpoints,
        archive_signer,
        clock=lambda: 200.0,
    )
    archives = DurableArchiveRepository(
        backend,
        checkpoints,
        archive_signer,
        namespace="archives",
        clock=lambda: 250.0,
    )
    return (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    )


def append_events(
    journal,
    count,
    *,
    start=0,
):
    return tuple(
        journal.append(
            "archive.health",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
            summary=f"event {index}",
            data={"index": index},
        )
        for index in range(
            start,
            start + count,
        )
    )


def archive_current(
    journal,
    checkpoints,
    builder,
    archives,
):
    checkpoint = checkpoints.publish(
        "journal",
        journal,
    )
    archive = builder.build(
        checkpoint,
        journal,
    )
    report = archives.put(
        archive,
        checkpoint,
        journal,
    )
    return checkpoint, archive, report


def root_key(
    archives,
    root_hash,
):
    return archives._root_key(
        "journal",
        root_hash,
    )


def delete_key(
    backend,
    namespace,
    key,
):
    record = backend.get(
        namespace,
        key,
    )
    assert record is not None
    backend.delete(
        namespace,
        key,
        expected_revision=record.revision,
    )


def test_healthy_archive_index_report():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(
        journal,
        3,
    )
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.HEALTHY
    assert health.archive_valid
    assert health.expected_root_indexes == 4
    assert health.root_indexes_present == 4
    assert health.replica_bindings_present == 4
    assert health.missing_root_indexes == ()
    assert health.missing_replica_roots == ()
    assert health.corrupt_root_indexes == ()
    assert not health.head_repair_required
    assert health.head_valid
    assert health.missing == 0
    assert health.corrupt == 0
    assert health.healthy
    assert not health.repairable
    assert events[-1].event_hash == archive.manifest.checkpoint_root


def test_missing_genesis_root_index_is_degraded_repairable():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        root_key(
            archives,
            GENESIS,
        ),
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.DEGRADED
    assert health.repairable
    assert health.missing_root_indexes == (
        GENESIS,
    )
    assert health.missing == 1
    assert health.corrupt == 0


def test_missing_historical_root_index_is_degraded():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 3)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        root_key(
            archives,
            events[1].event_hash,
        ),
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.repairable
    assert health.missing_root_indexes == (
        events[1].event_hash,
    )
    assert health.root_indexes_present == 3
    assert health.replica_bindings_present == 3


def test_missing_archive_replica_binding_is_degraded():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    first_events = append_events(
        journal,
        2,
    )
    _, first_archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    append_events(
        journal,
        2,
        start=2,
    )
    _, second_archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    root = first_events[0].event_hash
    key = root_key(
        archives,
        root,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    index = archives._root_index(
        dict(record.value)
    )
    assert len(index.replicas) == 2
    only_first = replace(
        index,
        replicas=(
            index.replicas[0],
        ),
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=only_first.to_dict(),
    )
    health = archives.inspect_indexes(
        second_archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.DEGRADED
    assert health.repairable
    assert health.missing_replica_roots == (
        root,
    )
    assert first_archive.manifest.archive_id != second_archive.manifest.archive_id


def test_missing_archive_head_is_degraded_repairable():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        archives._head_key(
            "journal"
        ),
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.DEGRADED
    assert health.head_repair_required
    assert health.head_valid
    assert health.repairable
    assert health.missing == 1


def test_stale_older_head_is_degraded_repairable():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    first_events = append_events(
        journal,
        1,
    )
    _, first_archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    append_events(
        journal,
        2,
        start=1,
    )
    _, second_archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._head_key(
        "journal"
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    stale = DurableArchiveHead(
        "journal",
        1,
        first_events[-1].event_hash,
        first_archive.manifest.archive_id,
        first_archive.manifest.digest,
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=stale.to_dict(),
    )
    health = archives.inspect_indexes(
        second_archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.DEGRADED
    assert health.head_repair_required
    assert health.repairable


def test_newer_head_does_not_degrade_older_archive():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 1)
    _, first_archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    append_events(
        journal,
        2,
        start=1,
    )
    archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    health = archives.inspect_indexes(
        first_archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.HEALTHY
    assert not health.head_repair_required
    assert health.head_valid


def test_wrong_root_index_sequence_is_invalid():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = root_key(
        archives,
        events[-1].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    index = archives._root_index(
        dict(record.value)
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            index,
            sequence=index.sequence + 1,
        ).to_dict(),
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.INVALID
    assert not health.repairable
    assert health.corrupt_root_indexes == (
        events[-1].event_hash,
    )


def test_wrong_root_index_chain_is_invalid():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = root_key(
        archives,
        events[-1].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    raw = dict(record.value)
    raw["chain_id"] = "other"
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.INVALID
    assert health.corrupt >= 1


def test_wrong_replica_manifest_digest_is_invalid():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = root_key(
        archives,
        events[0].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    index = archives._root_index(
        dict(record.value)
    )
    bad_replica = DurableArchiveRootReplica(
        archive.manifest.archive_id,
        "f" * 64,
    )
    bad = replace(
        index,
        replicas=(
            bad_replica,
        ),
        archive_manifest_digest="f" * 64,
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=bad.to_dict(),
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.INVALID
    assert events[0].event_hash in health.corrupt_root_indexes


def test_malformed_root_index_record_is_invalid():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = root_key(
        archives,
        events[0].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.INVALID
    assert health.corrupt_root_indexes == (
        events[0].event_hash,
    )


def test_same_sequence_conflicting_head_is_invalid():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._head_key(
        "journal"
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    bad = DurableArchiveHead(
        "journal",
        archive.manifest.checkpoint_sequence,
        events[0].event_hash,
        "other-archive",
        "f" * 64,
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=bad.to_dict(),
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.INVALID
    assert not health.head_valid
    assert health.corrupt >= 1


def test_malformed_head_record_is_invalid():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._head_key(
        "journal"
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert health.state is DurableArchiveIndexState.INVALID
    assert not health.head_valid


def test_invalid_archive_payload_reports_invalid_health():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    archive_key = archives._archive_key(
        archive.manifest.archive_id
    )
    record = backend.get(
        archives.namespace,
        archive_key,
    )
    raw = dict(record.value)
    raw["record_digest"] = "f" * 64
    backend.compare_and_swap(
        archives.namespace,
        archive_key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableArchiveStoreError,
    ):
        archives.inspect_indexes(
            archive.manifest.archive_id
        )


def test_missing_archive_raises():
    _, _, _, _, archives = fixture()
    with pytest.raises(
        DurableArchiveStoreError,
        match="missing",
    ):
        archives.inspect_indexes(
            "missing"
        )


def test_repair_indexes_restores_missing_root_health():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        root_key(
            archives,
            events[0].event_hash,
        ),
    )
    assert archives.inspect_indexes(
        archive.manifest.archive_id
    ).repairable
    repaired = archives.repair_indexes(
        archive.manifest.archive_id
    )
    assert repaired >= 1
    assert archives.inspect_indexes(
        archive.manifest.archive_id
    ).healthy


def test_repair_indexes_restores_missing_replica():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    first = append_events(journal, 2)
    archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    append_events(
        journal,
        1,
        start=2,
    )
    _, second_archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    root = first[0].event_hash
    key = root_key(
        archives,
        root,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    index = archives._root_index(
        dict(record.value)
    )
    without_second = replace(
        index,
        replicas=(
            index.replicas[0],
        ),
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=without_second.to_dict(),
    )
    assert archives.inspect_indexes(
        second_archive.manifest.archive_id
    ).repairable
    archives.repair_indexes(
        second_archive.manifest.archive_id
    )
    assert archives.inspect_indexes(
        second_archive.manifest.archive_id
    ).healthy


def test_repair_indexes_restores_missing_head():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        archives._head_key(
            "journal"
        ),
    )
    assert archives.inspect_indexes(
        archive.manifest.archive_id
    ).head_repair_required
    archives.repair_indexes(
        archive.manifest.archive_id
    )
    assert archives.inspect_indexes(
        archive.manifest.archive_id
    ).healthy


def test_repair_indexes_refuses_conflicting_root_position():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = root_key(
        archives,
        events[0].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    index = archives._root_index(
        dict(record.value)
    )
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            index,
            sequence=9,
        ).to_dict(),
    )
    with pytest.raises(
        DurableArchiveStoreError,
        match="incompatible historical position",
    ):
        archives.repair_indexes(
            archive.manifest.archive_id
        )


def test_health_digest_is_stable():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 2)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    first = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    second = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_health_digest_changes_when_index_removed():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    healthy = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    delete_key(
        backend,
        archives.namespace,
        root_key(
            archives,
            events[0].event_hash,
        ),
    )
    degraded = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    assert degraded.digest != healthy.digest


def test_health_serialization():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
    ) = fixture()
    append_events(journal, 1)
    _, archive, _ = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    data = health.to_dict()
    assert data["archive_id"] == archive.manifest.archive_id
    assert data["chain_id"] == "journal"
    assert data["state"] == "healthy"
    assert data["archive_valid"] is True
    assert data["healthy"] is True
    assert data["repairable"] is False
    assert data["missing"] == 0
    assert data["corrupt"] == 0
    assert data["expected_root_indexes"] == 2


def test_health_accepts_string_state():
    health = DurableArchiveIndexHealth(
        "archive",
        "chain",
        "healthy",
        True,
        1,
        1,
        1,
        (),
        (),
        (),
        False,
        True,
    )
    assert health.state is DurableArchiveIndexState.HEALTHY


@pytest.mark.parametrize(
    "field,value",
    [
        ("archive_valid", 1),
        ("head_repair_required", 1),
        ("head_valid", 1),
    ],
)
def test_health_boolean_validation(field, value):
    values = dict(
        archive_id="archive",
        chain_id="chain",
        state=DurableArchiveIndexState.HEALTHY,
        archive_valid=True,
        expected_root_indexes=1,
        root_indexes_present=1,
        replica_bindings_present=1,
        missing_root_indexes=(),
        missing_replica_roots=(),
        corrupt_root_indexes=(),
        head_repair_required=False,
        head_valid=True,
    )
    values[field] = value
    with pytest.raises(ValueError, match="bool"):
        DurableArchiveIndexHealth(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_root_indexes", -1),
        ("root_indexes_present", -1),
        ("replica_bindings_present", -1),
        ("expected_root_indexes", True),
    ],
)
def test_health_count_validation(field, value):
    values = dict(
        archive_id="archive",
        chain_id="chain",
        state=DurableArchiveIndexState.HEALTHY,
        archive_valid=True,
        expected_root_indexes=1,
        root_indexes_present=1,
        replica_bindings_present=1,
        missing_root_indexes=(),
        missing_replica_roots=(),
        corrupt_root_indexes=(),
        head_repair_required=False,
        head_valid=True,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableArchiveIndexHealth(**values)


def test_health_rejects_present_count_above_expected():
    with pytest.raises(ValueError, match="exceeds"):
        DurableArchiveIndexHealth(
            "archive",
            "chain",
            "healthy",
            True,
            1,
            2,
            1,
            (),
            (),
            (),
            False,
            True,
        )


def test_health_rejects_duplicate_missing_roots():
    with pytest.raises(ValueError, match="duplicate"):
        DurableArchiveIndexHealth(
            "archive",
            "chain",
            "degraded",
            True,
            2,
            0,
            0,
            ("a" * 64, "a" * 64),
            (),
            (),
            False,
            True,
        )


def test_health_rejects_bad_root_digest():
    with pytest.raises(ValueError):
        DurableArchiveIndexHealth(
            "archive",
            "chain",
            "degraded",
            True,
            1,
            0,
            0,
            ("bad",),
            (),
            (),
            False,
            True,
        )


def test_health_invalid_archive_is_not_repairable():
    health = DurableArchiveIndexHealth(
        "archive",
        "chain",
        DurableArchiveIndexState.INVALID,
        False,
        2,
        0,
        0,
        (),
        (),
        (),
        False,
        True,
    )
    assert not health.healthy
    assert not health.repairable


def test_head_only_gap_counts_as_one_missing():
    health = DurableArchiveIndexHealth(
        "archive",
        "chain",
        DurableArchiveIndexState.DEGRADED,
        True,
        2,
        2,
        2,
        (),
        (),
        (),
        True,
        True,
    )
    assert health.missing == 1
    assert health.repairable


def test_bad_head_counts_as_corrupt():
    health = DurableArchiveIndexHealth(
        "archive",
        "chain",
        DurableArchiveIndexState.INVALID,
        True,
        2,
        2,
        2,
        (),
        (),
        (),
        False,
        False,
    )
    assert health.corrupt == 1
    assert not health.repairable

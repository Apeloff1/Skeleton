"""Bounded durable archive-index repair workflow tests."""

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
    DurableArchiveHead,
    DurableArchiveIndexState,
    DurableArchiveRepository,
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
    now: float,
):
    return ArtifactSigner(
        key_id,
        byte * 32,
        clock=lambda: now,
    )


def fixture(*, policy=None):
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
        100.0,
    )
    archive_signer = signer(
        "archive",
        b"a",
        200.0,
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
    coordinator = DurableArchiveIndexRepairCoordinator(
        archives,
        policy,
        clock=lambda: 300.0,
    )
    return (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    )


def append_events(
    journal,
    count,
    *,
    start=0,
):
    return tuple(
        journal.append(
            "archive.repair",
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
    archives.put(
        archive,
        checkpoint,
        journal,
    )
    return checkpoint, archive


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


def test_default_policy():
    policy = ArchiveIndexRepairPolicy()
    assert policy.auto_repair_missing
    assert policy.max_repairs_per_archive == 100_000
    assert policy.max_archives_per_batch == 128


def test_policy_digest_is_stable():
    first = ArchiveIndexRepairPolicy(
        auto_repair_missing=False,
        max_repairs_per_archive=7,
        max_archives_per_batch=3,
    )
    second = ArchiveIndexRepairPolicy(
        auto_repair_missing=False,
        max_repairs_per_archive=7,
        max_archives_per_batch=3,
    )
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_policy_bool_validation():
    with pytest.raises(ValueError, match="bool"):
        ArchiveIndexRepairPolicy(
            auto_repair_missing=1,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_repairs_per_archive", 0),
        ("max_repairs_per_archive", -1),
        ("max_repairs_per_archive", True),
        ("max_repairs_per_archive", 1_000_001),
        ("max_archives_per_batch", 0),
        ("max_archives_per_batch", -1),
        ("max_archives_per_batch", True),
        ("max_archives_per_batch", 4097),
    ],
)
def test_policy_bounds(field, value):
    values = dict(
        max_repairs_per_archive=100,
        max_archives_per_batch=10,
    )
    values[field] = value
    with pytest.raises(ValueError, match=field):
        ArchiveIndexRepairPolicy(**values)


def test_healthy_archive_plan_is_none():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 2)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.NONE
    assert plan.repair_units == 0
    assert not plan.executable
    assert not plan.blocked
    assert plan.reasons == ()


def test_missing_root_plans_repair():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._root_key(
        "journal",
        events[0].event_hash,
    )
    delete_key(
        backend,
        archives.namespace,
        key,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.REPAIR_MISSING
    assert plan.executable
    assert plan.missing_root_indexes == (
        events[0].event_hash,
    )
    assert plan.repair_units == 1


def test_missing_head_plans_repair():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
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
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.REPAIR_MISSING
    assert plan.head_repair_required
    assert plan.repair_units == 1


def test_apply_repairs_missing_root():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._root_key(
        "journal",
        events[0].event_hash,
    )
    delete_key(
        backend,
        archives.namespace,
        key,
    )
    result = coordinator.repair(
        archive.manifest.archive_id
    )
    assert result.state is ArchiveIndexRepairState.REPAIRED
    assert result.ok
    assert result.mutated
    assert result.repaired_units == 1
    assert result.repaired_root_or_replica_indexes >= 1
    assert not result.head_repaired
    assert result.post_health.healthy
    assert backend.get(
        archives.namespace,
        key,
    ) is not None


def test_apply_repairs_missing_head():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 2)
    _, archive = archive_current(
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
    result = coordinator.repair(
        archive.manifest.archive_id
    )
    assert result.ok
    assert result.repaired_units == 1
    assert result.head_repaired


def test_apply_repairs_multiple_metadata_gaps():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            GENESIS,
        ),
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            events[0].event_hash,
        ),
    )
    delete_key(
        backend,
        archives.namespace,
        archives._head_key(
            "journal"
        ),
    )
    result = coordinator.repair(
        archive.manifest.archive_id
    )
    assert result.ok
    assert result.repaired_units == 3
    assert result.head_repaired


def test_healthy_apply_is_noop():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    result = coordinator.apply(
        plan
    )
    assert result.state is ArchiveIndexRepairState.HEALTHY
    assert result.ok
    assert not result.mutated


def test_competing_worker_completed_repair_is_idempotent_success():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            events[0].event_hash,
        ),
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    archives.repair_indexes(
        archive.manifest.archive_id
    )
    result = coordinator.apply(
        plan
    )
    assert result.state is ArchiveIndexRepairState.ALREADY_REPAIRED
    assert result.ok
    assert result.repaired_units == 0


def test_changed_but_still_degraded_health_marks_plan_stale():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    first_key = archives._root_key(
        "journal",
        events[0].event_hash,
    )
    second_key = archives._root_key(
        "journal",
        events[1].event_hash,
    )
    delete_key(
        backend,
        archives.namespace,
        first_key,
    )
    delete_key(
        backend,
        archives.namespace,
        second_key,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    stored = archives.get(
        archive.manifest.archive_id
    )
    root = DurableArchiveHead
    # Restore only one root through the repository's canonical root writer.
    archive_index = archives._root_index(
        {
            "chain_id": "journal",
            "root_hash": events[0].event_hash,
            "sequence": 1,
            "archive_id": archive.manifest.archive_id,
            "archive_manifest_digest": archive.manifest.digest,
            "replicas": [
                {
                    "archive_id": archive.manifest.archive_id,
                    "archive_manifest_digest": archive.manifest.digest,
                }
            ],
        }
    )
    archives._put_root_index(
        archive_index
    )
    assert stored is not None
    assert root is not None
    result = coordinator.apply(
        plan
    )
    assert result.state is ArchiveIndexRepairState.STALE
    assert not result.ok
    assert result.post_health.missing == 1


def test_corrupt_root_index_is_blocked():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._root_key(
        "journal",
        events[0].event_hash,
    )
    record = backend.get(
        archives.namespace,
        key,
    )
    raw = dict(record.value)
    raw["sequence"] = 99
    backend.compare_and_swap(
        archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.BLOCK_CORRUPT
    assert plan.blocked
    result = coordinator.apply(
        plan
    )
    assert result.state is ArchiveIndexRepairState.BLOCKED
    assert not result.ok
    assert result.post_health.state is DurableArchiveIndexState.INVALID


def test_conflicting_head_is_blocked():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive = archive_current(
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
        value=DurableArchiveHead(
            "journal",
            1,
            events[0].event_hash,
            "other",
            "f" * 64,
        ).to_dict(),
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.BLOCK_CORRUPT
    result = coordinator.apply(
        plan
    )
    assert result.state is ArchiveIndexRepairState.BLOCKED


def test_policy_limit_blocks_large_repair():
    policy = ArchiveIndexRepairPolicy(
        max_repairs_per_archive=1,
    )
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture(
        policy=policy
    )
    events = append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            GENESIS,
        ),
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            events[0].event_hash,
        ),
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.BLOCK_LIMIT


def test_disabled_auto_repair_is_nonmutating():
    policy = ArchiveIndexRepairPolicy(
        auto_repair_missing=False,
    )
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture(
        policy=policy
    )
    events = append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    key = archives._root_key(
        "journal",
        events[0].event_hash,
    )
    delete_key(
        backend,
        archives.namespace,
        key,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.action is ArchiveIndexRepairAction.NONE
    result = coordinator.apply(
        plan
    )
    assert result.state is ArchiveIndexRepairState.BLOCKED
    assert backend.get(
        archives.namespace,
        key,
    ) is None


def test_policy_mismatch_is_rejected():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            events[0].event_hash,
        ),
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    other = DurableArchiveIndexRepairCoordinator(
        archives,
        ArchiveIndexRepairPolicy(
            max_repairs_per_archive=7,
        ),
    )
    with pytest.raises(
        ArchiveIndexRepairError,
        match="policy differs",
    ):
        other.apply(plan)


def test_missing_archive_inspection_raises_repair_error():
    _, _, _, _, _, coordinator = fixture()
    with pytest.raises(
        ArchiveIndexRepairError,
        match="missing",
    ):
        coordinator.inspect(
            "missing"
        )


def test_apply_type_validation():
    _, _, _, _, _, coordinator = fixture()
    with pytest.raises(TypeError, match="plan"):
        coordinator.apply(object())


def test_batch_repairs_multiple_archives_sorted():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, first = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    append_events(
        journal,
        1,
        start=1,
    )
    _, second = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    # Remove the later archive replica from the shared genesis index.
    key = archives._root_key(
        "journal",
        GENESIS,
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
            replicas=(
                index.replicas[0],
            ),
        ).to_dict(),
    )
    report = coordinator.repair_batch(
        (
            second.manifest.archive_id,
            first.manifest.archive_id,
        )
    )
    assert tuple(
        item.archive_id
        for item in report.results
    ) == tuple(
        sorted(
            (
                first.manifest.archive_id,
                second.manifest.archive_id,
            )
        )
    )
    assert report.ok
    assert report.repaired_units >= 1


def test_batch_rejects_empty():
    _, _, _, _, _, coordinator = fixture()
    with pytest.raises(ValueError, match="at least one"):
        coordinator.repair_batch(())


def test_batch_rejects_duplicates():
    _, _, _, _, _, coordinator = fixture()
    with pytest.raises(ValueError, match="duplicate"):
        coordinator.repair_batch(
            ("a", "a")
        )


@pytest.mark.parametrize(
    "archive_id",
    ["", "x" * 161, 7],
)
def test_batch_validates_archive_ids(archive_id):
    _, _, _, _, _, coordinator = fixture()
    with pytest.raises(ValueError, match="archive_id"):
        coordinator.repair_batch(
            (archive_id,)
        )


def test_batch_bound_enforced():
    _, _, _, _, archives, _ = fixture()
    coordinator = DurableArchiveIndexRepairCoordinator(
        archives,
        ArchiveIndexRepairPolicy(
            max_archives_per_batch=1,
        ),
    )
    with pytest.raises(
        ArchiveIndexRepairError,
        match="batch exceeds",
    ):
        coordinator.repair_batch(
            ("a", "b")
        )


def test_plan_digest_stable_for_same_health_clock():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    first = coordinator.inspect(
        archive.manifest.archive_id
    )
    second = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert first.digest == second.digest


def test_plan_digest_changes_after_health_change():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    first = coordinator.inspect(
        archive.manifest.archive_id
    )
    delete_key(
        backend,
        archives.namespace,
        archives._root_key(
            "journal",
            events[0].event_hash,
        ),
    )
    second = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert first.digest != second.digest


def test_plan_serialization():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    data = plan.to_dict()
    assert data["archive_id"] == archive.manifest.archive_id
    assert data["chain_id"] == "journal"
    assert data["action"] == "none"
    assert data["repair_units"] == 0
    assert data["executable"] is False
    assert data["blocked"] is False
    assert data["digest"] == plan.digest


def test_result_serialization():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    result = coordinator.repair(
        archive.manifest.archive_id
    )
    data = result.to_dict()
    assert data["state"] == "healthy"
    assert data["ok"] is True
    assert data["mutated"] is False
    assert data["post_health"]["healthy"] is True


def test_batch_serialization():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    report = coordinator.repair_batch(
        (archive.manifest.archive_id,)
    )
    data = report.to_dict()
    assert data["ok"] is True
    assert data["repaired_units"] == 0
    assert data["blocked"] == 0
    assert data["digest"] == report.digest


def test_coordinator_constructor_validation():
    with pytest.raises(TypeError, match="archives"):
        DurableArchiveIndexRepairCoordinator(
            object()
        )
    _, _, _, _, archives, _ = fixture()
    with pytest.raises(TypeError, match="policy"):
        DurableArchiveIndexRepairCoordinator(
            archives,
            object(),
        )
    with pytest.raises(TypeError, match="clock"):
        DurableArchiveIndexRepairCoordinator(
            archives,
            clock=object(),
        )


@pytest.mark.parametrize(
    "clock_value",
    [-1.0, float("nan"), float("inf"), True, "now"],
)
def test_clock_validation(clock_value):
    _, _, _, _, archives, _ = fixture()
    coordinator = DurableArchiveIndexRepairCoordinator(
        archives,
        clock=lambda: clock_value,
    )
    with pytest.raises(
        ArchiveIndexRepairError,
        match="clock",
    ):
        coordinator.inspect(
            "missing"
        )


def test_plan_rejects_repair_with_corruption():
    with pytest.raises(
        ValueError,
        match="corruption",
    ):
        ArchiveIndexRepairPlan(
            1,
            "archive",
            "chain",
            ArchiveIndexRepairAction.REPAIR_MISSING,
            "a" * 64,
            "b" * 64,
            ("c" * 64,),
            (),
            ("d" * 64,),
            False,
            5,
            1.0,
            (),
        )


def test_plan_rejects_repair_above_bound():
    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        ArchiveIndexRepairPlan(
            1,
            "archive",
            "chain",
            ArchiveIndexRepairAction.REPAIR_MISSING,
            "a" * 64,
            "b" * 64,
            ("c" * 64, "d" * 64),
            (),
            (),
            False,
            1,
            1.0,
            (),
        )


def test_batch_report_sorted_unique_validation():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    one = coordinator.repair(
        archive.manifest.archive_id
    )
    other = replace(
        one,
        archive_id="other",
        post_health=replace(
            one.post_health,
            archive_id="other",
        ),
    )
    reverse_sorted = tuple(
        sorted(
            (one, other),
            key=lambda item: item.archive_id,
            reverse=True,
        )
    )
    with pytest.raises(ValueError, match="sorted"):
        ArchiveIndexRepairBatchReport(
            reverse_sorted,
            coordinator.policy.digest,
        )
    with pytest.raises(ValueError, match="duplicate"):
        ArchiveIndexRepairBatchReport(
            (one, one),
            coordinator.policy.digest,
        )


def test_health_digest_bound_to_plan():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    health = archives.inspect_indexes(
        archive.manifest.archive_id
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    assert plan.health_digest == health.digest


def test_policy_digest_bound_to_plan_and_batch():
    (
        _,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    plan = coordinator.inspect(
        archive.manifest.archive_id
    )
    batch = coordinator.repair_batch(
        (archive.manifest.archive_id,)
    )
    assert plan.policy_digest == coordinator.policy.digest
    assert batch.policy_digest == coordinator.policy.digest


def test_repair_preserves_archive_record_and_nodes():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    events = append_events(journal, 2)
    _, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    stored_before = archives.get(
        archive.manifest.archive_id
    )
    node_before = archives.get_node(
        "journal",
        events[0].event_hash,
    )
    key = archives._root_key(
        "journal",
        events[0].event_hash,
    )
    delete_key(
        backend,
        archives.namespace,
        key,
    )
    coordinator.repair(
        archive.manifest.archive_id
    )
    assert archives.get(
        archive.manifest.archive_id
    ) == stored_before
    assert archives.get_node(
        "journal",
        events[0].event_hash,
    ) == node_before
    assert archives.verify_archive(
        stored_before
    )


def test_repair_does_not_change_signed_manifest_or_checkpoint():
    (
        backend,
        journal,
        checkpoints,
        builder,
        archives,
        coordinator,
    ) = fixture()
    append_events(journal, 1)
    checkpoint, archive = archive_current(
        journal,
        checkpoints,
        builder,
        archives,
    )
    stored_before = archives.get(
        archive.manifest.archive_id
    )
    delete_key(
        backend,
        archives.namespace,
        archives._head_key(
            "journal"
        ),
    )
    coordinator.repair(
        archive.manifest.archive_id
    )
    stored_after = archives.get(
        archive.manifest.archive_id
    )
    assert stored_after.manifest == stored_before.manifest
    assert stored_after.checkpoint == checkpoint

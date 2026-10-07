"""Bounded durable checkpoint-index repair workflow tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
    DurableCheckpointIndexState,
)
from skeleton.shells.ai.durable_checkpoint_repair import (
    CheckpointIndexRepairAction,
    CheckpointIndexRepairBatchReport,
    CheckpointIndexRepairError,
    CheckpointIndexRepairPlan,
    CheckpointIndexRepairPolicy,
    CheckpointIndexRepairResult,
    CheckpointIndexRepairState,
    DurableCheckpointIndexRepairCoordinator,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
)
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
)


def signer():
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def fixture(*, policy=None):
    backend = InMemoryFencedStore()
    source = ContentAddressedEvidenceChain(
        backend,
        namespace="source",
        max_events=100,
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        max_checkpoints=100,
        clock=lambda: 50.0,
    )
    coordinator = DurableCheckpointIndexRepairCoordinator(
        checkpoints,
        policy,
        clock=lambda: 200.0,
    )
    return (
        backend,
        source,
        checkpoints,
        coordinator,
    )


def append_checkpoint(
    source,
    checkpoints,
    *,
    index,
    chain_id="source",
):
    source.append(
        "source.event",
        {"index": index},
    )
    return checkpoints.publish(
        chain_id,
        source,
    )


def delete_digest_index(
    backend,
    checkpoints,
    item,
):
    key = checkpoints._digest_lookup_key(
        item.checkpoint.digest
    )
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.delete(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
    )
    return key


def delete_root_index(
    backend,
    checkpoints,
    item,
):
    key = checkpoints._root_lookup_key(
        item.checkpoint.chain_id,
        item.checkpoint.root_hash,
    )
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.delete(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
    )
    return key


def test_default_policy():
    policy = CheckpointIndexRepairPolicy()
    assert policy.auto_repair_missing
    assert policy.max_repairs_per_chain == 4096
    assert policy.max_chains_per_batch == 128
    assert policy.require_registry_valid


def test_policy_digest_is_stable():
    first = CheckpointIndexRepairPolicy(
        auto_repair_missing=False,
        max_repairs_per_chain=7,
        max_chains_per_batch=3,
        require_registry_valid=False,
    )
    second = CheckpointIndexRepairPolicy(
        auto_repair_missing=False,
        max_repairs_per_chain=7,
        max_chains_per_batch=3,
        require_registry_valid=False,
    )
    assert first.digest == second.digest
    assert len(first.digest) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("auto_repair_missing", 1),
        ("require_registry_valid", "yes"),
    ],
)
def test_policy_boolean_validation(field, value):
    values = dict(
        auto_repair_missing=True,
        max_repairs_per_chain=10,
        max_chains_per_batch=5,
        require_registry_valid=True,
    )
    values[field] = value
    with pytest.raises(ValueError, match="bool"):
        CheckpointIndexRepairPolicy(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_repairs_per_chain", 0),
        ("max_repairs_per_chain", -1),
        ("max_repairs_per_chain", True),
        ("max_repairs_per_chain", 100_001),
        ("max_chains_per_batch", 0),
        ("max_chains_per_batch", -1),
        ("max_chains_per_batch", True),
        ("max_chains_per_batch", 4097),
    ],
)
def test_policy_bounds(field, value):
    values = dict(
        max_repairs_per_chain=10,
        max_chains_per_batch=5,
    )
    values[field] = value
    with pytest.raises(ValueError, match=field):
        CheckpointIndexRepairPolicy(**values)


def test_inspect_healthy_chain_returns_none_action():
    _, source, checkpoints, coordinator = fixture()
    append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.NONE
    assert plan.missing_count == 0
    assert not plan.executable
    assert not plan.blocked
    assert plan.reasons == ()


def test_inspect_missing_digest_index_plans_repair():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.REPAIR_MISSING
    assert plan.executable
    assert plan.missing_digest_indexes == (
        item.checkpoint.digest,
    )
    assert plan.missing_root_indexes == ()
    assert plan.missing_count == 1


def test_inspect_missing_root_index_plans_repair():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_root_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.REPAIR_MISSING
    assert plan.missing_root_indexes == (
        item.checkpoint.root_hash,
    )


def test_inspect_both_missing_indexes_plans_two_repairs():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    delete_root_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.missing_count == 2
    assert plan.action is CheckpointIndexRepairAction.REPAIR_MISSING


def test_apply_repairs_missing_digest_index():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    key = delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.REPAIRED
    assert result.ok
    assert result.mutated
    assert result.repaired == 1
    assert result.requested_repairs == 1
    assert backend.get(
        checkpoints._namespace,
        key,
    ) is not None
    assert result.post_health.healthy


def test_apply_repairs_missing_root_index():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    key = delete_root_index(
        backend,
        checkpoints,
        item,
    )
    result = coordinator.repair(
        "source"
    )
    assert result.state is CheckpointIndexRepairState.REPAIRED
    assert result.repaired == 1
    assert backend.get(
        checkpoints._namespace,
        key,
    ) is not None


def test_apply_repairs_multiple_missing_indexes():
    backend, source, checkpoints, coordinator = fixture()
    first = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    second = append_checkpoint(
        source,
        checkpoints,
        index=2,
    )
    for item in (first, second):
        delete_digest_index(
            backend,
            checkpoints,
            item,
        )
        delete_root_index(
            backend,
            checkpoints,
            item,
        )
    result = coordinator.repair(
        "source"
    )
    assert result.ok
    assert result.repaired == 4
    assert result.requested_repairs == 4


def test_apply_healthy_plan_is_idempotent():
    _, source, checkpoints, coordinator = fixture()
    append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    plan = coordinator.inspect(
        "source"
    )
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.HEALTHY
    assert result.ok
    assert not result.mutated
    assert result.repaired == 0


def test_stale_repair_plan_becomes_already_repaired_if_other_worker_finishes():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    checkpoints.repair_missing_lookup_indexes(
        "source"
    )
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.ALREADY_REPAIRED
    assert result.ok
    assert result.repaired == 0


def test_stale_repair_plan_fails_closed_when_health_changes_but_not_healthy():
    backend, source, checkpoints, coordinator = fixture()
    first = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    second = append_checkpoint(
        source,
        checkpoints,
        index=2,
    )
    delete_digest_index(
        backend,
        checkpoints,
        first,
    )
    delete_digest_index(
        backend,
        checkpoints,
        second,
    )
    plan = coordinator.inspect(
        "source"
    )
    # Repair only one missing index manually, leaving health degraded but
    # changing the observed health digest.
    checkpoints._put_lookup(
        checkpoints._digest_lookup_key(
            first.checkpoint.digest
        ),
        checkpoints._lookup_for(
            first
        ),
    )
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.STALE
    assert not result.ok
    assert result.repaired == 0
    assert result.post_health.missing == 1


def test_corrupt_index_is_blocked_not_repaired():
    backend, source, checkpoints, coordinator = fixture()
    first = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    second = append_checkpoint(
        source,
        checkpoints,
        index=2,
    )
    key = checkpoints._digest_lookup_key(
        first.checkpoint.digest
    )
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.compare_and_swap(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
        value=checkpoints._lookup_for(
            second
        ).to_dict(),
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.BLOCK_CORRUPT
    assert plan.blocked
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.BLOCKED
    assert not result.ok
    assert result.repaired == 0
    assert (
        result.post_health.state
        is DurableCheckpointIndexState.INVALID
    )


def test_malformed_index_is_blocked():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    key = checkpoints._root_lookup_key(
        "source",
        item.checkpoint.root_hash,
    )
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.compare_and_swap(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
        value={"bad": True},
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.BLOCK_CORRUPT
    assert plan.corrupt_indexes


def test_registry_corruption_blocks_repair():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    key = f"node:{item.chain_node_hash}"
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.compare_and_swap(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            kind="corrupt.kind",
        ),
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.BLOCK_REGISTRY
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.BLOCKED
    assert not result.ok


def test_policy_limit_blocks_large_repair():
    policy = CheckpointIndexRepairPolicy(
        max_repairs_per_chain=1,
    )
    backend, source, checkpoints, coordinator = fixture(
        policy=policy
    )
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    delete_root_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.BLOCK_LIMIT
    assert plan.blocked


def test_disabled_auto_repair_creates_nonmutating_plan():
    policy = CheckpointIndexRepairPolicy(
        auto_repair_missing=False,
    )
    backend, source, checkpoints, coordinator = fixture(
        policy=policy
    )
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.action is CheckpointIndexRepairAction.NONE
    assert not plan.executable
    assert plan.missing_count == 1
    result = coordinator.apply(
        plan
    )
    assert result.state is CheckpointIndexRepairState.BLOCKED
    assert not result.ok
    assert result.repaired == 0


def test_plan_policy_mismatch_is_rejected():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    plan = coordinator.inspect(
        "source"
    )
    other = DurableCheckpointIndexRepairCoordinator(
        checkpoints,
        CheckpointIndexRepairPolicy(
            max_repairs_per_chain=7,
        ),
        clock=lambda: 200.0,
    )
    with pytest.raises(
        CheckpointIndexRepairError,
        match="policy differs",
    ):
        other.apply(plan)


def test_apply_type_validation():
    _, _, _, coordinator = fixture()
    with pytest.raises(TypeError, match="plan"):
        coordinator.apply(object())


def test_repair_batch_sorts_results():
    backend = InMemoryFencedStore()
    source_a = ContentAddressedEvidenceChain(
        backend,
        namespace="a",
    )
    source_b = ContentAddressedEvidenceChain(
        backend,
        namespace="b",
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 50.0,
    )
    coordinator = DurableCheckpointIndexRepairCoordinator(
        checkpoints,
        clock=lambda: 200.0,
    )
    a = append_checkpoint(
        source_a,
        checkpoints,
        index=1,
        chain_id="a",
    )
    b = append_checkpoint(
        source_b,
        checkpoints,
        index=1,
        chain_id="b",
    )
    delete_digest_index(
        backend,
        checkpoints,
        a,
    )
    delete_root_index(
        backend,
        checkpoints,
        b,
    )
    report = coordinator.repair_batch(
        ("b", "a")
    )
    assert tuple(
        item.chain_id
        for item in report.results
    ) == ("a", "b")
    assert report.ok
    assert report.repaired == 2


def test_repair_batch_reports_blocked_chain():
    backend = InMemoryFencedStore()
    source_a = ContentAddressedEvidenceChain(
        backend,
        namespace="a",
    )
    source_b = ContentAddressedEvidenceChain(
        backend,
        namespace="b",
    )
    checkpoints = DurableChainCheckpointStore(
        backend,
        signer(),
        namespace="checkpoints",
        clock=lambda: 50.0,
    )
    coordinator = DurableCheckpointIndexRepairCoordinator(
        checkpoints,
        clock=lambda: 200.0,
    )
    a = append_checkpoint(
        source_a,
        checkpoints,
        index=1,
        chain_id="a",
    )
    b = append_checkpoint(
        source_b,
        checkpoints,
        index=1,
        chain_id="b",
    )
    delete_digest_index(
        backend,
        checkpoints,
        a,
    )
    key = checkpoints._digest_lookup_key(
        b.checkpoint.digest
    )
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.compare_and_swap(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
        value=checkpoints._lookup_for(a).to_dict(),
    )
    report = coordinator.repair_batch(
        ("a", "b")
    )
    assert not report.ok
    assert report.blocked == 1
    assert report.repaired == 1


def test_repair_batch_rejects_empty():
    _, _, _, coordinator = fixture()
    with pytest.raises(ValueError, match="at least one"):
        coordinator.repair_batch(())


def test_repair_batch_rejects_duplicates():
    _, _, _, coordinator = fixture()
    with pytest.raises(ValueError, match="duplicate"):
        coordinator.repair_batch(
            ("source", "source")
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 129, 7],
)
def test_repair_batch_validates_chain_ids(chain_id):
    _, _, _, coordinator = fixture()
    with pytest.raises(ValueError, match="chain_id"):
        coordinator.repair_batch(
            (chain_id,)
        )


def test_repair_batch_enforces_policy_bound():
    _, _, checkpoints, _ = fixture()
    coordinator = DurableCheckpointIndexRepairCoordinator(
        checkpoints,
        CheckpointIndexRepairPolicy(
            max_chains_per_batch=1,
        ),
    )
    with pytest.raises(
        CheckpointIndexRepairError,
        match="batch exceeds",
    ):
        coordinator.repair_batch(
            ("a", "b")
        )


def test_plan_digest_is_stable_for_same_health_and_clock():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    first = coordinator.inspect(
        "source"
    )
    second = coordinator.inspect(
        "source"
    )
    assert first.digest == second.digest


def test_plan_digest_changes_with_health():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    first = coordinator.inspect(
        "source"
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    second = coordinator.inspect(
        "source"
    )
    assert first.digest != second.digest


def test_result_digest_is_stable():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    result = coordinator.repair(
        "source"
    )
    assert result.digest == result.digest
    assert len(result.digest) == 64


def test_plan_serialization_contract():
    _, source, checkpoints, coordinator = fixture()
    append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    plan = coordinator.inspect(
        "source"
    )
    data = plan.to_dict()
    assert data["schema_version"] == 1
    assert data["chain_id"] == "source"
    assert data["action"] == "none"
    assert data["missing_count"] == 0
    assert data["executable"] is False
    assert data["blocked"] is False
    assert data["digest"] == plan.digest


def test_result_serialization_contract():
    _, source, checkpoints, coordinator = fixture()
    append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    result = coordinator.repair(
        "source"
    )
    data = result.to_dict()
    assert data["state"] == "healthy"
    assert data["ok"] is True
    assert data["mutated"] is False
    assert data["post_health"]["healthy"] is True
    assert data["digest"] == result.digest


def test_batch_serialization_contract():
    _, source, checkpoints, coordinator = fixture()
    append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    batch = coordinator.repair_batch(
        ("source",)
    )
    data = batch.to_dict()
    assert data["ok"] is True
    assert data["repaired"] == 0
    assert data["blocked"] == 0
    assert len(data["results"]) == 1
    assert data["digest"] == batch.digest


def test_coordinator_constructor_validation():
    with pytest.raises(TypeError, match="checkpoints"):
        DurableCheckpointIndexRepairCoordinator(
            object()
        )
    _, _, checkpoints, _ = fixture()
    with pytest.raises(TypeError, match="policy"):
        DurableCheckpointIndexRepairCoordinator(
            checkpoints,
            object(),
        )
    with pytest.raises(TypeError, match="clock"):
        DurableCheckpointIndexRepairCoordinator(
            checkpoints,
            clock=object(),
        )


@pytest.mark.parametrize(
    "clock_value",
    [-1.0, float("nan"), float("inf"), True, "now"],
)
def test_coordinator_clock_validation(clock_value):
    _, _, checkpoints, _ = fixture()
    coordinator = DurableCheckpointIndexRepairCoordinator(
        checkpoints,
        clock=lambda: clock_value,
    )
    with pytest.raises(
        CheckpointIndexRepairError,
        match="clock",
    ):
        coordinator.inspect(
            "source"
        )


def test_plan_validation():
    with pytest.raises(ValueError):
        CheckpointIndexRepairPlan(
            2,
            "source",
            CheckpointIndexRepairAction.NONE,
            "a" * 64,
            "b" * 64,
            0,
            (),
            (),
            (),
            1,
            1.0,
            (),
        )
    with pytest.raises(ValueError):
        CheckpointIndexRepairPlan(
            1,
            "",
            CheckpointIndexRepairAction.NONE,
            "a" * 64,
            "b" * 64,
            0,
            (),
            (),
            (),
            1,
            1.0,
            (),
        )


def test_plan_rejects_repair_action_with_corruption():
    with pytest.raises(
        ValueError,
        match="corrupt",
    ):
        CheckpointIndexRepairPlan(
            1,
            "source",
            CheckpointIndexRepairAction.REPAIR_MISSING,
            "a" * 64,
            "b" * 64,
            1,
            ("c" * 64,),
            (),
            ("digest:x:mismatch",),
            5,
            1.0,
            (),
        )


def test_plan_rejects_repair_above_bound():
    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        CheckpointIndexRepairPlan(
            1,
            "source",
            CheckpointIndexRepairAction.REPAIR_MISSING,
            "a" * 64,
            "b" * 64,
            1,
            ("c" * 64, "d" * 64),
            (),
            (),
            1,
            1.0,
            (),
        )


def test_result_validation_repaired_cannot_exceed_requested():
    health = DurableCheckpointIndexRepairCoordinator(
        fixture()[2]
    ).checkpoints.inspect_lookup_indexes(
        "source"
    )
    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        CheckpointIndexRepairResult(
            "source",
            CheckpointIndexRepairState.REPAIRED,
            CheckpointIndexRepairAction.REPAIR_MISSING,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            2,
            1,
            health,
            (),
        )


def test_batch_report_requires_sorted_unique_results():
    _, source, checkpoints, coordinator = fixture()
    append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    one = coordinator.repair(
        "source"
    )
    other = replace(
        one,
        chain_id="other",
        post_health=replace(
            one.post_health,
            chain_id="other",
        ),
    )
    with pytest.raises(
        ValueError,
        match="sorted",
    ):
        CheckpointIndexRepairBatchReport(
            (one, other),
            coordinator.policy.digest,
        )
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        CheckpointIndexRepairBatchReport(
            (one, one),
            coordinator.policy.digest,
        )


def test_repair_missing_store_method_bound_validation():
    _, _, checkpoints, _ = fixture()
    for value in (
        0,
        -1,
        True,
        1.5,
    ):
        with pytest.raises(
            ValueError,
            match="max_repairs",
        ):
            checkpoints.repair_missing_lookup_indexes(
                "source",
                max_repairs=value,
            )


def test_repair_missing_store_method_chain_validation():
    _, _, checkpoints, _ = fixture()
    with pytest.raises(ValueError, match="chain_id"):
        checkpoints.repair_missing_lookup_indexes(
            ""
        )


def test_repair_missing_store_method_refuses_corruption():
    backend, source, checkpoints, _ = fixture()
    first = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    second = append_checkpoint(
        source,
        checkpoints,
        index=2,
    )
    key = checkpoints._digest_lookup_key(
        first.checkpoint.digest
    )
    record = backend.get(
        checkpoints._namespace,
        key,
    )
    backend.compare_and_swap(
        checkpoints._namespace,
        key,
        expected_revision=record.revision,
        value=checkpoints._lookup_for(
            second
        ).to_dict(),
    )
    with pytest.raises(
        Exception,
        match="conflicting",
    ):
        checkpoints.repair_missing_lookup_indexes(
            "source"
        )


def test_repair_missing_store_method_enforces_bound():
    backend, source, checkpoints, _ = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    delete_root_index(
        backend,
        checkpoints,
        item,
    )
    with pytest.raises(
        Exception,
        match="bounded",
    ):
        checkpoints.repair_missing_lookup_indexes(
            "source",
            max_repairs=1,
        )


def test_repair_only_mutates_missing_index_keys():
    backend, source, checkpoints, coordinator = fixture()
    first = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    second = append_checkpoint(
        source,
        checkpoints,
        index=2,
    )
    first_root_key = checkpoints._root_lookup_key(
        "source",
        first.checkpoint.root_hash,
    )
    second_root_key = checkpoints._root_lookup_key(
        "source",
        second.checkpoint.root_hash,
    )
    before_first_root = backend.get(
        checkpoints._namespace,
        first_root_key,
    )
    before_second_root = backend.get(
        checkpoints._namespace,
        second_root_key,
    )
    delete_digest_index(
        backend,
        checkpoints,
        first,
    )
    coordinator.repair(
        "source"
    )
    after_first_root = backend.get(
        checkpoints._namespace,
        first_root_key,
    )
    after_second_root = backend.get(
        checkpoints._namespace,
        second_root_key,
    )
    assert after_first_root == before_first_root
    assert after_second_root == before_second_root


def test_repair_does_not_change_checkpoint_registry_head():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    registry_head_before = checkpoints._chain.head()
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    coordinator.repair(
        "source"
    )
    assert checkpoints._chain.head() == registry_head_before
    assert checkpoints.verify()


def test_repair_result_post_health_digest_matches_live_health():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_digest_index(
        backend,
        checkpoints,
        item,
    )
    result = coordinator.repair(
        "source"
    )
    current = checkpoints.inspect_lookup_indexes(
        "source"
    )
    assert result.after_health_digest == current.digest
    assert result.post_health == current


def test_health_digest_is_bound_into_plan():
    backend, source, checkpoints, coordinator = fixture()
    item = append_checkpoint(
        source,
        checkpoints,
        index=1,
    )
    delete_root_index(
        backend,
        checkpoints,
        item,
    )
    health = checkpoints.inspect_lookup_indexes(
        "source"
    )
    plan = coordinator.inspect(
        "source"
    )
    assert plan.health_digest == health.digest


def test_policy_digest_is_bound_into_plan():
    _, _, _, coordinator = fixture()
    plan = coordinator.inspect(
        "source"
    )
    assert plan.policy_digest == coordinator.policy.digest


def test_batch_policy_digest_is_bound():
    _, _, _, coordinator = fixture()
    batch = coordinator.repair_batch(
        ("source",)
    )
    assert batch.policy_digest == coordinator.policy.digest


def test_repair_empty_checkpoint_chain_is_healthy_noop():
    _, _, checkpoints, coordinator = fixture()
    plan = coordinator.inspect(
        "source"
    )
    assert plan.checkpoint_count == 0
    assert plan.action is CheckpointIndexRepairAction.NONE
    result = coordinator.apply(plan)
    assert result.ok
    assert result.state is CheckpointIndexRepairState.HEALTHY
    assert checkpoints.inspect_lookup_indexes(
        "source"
    ).healthy

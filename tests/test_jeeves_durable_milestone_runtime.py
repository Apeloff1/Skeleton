"""Jeeves runtime durable queue binding, replay and fail-closed persistence."""

from threading import RLock

import pytest

from skeleton.jeeves.agent.adaptive_runtime import AdaptiveJeevesRuntime
from skeleton.jeeves.agent.delivery_milestone_store import (
    MilestoneCheckpointError, SQLiteMilestoneQueueStore,
)
from skeleton.jeeves.agent.delivery_milestone_workbench import HostMeasurement

COMMIT = "a" * 40
ARTIFACT = "b" * 64
RUN = "run:durable"


def runtime():
    # Isolate the public milestone API from unrelated model/provider setup.
    instance = AdaptiveJeevesRuntime.__new__(AdaptiveJeevesRuntime)
    instance._adaptive_lock = RLock()
    instance._milestone_queue_stores = {}
    instance._milestone_queues = {}
    instance._milestone_boards = {}
    return instance


def checker(name):
    def host(spec, commit, digest):
        return HostMeasurement(
            spec.milestone_id, name, commit, digest, spec.metric, spec.unit,
            spec.target, spec.min_samples, "host-fixture",
            f"host:{name}:{spec.milestone_id}", "exact code bytes",
        )
    return host


def test_runtime_persists_each_queue_state_and_replays_into_fresh_instance(tmp_path):
    path = tmp_path / "runtime-milestones.sqlite"
    original = runtime()
    with SQLiteMilestoneQueueStore(path) as store:
        assert original.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        ) is None
        original.begin_assurance_work_queue(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        lease = original.claim_assurance_work(RUN, owner="host-primary", now=10)
        checkpoint = store.load(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        assert checkpoint.generation == 2
        assert checkpoint.queue.get(lease.milestone_id).status == "leased"

    resumed = runtime()
    with SQLiteMilestoneQueueStore(path) as store:
        returned = resumed.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        assert returned.fingerprint == checkpoint.queue.fingerprint
        assert resumed.assurance_milestone_board(RUN).completion_count == 0
        verdict = resumed.settle_assurance_work(
            RUN, lease=lease, now=11,
            primary=checker("host-primary"),
            independent=checker("host-secondary"),
        )
        assert verdict.passed
        assert resumed.assurance_work_queue(RUN).board.completion_count == 1
        stored = store.load(RUN, source_commit=COMMIT, artifact_digest=ARTIFACT)
        assert stored.generation == 3
        assert stored.queue.fingerprint == resumed.assurance_work_queue(RUN).fingerprint


def test_failed_checkpoint_write_keeps_last_accepted_memory_state(tmp_path):
    instance = runtime()
    store = SQLiteMilestoneQueueStore(tmp_path / "closed.sqlite")
    instance.bind_assurance_checkpoint_store(
        RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
    )
    instance.begin_assurance_work_queue(
        RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
    )
    previous = instance.assurance_work_queue(RUN).fingerprint
    store.close()
    with pytest.raises(MilestoneCheckpointError, match="closed"):
        instance.claim_assurance_work(RUN, owner="worker", now=20)
    assert instance.assurance_work_queue(RUN).fingerprint == previous
    assert instance.assurance_milestone_board(RUN).completion_count == 0


def test_bound_queue_cannot_be_reinitialized_after_recovery(tmp_path):
    path = tmp_path / "restored.sqlite"
    first = runtime()
    with SQLiteMilestoneQueueStore(path) as store:
        first.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        first.begin_assurance_work_queue(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
    restored = runtime()
    with SQLiteMilestoneQueueStore(path) as store:
        restored.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        with pytest.raises(ValueError, match="already exists"):
            restored.begin_assurance_work_queue(
                RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            )


def test_runtime_expiration_recovery_persists_and_revokes_old_lease(tmp_path):
    path = tmp_path / "expire.sqlite"
    instance = runtime()
    with SQLiteMilestoneQueueStore(path) as store:
        instance.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        instance.begin_assurance_work_queue(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            lease_seconds=5,
        )
        lease = instance.claim_assurance_work(RUN, owner="worker", now=2)
        new = instance.recover_assurance_work(RUN, now=10)
        assert new.get(lease.milestone_id).status == "pending"
        assert instance.assurance_milestone_board(RUN).completion_count == 0
        persisted = store.load(RUN, source_commit=COMMIT, artifact_digest=ARTIFACT)
        assert persisted.queue.fingerprint == new.fingerprint


def test_duplicate_binding_must_be_explicitly_rejected(tmp_path):
    instance = runtime()
    with SQLiteMilestoneQueueStore(tmp_path / "x.sqlite") as store:
        instance.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        with pytest.raises(ValueError, match="already bound"):
            instance.bind_assurance_checkpoint_store(
                RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
            )



def test_runtime_exposes_host_authorized_durable_pause_and_cancel(tmp_path):
    instance = runtime()
    with SQLiteMilestoneQueueStore(tmp_path / "operator-runtime.sqlite") as store:
        instance.bind_assurance_checkpoint_store(
            RUN, store, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        instance.begin_assurance_work_queue(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        )
        paused = instance.set_assurance_operator_control(
            RUN, mode="paused", actor_ref="host:operator",
            reason_ref="ticket:hold",
        )
        assert paused.generation == 1
        assert instance.assurance_operator_control(RUN).mode == "paused"
        with pytest.raises(MilestoneCheckpointError, match="paused"):
            instance.claim_assurance_work(RUN, owner="host-worker", now=10)
        assert instance.assurance_work_queue(RUN).board.completion_count == 0
        instance.set_assurance_operator_control(
            RUN, mode="running", actor_ref="host:operator",
            reason_ref="ticket:release", expected_generation=1,
        )
        lease = instance.claim_assurance_work(
            RUN, owner="host-worker", now=10,
        )
        assert lease.milestone_id == "M001"
        instance.set_assurance_operator_control(
            RUN, mode="cancelled", actor_ref="host:operator",
            reason_ref="ticket:cancel", expected_generation=2,
        )
        with pytest.raises(MilestoneCheckpointError, match="cancelled"):
            instance.settle_assurance_work(
                RUN, lease=lease, now=11,
                primary=checker("host-primary"),
                independent=checker("host-secondary"),
            )
        assert instance.assurance_work_queue(RUN).board.completion_count == 0
        assert instance.assurance_operator_control(RUN).mode == "cancelled"

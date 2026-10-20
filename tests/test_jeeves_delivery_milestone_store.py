"""Durable milestones: exact-source recovery, CAS, corruption and lease survival."""

from dataclasses import replace
import hashlib
import sqlite3

import pytest

from skeleton.jeeves.agent.delivery_milestone_queue import MilestoneQueue
from skeleton.jeeves.agent.delivery_milestone_store import (
    MilestoneCheckpointConflict, MilestoneCheckpointError,
    SQLiteMilestoneQueueStore,
)
from skeleton.jeeves.agent.delivery_milestone_workbench import HostMeasurement

COMMIT = "a" * 40
SOURCE = "b" * 64


def queue():
    return MilestoneQueue.start(COMMIT, SOURCE)


def check(name):
    def inspect(spec, commit, artifact):
        return HostMeasurement(
            milestone_id=spec.milestone_id,
            checker_id=name, source_commit=commit, artifact_digest=artifact,
            metric=spec.metric, unit=spec.unit, observed=spec.target,
            sample_count=spec.min_samples, method="fixture",
            evidence_ref=f"host:{name}:{spec.milestone_id}",
            scope="exact host artifact",
        )
    return inspect


def test_sqlite_checkpoint_survives_restart_and_does_not_forge_a_pass(tmp_path):
    path = tmp_path / "milestones.sqlite"
    with SQLiteMilestoneQueueStore(path) as store:
        original = store.save("run:001", queue())
        assert original.generation == 1
        first, lease = original.queue.claim("worker:1", 10)
        saved = store.save(
            "run:001", first, expected_fingerprint=original.fingerprint,
        )
        assert saved.generation == 2
        assert saved.queue.get("M001").status == "leased"
        assert saved.queue.board.completion_count == 0

    with SQLiteMilestoneQueueStore(path) as restarted:
        restored = restarted.load(
            "run:001", source_commit=COMMIT, artifact_digest=SOURCE,
        )
        assert restored.generation == 2
        assert restored.queue.fingerprint == saved.queue.fingerprint
        assert restored.queue.get("M001").lease_serial == lease.serial
        complete, result = restored.queue.settle(
            lease, 11, check("primary"), check("secondary"),
        )
        assert result.passed
        end = restarted.save(
            "run:001", complete, expected_fingerprint=restored.fingerprint,
        )
        assert end.generation == 3
        assert end.queue.board.completion_count == 1
        assert end.queue.get("M001").status == "passed"
    with SQLiteMilestoneQueueStore(path) as final:
        persisted = final.load(
            "run:001", source_commit=COMMIT, artifact_digest=SOURCE,
        )
        assert persisted.generation == 3
        assert persisted.queue.board.completion_count == 1


def test_idempotent_save_does_not_advance_generation(tmp_path):
    with SQLiteMilestoneQueueStore(tmp_path / "checkpoint.sqlite") as store:
        q = queue()
        first = store.save("run:stable", q)
        second = store.save("run:stable", q)
        assert first.generation == second.generation == 1
        assert first.payload_sha256 == second.payload_sha256


def test_stale_reader_cannot_overwrite_a_newer_commit(tmp_path):
    path = tmp_path / "milestones.sqlite"
    with SQLiteMilestoneQueueStore(path) as first:
        seed = first.save("run:cas", queue())
    with SQLiteMilestoneQueueStore(path) as a, SQLiteMilestoneQueueStore(path) as b:
        view_a = a.load("run:cas", source_commit=COMMIT, artifact_digest=SOURCE)
        view_b = b.load("run:cas", source_commit=COMMIT, artifact_digest=SOURCE)
        next_a, _ = view_a.queue.claim("worker:a", 10)
        advanced = a.save(
            "run:cas", next_a, expected_fingerprint=view_a.fingerprint,
        )
        assert advanced.generation == 2
        next_b, _ = view_b.queue.claim("worker:b", 11)
        with pytest.raises(MilestoneCheckpointConflict, match="since last read"):
            b.save(
                "run:cas", next_b, expected_fingerprint=view_b.fingerprint,
            )
        saved = b.load("run:cas", source_commit=COMMIT, artifact_digest=SOURCE)
        assert saved.queue.fingerprint == next_a.fingerprint
        assert saved.generation == advanced.generation


def test_save_rejects_unapproved_source_rebinding(tmp_path):
    with SQLiteMilestoneQueueStore(tmp_path / "milestones.sqlite") as store:
        store.save("run:source", queue())
        with pytest.raises(MilestoneCheckpointConflict, match="source binding"):
            store.save("run:source", MilestoneQueue.start("c" * 40, SOURCE))
        with pytest.raises(MilestoneCheckpointError, match="another source"):
            store.load("run:source", source_commit="c" * 40,
                       artifact_digest=SOURCE)


def test_persisted_snapshot_detects_row_tampering(tmp_path):
    path = tmp_path / "tamper.sqlite"
    with SQLiteMilestoneQueueStore(path) as store:
        store.save("run:tamper", queue())
        store._connection.execute(
            "UPDATE milestone_queue_checkpoint SET payload = ?",
            (b'{"forged":true}',),
        )
        with pytest.raises(MilestoneCheckpointError, match="content hash"):
            store.load("run:tamper", source_commit=COMMIT,
                       artifact_digest=SOURCE)
        with pytest.raises(MilestoneCheckpointError, match="corrupted"):
            store.save("run:tamper", queue())


def test_rehashed_but_nonsensical_checkpoint_fails_typed_replay(tmp_path):
    path = tmp_path / "malformed.sqlite"
    with SQLiteMilestoneQueueStore(path) as store:
        store.save("run:tamper", queue())
        forged = b'{"queue":{"work":[]},"schema":"skeleton.jeeves.milestone_durable_queue.v1"}'
        store._connection.execute(
            "UPDATE milestone_queue_checkpoint SET payload=?,payload_sha256=?",
            (forged, hashlib.sha256(forged).hexdigest()),
        )
        with pytest.raises(MilestoneCheckpointError):
            store.load("run:tamper", source_commit=COMMIT, artifact_digest=SOURCE)


def test_restored_expired_lease_is_recovered_not_reused(tmp_path):
    path = tmp_path / "expire.sqlite"
    with SQLiteMilestoneQueueStore(path) as store:
        initial = store.save("run:recover", queue())
        active, lease = initial.queue.claim("worker:old", 10)
        store.save("run:recover", active,
                   expected_fingerprint=initial.fingerprint)
    with SQLiteMilestoneQueueStore(path) as store:
        restored = store.load("run:recover", source_commit=COMMIT,
                              artifact_digest=SOURCE)
        assert lease.milestone_id == "M001"
        after = restored.queue.expire(200, retry_seconds=1)
        updated = store.save("run:recover", after,
                             expected_fingerprint=restored.fingerprint)
        assert updated.queue.get("M001").status == "pending"
        assert updated.queue.get("M001").owner is None
        assert updated.queue.board.completion_count == 0
        assert len(updated.queue.events) == 2


@pytest.mark.parametrize("run", ("", "../../shadow", "unsafe key", 1, None))
def test_run_scope_is_canonical(run, tmp_path):
    with SQLiteMilestoneQueueStore(tmp_path / "scope.sqlite") as store:
        with pytest.raises(MilestoneCheckpointError, match="run identity"):
            store.save(run, queue())


def test_namespace_scopes_restore_without_cross_run_leak(tmp_path):
    path = tmp_path / "namespaces.sqlite"
    with SQLiteMilestoneQueueStore(path, namespace="first") as a:
        a.save("run:one", queue())
    with SQLiteMilestoneQueueStore(path, namespace="second") as b:
        assert b.load("run:one", source_commit=COMMIT, artifact_digest=SOURCE) is None
        b.save("run:one", queue())
    with SQLiteMilestoneQueueStore(path, namespace="first") as a:
        assert a.load("run:one", source_commit=COMMIT,
                      artifact_digest=SOURCE).generation == 1


def test_closed_store_refuses_all_new_work(tmp_path):
    store = SQLiteMilestoneQueueStore(tmp_path / "closed.sqlite")
    store.close()
    with pytest.raises(MilestoneCheckpointError, match="closed"):
        store.save("run:closed", queue())
    with pytest.raises(MilestoneCheckpointError, match="closed"):
        store.load("run:closed", source_commit=COMMIT, artifact_digest=SOURCE)

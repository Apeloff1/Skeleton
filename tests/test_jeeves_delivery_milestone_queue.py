"""Long-running milestone scheduler: source-bound leases, retries and receipts."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.delivery_milestone_queue import (
    MilestoneQueue, QueueContractError, restore_queue, verify_queue,
)
from skeleton.jeeves.agent.delivery_milestone_workbench import HostMeasurement
from skeleton.jeeves.agent.delivery_milestone_workbench import CRITERION_BY_ID


COMMIT = "a" * 40
ROOT = "b" * 64


def check(name, value=None):
    def run(spec, commit, digest):
        return HostMeasurement(
            milestone_id=spec.milestone_id, checker_id=name,
            source_commit=commit, artifact_digest=digest,
            metric=spec.metric, unit=spec.unit,
            observed=spec.target if value is None else value,
            sample_count=spec.min_samples,
            method="native-check-fixture",
            evidence_ref=f"fixture:{name}:{spec.milestone_id}",
            scope="reviewed exact source bytes",
        )
    return run


def passes():
    return check("host-primary"), check("host-secondary")


def start(**kwargs):
    return MilestoneQueue.start(COMMIT, ROOT, **kwargs)


def test_empty_queue_contains_exact_100_unverified_jobs():
    queue = start()
    assert queue.summary()["target"] == 100
    assert queue.summary()["completed"] == 0
    assert queue.summary()["pending"] == 100
    assert queue.summary()["event_count"] == 0
    assert queue.ready(10) == tuple(f"M{i:03}" for i in range(1, 101, 10))
    assert restore_queue(queue, COMMIT, ROOT) == queue


def test_claim_and_complete_opens_dependency_chain():
    queue, lease = start().claim("host-worker-1", 10)
    assert lease.milestone_id == "M001"
    assert lease.expires_at == 130
    assert queue.get("M001").status == "leased"
    assert "M001" not in queue.ready(11)
    assert "M002" not in queue.ready(11)
    queue, verdict = queue.settle(lease, 11, *passes())
    assert verdict.passed
    assert queue.get("M001").status == "passed"
    assert queue.board.completion_count == 1
    assert "M002" in queue.ready(12)
    assert len(queue.events) == 2
    verify_queue(queue)
    assert restore_queue(queue, COMMIT, ROOT) == queue


def test_fail_and_retry_with_fresh_lease_token():
    queue, lease = start(max_attempts=2, priorities={"M001": 10}).claim("host-worker", 0)
    q, result = queue.settle(
        lease, 2, check("host-primary", -1),
        check("host-secondary", -1), retry_seconds=5,
    )
    assert not result.passed
    assert q.get("M001").attempts == 1
    assert q.get("M001").status == "pending"
    assert q.get("M001").retry_after == 7
    assert "M001" not in q.ready(6)
    # Other domains are ready while this domain's dependency is blocked.
    assert "M011" in q.ready(6)
    with pytest.raises(QueueContractError, match="stale"):
        q.settle(lease, 3, *passes())
    q, other = q.claim("host-other", 6)
    assert other.milestone_id != "M001"
    q, _ = q.settle(other, 6.5, *passes())
    q, fresh = q.claim("host-worker", 7)
    assert fresh.milestone_id == "M001"
    assert fresh.serial != lease.serial
    q, failed = q.settle(
        fresh, 8, check("host-primary", -1),
        check("host-secondary", -1),
    )
    assert not failed.passed
    assert q.get("M001").status == "failed"
    assert q.get("M001").attempts == 2
    assert "M001" not in q.ready(100)
    assert q.summary()["failed"] == 1


def test_expired_lease_releases_job_and_revokes_old_token():
    queue, lease = start(max_attempts=2, lease_seconds=5, priorities={"M001": 10}).claim("worker", 10)
    assert queue.expire(14) == queue
    recovered = queue.expire(15, retry_seconds=2)
    assert recovered.get("M001").status == "pending"
    assert recovered.get("M001").retry_after == 17
    with pytest.raises(QueueContractError, match="stale"):
        recovered.settle(lease, 16, *passes())
    assert "M001" in recovered.ready(17)
    recovered, fresh = recovered.claim("worker", 17)
    assert fresh.serial != lease.serial
    recovered, verdict = recovered.settle(fresh, 18, *passes())
    assert verdict.passed


def test_exhausted_expired_lease_cannot_infinite_retry():
    queue, lease = start(max_attempts=1, lease_seconds=3).claim("worker", 1)
    failed = queue.expire(4)
    assert failed.get("M001").status == "failed"
    assert "M001" not in failed.ready(10_000)
    assert failed.summary()["failed"] == 1


def test_priority_is_deterministic_but_prerequisites_remain_required():
    queue = start(priorities={"M021": 500, "M022": 999,
                              "M001": 100})
    assert queue.ready(0)[0] == "M021"
    assert "M022" not in queue.ready(0)
    queue, lease = queue.claim("worker", 0)
    assert lease.milestone_id == "M021"


def test_progress_across_hundred_milestones_with_no_fake_green():
    queue = start(lease_seconds=10)
    for i in range(100):
        queue, lease = queue.claim("worker", i * 2)
        assert lease is not None
        queue, verdict = queue.settle(lease, i * 2 + 1, *passes())
        assert verdict.passed
    assert queue.board.completion_count == 100
    assert queue.summary()["completed"] == 100
    assert queue.summary()["pending"] == 0
    assert len(queue.events) == 200
    assert not queue.ready(999)
    verify_queue(queue)
    assert restore_queue(queue, COMMIT, ROOT).fingerprint == queue.fingerprint


def test_no_registered_host_verifiers_cannot_complete_milestones():
    queue, lease = start(max_attempts=1).claim("worker", 0)
    queue, result = queue.settle(lease, 1, None, None)
    assert not result.passed
    assert queue.board.completion_count == 0
    assert queue.get("M001").status == "failed"
    assert queue.summary()["completed"] == 0


def test_stale_or_forged_source_is_rejected_on_restore_and_settle():
    queue, lease = start().claim("worker", 0)
    with pytest.raises(QueueContractError, match="source"):
        restore_queue(queue, "c" * 40, ROOT)
    with pytest.raises(QueueContractError, match="source"):
        restore_queue(queue, COMMIT, "d" * 64)
    with pytest.raises(QueueContractError, match="forged"):
        queue.settle(replace(lease, artifact_digest="e" * 64),
                     1, *passes())


def test_different_worker_cannot_steal_authorized_lease():
    queue, lease = start().claim("worker-original", 0)
    with pytest.raises(QueueContractError, match="foreign"):
        queue.settle(replace(lease, owner="worker-fraud"), 1, *passes())


def test_expiration_boundary_disallows_late_result():
    queue, lease = start(lease_seconds=5).claim("worker", 2)
    with pytest.raises(QueueContractError, match="expired"):
        queue.settle(lease, 7, *passes())


@pytest.mark.parametrize("now", (-1, float("nan"), float("inf"), True))
def test_monotonic_host_clock_must_be_finite_nonnegative_number(now):
    with pytest.raises(QueueContractError, match="finite"):
        start().ready(now)


@pytest.mark.parametrize("field,value", (
    ("digest", "0" * 64), ("previous", "1" * 64),
    ("sequence", 55), ("milestone_id", "M052"),
    ("action", "pretend_pass"),
))
def test_queue_event_mutations_are_rejected_on_replay(field, value):
    queue, _ = start().claim("worker", 0)
    tampered_event = replace(queue.events[0], **{field: value})
    with pytest.raises(QueueContractError):
        verify_queue(replace(queue, events=(tampered_event,)))


def test_queue_rejects_reordered_or_missing_work():
    queue = start()
    with pytest.raises(QueueContractError, match="reordered"):
        verify_queue(replace(queue, work=tuple(reversed(queue.work))))
    with pytest.raises(QueueContractError, match="reordered"):
        verify_queue(replace(queue, work=queue.work[:-1]))


def test_queue_rejects_unauthorized_status_upgrade():
    queue = start()
    work = list(queue.work)
    work[0] = replace(work[0], status="passed")
    with pytest.raises(QueueContractError, match="pass state"):
        verify_queue(replace(queue, work=tuple(work)))


@pytest.mark.parametrize("value", (0, -1, 51, True))
def test_retry_budget_is_finite_and_positive(value):
    with pytest.raises(QueueContractError, match="retry policy"):
        start(max_attempts=value)


def test_duplicate_lease_token_is_detected():
    queue, lease = start().claim("worker", 0)
    items = list(queue.work)
    items[10] = replace(items[10], status="leased", attempts=1,
                        owner="worker", lease_expires=lease.expires_at,
                        lease_serial=lease.serial)
    with pytest.raises(QueueContractError, match="duplicate lease"):
        verify_queue(replace(queue, work=tuple(items)))

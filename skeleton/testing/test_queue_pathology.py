from skeleton.agents.queue_pathology import (
    QueueDisposition,
    QueueObservation,
    classify_queue_observation,
    summarize_queue_health,
)


def test_orphaned_conflict_becomes_zombie_without_consuming_capacity():
    decision = classify_queue_observation(
        QueueObservation("run-1", "queued", 3600, attempts=3, last_status=409, source_exists=False)
    )
    assert decision.disposition is QueueDisposition.ZOMBIE
    assert decision.retry is True
    assert decision.consume_capacity is False


def test_zombie_retry_budget_escalates_instead_of_spinning_forever():
    decision = classify_queue_observation(
        QueueObservation("run-1", "queued", 3600, attempts=8, last_status=422, source_exists=False)
    )
    assert decision.disposition is QueueDisposition.ZOMBIE
    assert decision.retry is False
    assert decision.escalate is True


def test_authoritative_work_is_never_reclassified_as_disposable_zombie():
    decision = classify_queue_observation(
        QueueObservation(
            "gate", "queued", 3600, attempts=99, last_status=409,
            source_exists=False, authoritative=True,
        )
    )
    assert decision.disposition is QueueDisposition.CONGESTED
    assert decision.consume_capacity is True
    assert decision.escalate is True


def test_conflict_without_orphan_evidence_remains_deferred():
    decision = classify_queue_observation(
        QueueObservation("run-2", "queued", 30, last_status=409)
    )
    assert decision.disposition is QueueDisposition.DEFERRED
    assert decision.retry is True


def test_summary_separates_scheduler_residue_from_real_capacity():
    summary = summarize_queue_health(
        [
            QueueObservation("z", "queued", 3600, attempts=8, last_status=409, source_exists=False),
            QueueObservation("live", "in_progress", 10),
            QueueObservation("done", "completed", 10),
        ]
    )
    assert summary["zombie"] == 1
    assert summary["healthy"] == 2
    assert summary["capacity_bearing"] == 1
    assert summary["escalations"] == 1


def test_invalid_thresholds_fail_closed():
    try:
        classify_queue_observation(QueueObservation("x", "queued", 0), retry_budget=0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid retry budget must fail closed")

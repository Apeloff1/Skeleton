"""Durable, bounded Jeeves host-driver: real queue claim/checkpoint/settle."""

import pytest

from skeleton.jeeves.agent.delivery_milestone_queue import MilestoneQueue
from skeleton.jeeves.agent.delivery_milestone_store import (
    MilestoneCheckpointError, SQLiteMilestoneQueueStore,
)
from skeleton.jeeves.agent.delivery_milestone_workbench import (
    ACCEPTANCE_CRITERIA, HostMeasurement,
)
from skeleton.jeeves.agent.delivery_milestone_driver import (
    WorkCycleError, WorkCyclePolicy, execute_durable_work_cycle,
)

COMMIT = "a" * 40
ARTIFACT = "b" * 64
RUN = "run:host-cycle"


def checker(name, *, raises=False):
    def run(spec, source, artifact):
        if raises:
            raise RuntimeError("sensitive host data should not leak to receipt")
        return HostMeasurement(
            milestone_id=spec.milestone_id, checker_id=name,
            source_commit=source, artifact_digest=artifact,
            metric=spec.metric, unit=spec.unit, observed=spec.target,
            sample_count=spec.min_samples, method="fixture-check-v1",
            evidence_ref=f"host:{name}:{spec.milestone_id}",
            scope="identical reviewed source snapshot",
        )
    return run


def pairs():
    return {
        row.milestone_id: (checker("host-one"), checker("host-two"))
        for row in ACCEPTANCE_CRITERIA
    }


def init(path):
    store = SQLiteMilestoneQueueStore(path)
    store.save(RUN, MilestoneQueue.start(COMMIT, ARTIFACT))
    return store


def run(store, *, clock=None, reviewers=None, policy=None, stop=None):
    return execute_durable_work_cycle(
        store, RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        owner="agent:worker", clock=clock or (lambda: 10.0),
        checkers=pairs() if reviewers is None else reviewers,
        policy=policy, stop_requested=stop,
    )


def test_real_host_driver_advances_all_hundred_with_restored_sqlite_state(tmp_path):
    path = tmp_path / "driver.sqlite"
    with init(path) as store:
        for batch in range(5):
            report = run(store, policy=WorkCyclePolicy(max_claims=20))
            assert report.attempted == 20
            assert report.passed == 20
            assert report.blocked == 0
            assert report.candidate_completed == 20 * (batch + 1)
            assert report.generation == 1 + 40 * (batch + 1)
            assert not report.as_dict()["independent_production_signoff"]
            assert report.as_dict()["production_qualified_milestones"] == 0
            assert len(report.generation_receipt) == 64
        assert report.status == "complete"
        snapshot = store.load(RUN, source_commit=COMMIT, artifact_digest=ARTIFACT)
        assert snapshot.queue.board.completion_count == 100
        assert len(snapshot.queue.events) == 200
        assert len(store.checkpoint_history(RUN)) == 201
    with SQLiteMilestoneQueueStore(path) as reopened:
        report = run(reopened)
        assert report.status == "complete"
        assert report.attempted == 0
        assert report.candidate_completed == 100
        assert reopened.checkpoint_history(RUN)[-1]["receipt_digest"] == report.generation_receipt


def test_operator_pause_before_claim_has_zero_side_effects(tmp_path):
    with init(tmp_path / "pause.sqlite") as store:
        before = store.load(RUN, source_commit=COMMIT,
                            artifact_digest=ARTIFACT)
        result = run(store, stop=lambda: True)
        after = store.load(RUN, source_commit=COMMIT,
                           artifact_digest=ARTIFACT)
        assert result.status == "operator_paused"
        assert result.attempted == 0
        assert before.generation == after.generation == 1
        assert before.queue.fingerprint == after.queue.fingerprint


def test_missing_host_reviewers_does_not_claim_or_approve_work(tmp_path):
    with init(tmp_path / "missing.sqlite") as store:
        result = run(store, reviewers={})
        assert result.status == "missing_independent_host_reviewers"
        assert result.attempted == 0
        assert result.candidate_completed == 0
        assert result.generation == 1
        assert store.checkpoint_history(RUN)[0]["generation"] == 1


def test_host_crash_preserves_lease_until_explicit_expiry(tmp_path):
    with init(tmp_path / "exception.sqlite") as store:
        bad = dict(pairs())
        bad["M001"] = (checker("host-bad", raises=True), checker("host-ok"))
        first = run(store, reviewers=bad)
        assert first.status == "host_reviewer_failed"
        assert first.error_type == "RuntimeError"
        assert first.attempted == 0
        assert first.active_leases == 1
        assert first.candidate_completed == 0
        assert "sensitive" not in str(first)
        persisted = store.load(RUN, source_commit=COMMIT, artifact_digest=ARTIFACT)
        assert persisted.generation == 2
        assert persisted.queue.get("M001").status == "leased"
        restored = run(store, clock=lambda: 300.0,
                       policy=WorkCyclePolicy(max_claims=1, retry_seconds=0))
        assert restored.attempted == 1
        assert restored.active_leases == 0
        assert restored.candidate_completed == 1
        assert restored.passed == 1
        persisted = store.load(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        ).queue
        assert persisted.get("M001").status == "pending"
        assert "M011" in persisted.board.passing


def test_reviewer_exceeding_lease_is_not_accepted(tmp_path):
    with init(tmp_path / "expired-review.sqlite") as store:
        values = iter([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 200.0, 200.0])
        result = run(
            store, clock=lambda: next(values),
            policy=WorkCyclePolicy(max_claims=1),
        )
        assert result.status == "host_reviewer_failed"
        assert result.error_type == "review_lease_expired"
        assert result.candidate_completed == 0
        assert store.load(RUN, source_commit=COMMIT,
                          artifact_digest=ARTIFACT).queue.get("M001").status == "leased"


def test_bounded_claims_prevent_uncontrolled_host_fanout(tmp_path):
    with init(tmp_path / "budget.sqlite") as store:
        result = run(store, policy=WorkCyclePolicy(max_claims=3))
        assert result.status == "budget_exhausted"
        assert result.attempted == 3
        assert result.passed == 3
        assert result.generation == 7
        assert result.candidate_completed == 3


def test_no_source_or_uninitialized_queue_is_never_auto_created(tmp_path):
    with SQLiteMilestoneQueueStore(tmp_path / "uninitialized.sqlite") as store:
        with pytest.raises(WorkCycleError, match="not been initialized"):
            run(store)
    with init(tmp_path / "other.sqlite") as store:
        with pytest.raises(MilestoneCheckpointError, match="another source"):
            execute_durable_work_cycle(
                store, RUN, source_commit="c" * 40, artifact_digest=ARTIFACT,
                owner="worker", clock=lambda: 10.0, checkers=pairs(),
            )


def test_untrusted_clock_cannot_advance_source_bound_work(tmp_path):
    with init(tmp_path / "clock.sqlite") as store:
        with pytest.raises(WorkCycleError, match="finite nonnegative"):
            run(store, clock=lambda: float("nan"))
        values = iter([10.0, 9.0])
        with pytest.raises(WorkCycleError, match="backward"):
            run(store, clock=lambda: next(values))
        assert store.load(RUN, source_commit=COMMIT,
                          artifact_digest=ARTIFACT).generation == 1


@pytest.mark.parametrize("bad", (True, 0, -1, 101, 1.5))
def test_claim_budget_validation_is_strict(bad):
    with pytest.raises(WorkCycleError, match="claim budget"):
        WorkCyclePolicy(max_claims=bad)


@pytest.mark.parametrize("bad", (True, 0, -1, float("inf")))
def test_time_budget_validation_is_strict(bad):
    with pytest.raises(WorkCycleError, match="duration"):
        WorkCyclePolicy(max_wall_seconds=bad)


def test_stop_callback_cannot_launder_non_boolean_admission(tmp_path):
    with init(tmp_path / "nonbool.sqlite") as store:
        with pytest.raises(WorkCycleError, match="boolean"):
            run(store, stop=lambda: "yes")
        assert store.load(RUN, source_commit=COMMIT,
                          artifact_digest=ARTIFACT).generation == 1


def test_failed_scoped_metrics_record_blocked_but_never_complete(tmp_path):
    with init(tmp_path / "blocked.sqlite") as store:
        bad = dict(pairs())
        def low(spec, commit, digest):
            return HostMeasurement(
                spec.milestone_id, "host-poor", commit, digest, spec.metric,
                spec.unit, -100, spec.min_samples, "fixture-check-v1",
                f"host:host-poor:{spec.milestone_id}",
                "identical reviewed source snapshot",
            )
        bad["M001"] = (low, checker("host-two"))
        result = run(store, reviewers=bad, policy=WorkCyclePolicy(max_claims=1))
        assert result.status == "budget_exhausted"
        assert result.attempted == 1
        assert result.blocked == 1
        assert result.candidate_completed == 0
        assert store.load(RUN, source_commit=COMMIT,
                          artifact_digest=ARTIFACT).queue.get("M001").status == "pending"



def test_persisted_operator_pause_resume_and_cancel(tmp_path):
    with init(tmp_path / "operator.sqlite") as store:
        paused = store.set_operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            mode="paused", actor_ref="operator:lead",
            reason_ref="incident:hold",
        )
        assert paused.generation == 1
        assert run(store).status == "operator_paused"
        assert store.load(RUN, source_commit=COMMIT,
                          artifact_digest=ARTIFACT).generation == 1
        running = store.set_operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            mode="running", actor_ref="operator:lead",
            reason_ref="incident:resolved",
            expected_generation=1,
        )
        assert running.generation == 2
        report = run(store, policy=WorkCyclePolicy(max_claims=1))
        assert report.passed == 1
        cancelled = store.set_operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            mode="cancelled", actor_ref="operator:lead",
            reason_ref="incident:terminal",
            expected_generation=2,
        )
        assert cancelled.generation == 3
        again = run(store)
        assert again.status == "operator_cancelled"
        assert again.attempted == 0
        assert again.candidate_completed == 1
        with pytest.raises(MilestoneCheckpointError, match="may not resume"):
            store.set_operator_control(
                RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
                mode="running", actor_ref="operator:lead",
                reason_ref="incident:resolved",
                expected_generation=3,
            )


def test_pause_blocks_direct_queue_claim_even_if_driver_bypassed(tmp_path):
    with init(tmp_path / "paused-cas.sqlite") as store:
        state = store.load(RUN, source_commit=COMMIT, artifact_digest=ARTIFACT)
        store.set_operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            mode="paused", actor_ref="operator:lead",
            reason_ref="ops:suspend",
        )
        claimed, _ = state.queue.claim("worker:a", 10)
        with pytest.raises(MilestoneCheckpointError, match="paused queue"):
            store.save(RUN, claimed, expected_fingerprint=state.fingerprint)
        assert store.load(RUN, source_commit=COMMIT,
                          artifact_digest=ARTIFACT).generation == 1


def test_cancel_during_reviewer_prevents_durable_promotion(tmp_path):
    from skeleton.jeeves.agent.delivery_milestone_store import SQLiteMilestoneQueueStore

    path = tmp_path / "race-cancel.sqlite"
    with init(path) as store:
        second = SQLiteMilestoneQueueStore(path)
        try:
            base = pairs()
            def cancel_as_review_happens(spec, commit, artifact):
                second.set_operator_control(
                    RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
                    mode="cancelled", actor_ref="host:operator",
                    reason_ref="ops:abort",
                )
                return checker("host-one")(spec, commit, artifact)

            base["M001"] = (cancel_as_review_happens, checker("host-two"))
            result = run(store, reviewers=base,
                         policy=WorkCyclePolicy(max_claims=1))
            assert result.status == "operator_cancelled"
            assert result.candidate_completed == 0
            assert result.active_leases == 1
            checkpoint = store.load(
                RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            )
            assert checkpoint.queue.get("M001").status == "leased"
            assert checkpoint.queue.board.completion_count == 0
            assert checkpoint.generation == 2
        finally:
            second.close()


def test_stale_operator_generation_and_changed_source_fail_closed(tmp_path):
    from skeleton.jeeves.agent.delivery_milestone_store import (
        MilestoneCheckpointConflict,
    )
    with init(tmp_path / "stale-control.sqlite") as store:
        first = store.set_operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            mode="paused", actor_ref="host:operator", reason_ref="ops:pause",
        )
        with pytest.raises(MilestoneCheckpointConflict):
            store.set_operator_control(
                RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
                mode="running", actor_ref="host:operator",
                reason_ref="ops:continue", expected_generation=3,
            )
        with pytest.raises(MilestoneCheckpointError, match="exact queue source"):
            store.set_operator_control(
                RUN, source_commit="f" * 40, artifact_digest=ARTIFACT,
                mode="running", actor_ref="host:operator",
                reason_ref="ops:continue", expected_generation=first.generation,
            )
        assert store.operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
        ).mode == "paused"


def test_operator_control_detects_modified_db_receipt(tmp_path):
    with init(tmp_path / "forged.sqlite") as store:
        store.set_operator_control(
            RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            mode="paused", actor_ref="host:operator", reason_ref="ops:pause",
        )
        store._connection.execute(
            "UPDATE milestone_queue_control SET receipt_digest = ?",
            ("f" * 64,),
        )
        with pytest.raises(MilestoneCheckpointError, match="altered"):
            store.operator_control(
                RUN, source_commit=COMMIT, artifact_digest=ARTIFACT,
            )

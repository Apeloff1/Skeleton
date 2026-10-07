from skeleton.agents.swarm_load_shed import LoadShedPolicy
from skeleton.agents.swarm_quarantine import QuarantineController
from skeleton.agents.swarm_retry import RetryPolicy
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_quarantine_expires_automatically() -> None:
    now=[0.0]; q=QuarantineController(clock=lambda: now[0])
    q.quarantine("w", reason="cooldown", seconds=10)
    assert q.is_quarantined("w") is True
    now[0]=11
    assert q.is_quarantined("w") is False
    assert q.records() == ()


def test_retry_policy_refuses_succeeded_and_exhausted_tasks() -> None:
    policy=RetryPolicy()
    done=SwarmTask("done", {}, state=TaskState.SUCCEEDED, attempts=1, max_attempts=3)
    exhausted=SwarmTask("dead", {}, state=TaskState.DEAD, attempts=3, max_attempts=3)
    assert policy.evaluate(done).retry is False
    assert policy.evaluate(exhausted).retry is False


def test_retry_policy_allows_queued_work_with_budget() -> None:
    decision=RetryPolicy().evaluate(SwarmTask("t", {}, attempts=1, max_attempts=3))
    assert decision.retry is True and decision.remaining == 2


def test_load_shed_rejects_bulk_work_under_pressure() -> None:
    runtime=SwarmRuntime(); runtime.submit(SwarmTask("queued", {}))
    decision=LoadShedPolicy(max_queue_pressure=0.5).evaluate(runtime, SwarmTask("bulk", {}, priority=100))
    assert decision.admit is False

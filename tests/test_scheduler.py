"""Tests for the swarm scheduler and activity ledger."""

import pytest

from skeleton.agents.ledger import ActivityLedger
from skeleton.agents.scheduler import SwarmScheduler, TaskState
from skeleton.kernel.errors import SchedulingError, TaskDeadLetteredError
from skeleton.kernel.ids import AgentId


class TestScheduler:
    def test_success_path(self):
        sched = SwarmScheduler()
        task = sched.submit("echo", "npc", {"x": 1}, run=lambda p: {"ok": p["x"]})
        ran = sched.run_until_idle()
        assert ran[0].state is TaskState.SUCCEEDED
        assert ran[0].result == {"ok": 1}
        assert sched.get(task.task_id).state is TaskState.SUCCEEDED

    def test_retry_then_dead_letter(self):
        clock = {"t": 0.0}

        def now() -> float:
            return clock["t"]

        def boom(_payload):
            raise RuntimeError("nope")

        sched = SwarmScheduler(clock=now, backoff_base=0.0, backoff_cap=0.0)
        sched.submit("fail", "npc", {}, run=boom, max_retries=1)
        sched.run_once()
        clock["t"] += 1
        sched.run_once()
        clock["t"] += 1
        sched.run_once()
        dead = sched.dead_letters()
        assert dead and dead[0].state is TaskState.DEAD_LETTERED

    def test_shutdown_rejects(self):
        sched = SwarmScheduler()
        sched.shutdown(drain=False)
        with pytest.raises(SchedulingError):
            sched.submit("late", "npc", {}, run=lambda p: p)

    def test_requeue_requires_dead_letter(self):
        sched = SwarmScheduler()
        task = sched.submit("ok", "npc", {}, run=lambda p: {})
        sched.run_until_idle()
        with pytest.raises(TaskDeadLetteredError):
            sched.requeue_dead_letter(task.task_id)


class TestLedger:
    def test_append_and_summarise(self):
        ledger = ActivityLedger()
        agent = AgentId.new()
        ledger.append(agent, "task.npc", {"n": 1}, outcome="success")
        ledger.append(agent, "task.npc", {"n": 2}, outcome="failure")
        summary = ledger.summarise(agent)
        assert summary.total_actions == 2
        assert summary.successes == 1
        assert 0 < summary.success_rate < 1
        assert ledger.stats()["entries"] == 2


def test_delayed_retry_is_separated_from_ready_priority_heap() -> None:
    clock = {"t": 0.0}
    events: list[str] = []

    def now() -> float:
        return clock["t"]

    def fail_once(_payload):
        events.append("retry")
        if events.count("retry") == 1:
            raise RuntimeError("retry later")
        return {"ok": True}

    sched = SwarmScheduler(clock=now, backoff_base=100.0, backoff_cap=100.0)
    retried = sched.submit(
        "retry",
        "npc",
        {},
        run=fail_once,
        priority=0,
        max_retries=1,
    )
    sched.run_once()

    assert retried.state is TaskState.QUEUED
    assert sched.stats()["ready"] == 0
    assert sched.stats()["delayed"] == 1

    ready = sched.submit(
        "ready",
        "npc",
        {},
        run=lambda payload: events.append("ready") or {"ok": True},
        priority=9,
    )
    assert sched.run_once() is ready
    assert events == ["retry", "ready"]

    clock["t"] = 100.0
    assert sched.run_once() is retried
    assert retried.state is TaskState.SUCCEEDED
    assert events == ["retry", "ready", "retry"]


def test_cancelling_delayed_retry_eagerly_releases_delayed_heap_entry() -> None:
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    def fail(_payload):
        raise RuntimeError("retry later")

    sched = SwarmScheduler(clock=now, backoff_base=1000.0, backoff_cap=1000.0)
    task = sched.submit("retry", "npc", {}, run=fail, max_retries=1)
    sched.run_once()
    assert sched.stats()["delayed"] == 1

    sched.cancel(task.task_id)
    assert task.state is TaskState.CANCELLED
    assert sched.stats()["delayed"] == 0
    assert task not in sched.pending()

    clock["t"] = 2000.0
    assert sched.run_once() is None

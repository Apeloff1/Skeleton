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

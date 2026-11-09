"""Fairness, failover, assignment, and shutdown tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.shells.queue import QueueState,ShellWorkQueue
from skeleton.shells.runner import ShellCommand
from skeleton.shells.worker import QueueWorker,WorkerPolicy
from skeleton.shells.worker_failover import WorkerFailover
from skeleton.shells.worker_fairness import DeficitFairQueue,FairSharePolicy
from skeleton.shells.worker_heartbeat import HeartbeatPolicy,HeartbeatRegistry
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry
from skeleton.shells.worker_shutdown import ShutdownPhase,ShutdownPolicy,WorkerShutdownCoordinator


def test_fairness_fifo_with_equal_weights():
    queue=DeficitFairQueue()
    queue.enqueue("a","a1")
    queue.enqueue("b","b1")
    queue.enqueue("a","a2")
    assert queue.pop()==("a","a1")
    assert queue.pop()==("b","b1")
    assert queue.pop()==("a","a2")


def test_fairness_weighted_principal_gets_more_dispatches():
    queue=DeficitFairQueue(FairSharePolicy(quantum=1))
    queue.set_weight("fast",3)
    for i in range(6):
        queue.enqueue("fast",f"f{i}",cost=2)
        queue.enqueue("slow",f"s{i}",cost=2)
    first=[queue.pop()[0] for _ in range(6)]
    assert first.count("fast")>first.count("slow")


def test_fairness_cost_delays_expensive_job():
    queue=DeficitFairQueue()
    queue.enqueue("a","expensive",cost=3)
    queue.enqueue("b","cheap",cost=1)
    assert queue.pop()==("b","cheap")
    # Repeated turns eventually accumulate enough deficit for a.
    assert queue.pop()==("a","expensive")


def test_fairness_remove_nonempty_requires_override():
    queue=DeficitFairQueue()
    queue.enqueue("a","x")
    with pytest.raises(RuntimeError):
        queue.remove_principal("a")
    assert queue.remove_principal("a",require_empty=False)


def test_fairness_principal_capacity():
    queue=DeficitFairQueue(FairSharePolicy(max_principals=1))
    queue.enqueue("a","x")
    with pytest.raises(RuntimeError):
        queue.enqueue("b","y")


def test_fairness_snapshot_counts():
    queue=DeficitFairQueue()
    queue.enqueue("a","x")
    queue.enqueue("b","y")
    snap=queue.snapshot()
    assert snap.total_queued==2
    queue.pop()
    assert queue.snapshot().total_dispatched==1


def setup_failover(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    a=WorkerIdentity("a",1);b=WorkerIdentity("b",1)
    workers.register(a);workers.register(b)
    beats=HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(late_after_seconds=2,stale_after_seconds=4),
        clock=lambda:now[0],
    )
    beats.beat(a,sequence=1);beats.beat(b,sequence=1)
    failover=WorkerFailover(workers,beats,clock=lambda:now[0])
    failover.create("g",[a,b],active_worker_id="a")
    return workers,a,b,beats,failover


def test_failover_keeps_healthy_active():
    now=[0.0]
    _,_,_,_,failover=setup_failover(now)
    decision=failover.evaluate("g")
    assert not decision.changed
    assert decision.active_worker_id=="a"


def test_failover_promotes_healthy_standby():
    now=[0.0]
    _,a,b,beats,failover=setup_failover(now)
    now[0]=3
    beats.beat(b,sequence=2)
    now[0]=5
    beats.beat(b,sequence=3)
    decision=failover.evaluate("g")
    assert decision.changed
    assert decision.previous_worker_id=="a"
    assert decision.active_worker_id=="b"


def test_failover_no_healthy_standby_does_not_change():
    now=[0.0]
    _,_,_,_,failover=setup_failover(now)
    now[0]=5
    decision=failover.evaluate("g")
    assert not decision.changed
    assert "no healthy" in decision.reason


@dataclass(frozen=True)
class Outcome:
    ok:bool


class Executor:
    def __init__(self,ok=True):self.ok=ok
    def execute(self,*args,**kwargs):return Outcome(self.ok)


def make_worker(queue,owner="w",ok=True):
    return QueueWorker(owner,queue,Executor(ok),policy=WorkerPolicy(max_items_per_drain=100))


def test_shutdown_drains_queue_and_stops_workers():
    now=[0.0]
    queue=ShellWorkQueue(clock=lambda:now[0])
    for i in range(3):queue.enqueue(ShellCommand("python"),item_id=str(i))
    workers=[make_worker(queue,"a"),make_worker(queue,"b")]
    report=WorkerShutdownCoordinator(
        workers,
        policy=ShutdownPolicy(max_rounds=10,deadline_seconds=100),
        clock=lambda:now[0],
    ).shutdown()
    assert report.phase is ShutdownPhase.STOPPED
    assert queue.counts()["completed"]==3
    assert all(worker.snapshot().stop_requested for worker in workers)


def test_shutdown_no_drain_leaves_queued_but_stops():
    queue=ShellWorkQueue()
    queue.enqueue(ShellCommand("python"))
    worker=make_worker(queue)
    report=WorkerShutdownCoordinator(
        [worker],policy=ShutdownPolicy(drain_claimed=False)
    ).shutdown()
    assert report.phase is ShutdownPhase.STOPPED
    assert queue.counts()["queued"]==1


def test_shutdown_failed_worker_can_abort():
    queue=ShellWorkQueue()
    queue.enqueue(ShellCommand("python"),item_id="x")
    failed=make_worker(queue,"a",ok=False)
    failed.run_once()
    # Trip failed state with a strict failure guard.
    strict=QueueWorker("b",queue,Executor(False),policy=WorkerPolicy(max_consecutive_failures=1))
    queue.enqueue(ShellCommand("python"),item_id="y")
    strict.run_once()
    report=WorkerShutdownCoordinator(
        [strict],
        policy=ShutdownPolicy(stop_on_failed_worker=True),
    ).shutdown()
    assert report.phase is ShutdownPhase.INCOMPLETE


def test_shutdown_requires_shared_queue():
    with pytest.raises(ValueError):
        WorkerShutdownCoordinator([make_worker(ShellWorkQueue(),"a"),make_worker(ShellWorkQueue(),"b")])

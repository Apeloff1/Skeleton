"""Ownership epoch, SLA, and drain-budget tests."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_drain_budget import DrainLimits,WorkerDrainBudget
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry
from skeleton.shells.worker_ownership import OwnershipConflict,WorkerOwnership
from skeleton.shells.worker_sla import SLAClass,SLABudget,WorkerSLA


def setup_ownership(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    worker=WorkerIdentity("w",1)
    workers.register(worker)
    return workers,worker,WorkerOwnership(workers,clock=lambda:now[0])


def test_ownership_acquire_require_release():
    now=[0.0]
    _,worker,ownership=setup_ownership(now)
    token=ownership.acquire("resource",worker,ttl_seconds=10)
    assert ownership.require(token)==token
    assert ownership.release(token)
    with pytest.raises(OwnershipConflict):
        ownership.require(token)


def test_ownership_conflict():
    now=[0.0]
    _,worker,ownership=setup_ownership(now)
    ownership.acquire("resource",worker)
    with pytest.raises(OwnershipConflict):
        ownership.acquire("resource",worker)


def test_ownership_expiry_allows_new_epoch():
    now=[0.0]
    _,worker,ownership=setup_ownership(now)
    first=ownership.acquire("resource",worker,ttl_seconds=5)
    now[0]=5
    second=ownership.acquire("resource",worker,ttl_seconds=5)
    assert second.epoch==first.epoch+1
    assert second.token!=first.token


def test_ownership_old_token_cannot_release_new_epoch():
    now=[0.0]
    _,worker,ownership=setup_ownership(now)
    first=ownership.acquire("resource",worker,ttl_seconds=5)
    now[0]=5
    second=ownership.acquire("resource",worker)
    assert not ownership.release(first)
    assert ownership.require(second)==second


def test_ownership_generation_replacement_invalidates_token():
    now=[0.0]
    workers,worker,ownership=setup_ownership(now)
    token=ownership.acquire("resource",worker)
    workers.replace(WorkerIdentity("w",2))
    with pytest.raises(Exception):
        ownership.require(token)


def test_ownership_renew_preserves_epoch_and_token():
    now=[0.0]
    _,worker,ownership=setup_ownership(now)
    first=ownership.acquire("resource",worker,ttl_seconds=5)
    now[0]=1
    renewed=ownership.renew(first,ttl_seconds=10)
    assert renewed.epoch==first.epoch
    assert renewed.token==first.token
    assert renewed.expires_at==11


def test_sla_defaults_have_all_classes():
    sla=WorkerSLA()
    for value in SLAClass:
        assert sla.budget(value).max_runtime_seconds>0


def test_sla_queue_breach():
    sla=WorkerSLA({value:SLABudget(1,10,2,1) for value in SLAClass})
    result=sla.evaluate(SLAClass.INTERACTIVE,queue_age_seconds=2)
    assert result.queue_breached
    assert result.breached


def test_sla_runtime_breach():
    sla=WorkerSLA({value:SLABudget(10,1,2,1) for value in SLAClass})
    result=sla.evaluate(SLAClass.STANDARD,queue_age_seconds=0,runtime_seconds=2)
    assert result.runtime_breached


def test_sla_attempt_breach():
    sla=WorkerSLA({value:SLABudget(10,10,1,1) for value in SLAClass})
    result=sla.evaluate(SLAClass.BATCH,queue_age_seconds=0,attempts=2)
    assert result.attempts_breached


def test_sla_exact_limit_not_breached():
    sla=WorkerSLA({value:SLABudget(10,20,3,1) for value in SLAClass})
    result=sla.evaluate(SLAClass.BATCH,queue_age_seconds=10,runtime_seconds=20,attempts=3)
    assert not result.breached


def test_sla_requires_every_class():
    with pytest.raises(ValueError):
        WorkerSLA({SLAClass.INTERACTIVE:SLABudget(1,1,1,1)})


def test_drain_budget_item_limit():
    now=[0.0]
    budget=WorkerDrainBudget(DrainLimits(max_items=2,max_failures=2,max_seconds=10),clock=lambda:now[0])
    budget.record(ok=True)
    budget.record(ok=True)
    assert not budget.can_start()
    assert "items" in budget.exhausted_reasons()


def test_drain_budget_failure_limit():
    now=[0.0]
    budget=WorkerDrainBudget(DrainLimits(max_items=10,max_failures=1,max_seconds=10),clock=lambda:now[0])
    budget.record(ok=False)
    assert budget.can_start()
    budget.record(ok=False)
    assert not budget.can_start()
    assert "failures" in budget.exhausted_reasons()


def test_drain_budget_time_limit():
    now=[0.0]
    budget=WorkerDrainBudget(DrainLimits(max_items=10,max_failures=10,max_seconds=5),clock=lambda:now[0])
    now[0]=5
    assert not budget.can_start()
    assert budget.remaining_seconds()==0
    assert "time" in budget.exhausted_reasons()


def test_drain_budget_record_after_exhaustion_rejected():
    now=[0.0]
    budget=WorkerDrainBudget(DrainLimits(max_items=1,max_failures=1,max_seconds=10),clock=lambda:now[0])
    budget.record(ok=True)
    with pytest.raises(RuntimeError):
        budget.record(ok=True)

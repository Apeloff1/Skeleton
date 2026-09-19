"""Capacity, admission, balancing, and batch planning tests."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_admission import WorkerAdmission,WorkerAdmissionCode
from skeleton.shells.worker_affinity import JobRequirements
from skeleton.shells.worker_backpressure import BackpressureDecision,BackpressureState
from skeleton.shells.worker_batches import WorkerBatchItem,WorkerBatchPlanner
from skeleton.shells.worker_balancer import BalanceAction,BalancePolicy,WorkerBalancer
from skeleton.shells.worker_capacity import CapacityDemand,CapacityView,WorkerCapacity,WorkerCapacityCatalog
from skeleton.shells.worker_heartbeat import LivenessView,WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistration,WorkerRole
from skeleton.shells.worker_quota import WorkerQuota,WorkerQuotaLedger


def reg(worker,role=WorkerRole.GENERAL,enabled=True):
    identity=WorkerIdentity(worker,1,role=role)
    return WorkerRegistration(identity,worker,0.0,0.0,enabled=enabled)


def live(worker,inflight=0,state=WorkerLiveness.HEALTHY):
    return LivenessView(worker,1,state,0.0,1,False,inflight)


def pressure(state):
    return BackpressureDecision(state,0.0 if state is BackpressureState.PAUSED else 1.0,"x",0,0,0,False,0)


def test_admission_allows_healthy_worker():
    worker=reg("a")
    admission=WorkerAdmission()
    decision=admission.inspect(principal="p",registrations=[worker],liveness={"a":live("a")})
    assert decision.allowed
    assert decision.code is WorkerAdmissionCode.ALLOWED
    assert decision.worker==worker


def test_admission_paused_backpressure_denies_before_placement():
    worker=reg("a")
    decision=WorkerAdmission().inspect(
        principal="p",registrations=[worker],liveness={"a":live("a")},
        backpressure=pressure(BackpressureState.PAUSED),
    )
    assert not decision.allowed
    assert decision.code is WorkerAdmissionCode.BACKPRESSURE


def test_admission_quota_denial():
    worker=reg("a")
    quotas=WorkerQuotaLedger(WorkerQuota(max_inflight=0,max_starts_per_window=0))
    decision=WorkerAdmission(quotas=quotas).inspect(
        principal="p",registrations=[worker],liveness={"a":live("a")}
    )
    assert not decision.allowed
    assert decision.code is WorkerAdmissionCode.QUOTA


def test_admission_no_worker():
    decision=WorkerAdmission().inspect(principal="p",registrations=[],liveness={})
    assert decision.code is WorkerAdmissionCode.NO_WORKER


def test_admission_capacity_denial():
    worker=reg("a")
    capacities=WorkerCapacityCatalog()
    capacities.set("a",WorkerCapacity(max_inflight=1,max_weight=1))
    decision=WorkerAdmission(capacities=capacities).inspect(
        principal="p",registrations=[worker],liveness={"a":live("a",inflight=1)},
        demand=CapacityDemand(),
    )
    assert not decision.allowed
    assert decision.code is WorkerAdmissionCode.CAPACITY


def test_admission_falls_through_to_second_candidate_with_capacity():
    workers=[reg("a"),reg("b")]
    capacities=WorkerCapacityCatalog()
    capacities.set("a",WorkerCapacity(max_inflight=1,max_weight=1))
    capacities.set("b",WorkerCapacity(max_inflight=2,max_weight=2))
    decision=WorkerAdmission(capacities=capacities).inspect(
        principal="p",registrations=workers,
        liveness={"a":live("a",inflight=1),"b":live("b",inflight=0)},
        demand=CapacityDemand(),
    )
    assert decision.allowed
    assert decision.worker.identity.worker_id=="b"


def test_admission_role_requirement():
    workers=[reg("a",WorkerRole.BUILDER),reg("b",WorkerRole.TESTER)]
    decision=WorkerAdmission().inspect(
        principal="p",registrations=workers,
        liveness={"a":live("a"),"b":live("b")},
        requirements=JobRequirements(required_role=WorkerRole.TESTER),
    )
    assert decision.worker.identity.worker_id=="b"


def make_view(worker,inflight,max_inflight,state=WorkerLiveness.HEALTHY):
    return CapacityView(worker,1,WorkerCapacity(max_inflight=max_inflight,max_weight=max_inflight),inflight,inflight,state)


def test_balancer_requests_capacity_on_high_worker():
    report=WorkerBalancer().analyze([make_view("a",9,10)])
    assert report.recommendations[0].action is BalanceAction.ADD_CAPACITY


def test_balancer_keeps_mid_utilization():
    report=WorkerBalancer().analyze([make_view("a",5,10)])
    assert report.recommendations[0].action is BalanceAction.KEEP


def test_balancer_can_recommend_drain_when_fleet_has_spare_capacity():
    views=[make_view("a",0,10),make_view("b",5,10)]
    report=WorkerBalancer(BalancePolicy(min_healthy_workers=1)).analyze(views)
    actions={item.worker_id:item.action for item in report.recommendations}
    assert actions["a"] is BalanceAction.DRAIN


def test_balancer_does_not_drain_below_min_workers():
    report=WorkerBalancer(BalancePolicy(min_healthy_workers=1)).analyze([make_view("a",0,10)])
    assert report.recommendations[0].action is BalanceAction.KEEP


def test_balancer_no_healthy_workers_requests_capacity():
    report=WorkerBalancer().analyze([make_view("a",0,10,WorkerLiveness.STALE)])
    assert report.healthy_workers==0
    assert report.recommendations[0].action is BalanceAction.ADD_CAPACITY


def test_balancer_aggregate_numbers():
    report=WorkerBalancer().analyze([make_view("a",5,10),make_view("b",5,10)])
    assert report.total_inflight==10
    assert report.total_capacity==20
    assert report.aggregate_utilization==0.5


def test_batch_plan_allows_all():
    worker=reg("a")
    planner=WorkerBatchPlanner(WorkerAdmission())
    plan=planner.plan(
        [WorkerBatchItem("1","p"),WorkerBatchItem("2","p")],
        registrations=[worker],
        liveness={"a":live("a")},
    )
    assert plan.allowed
    assert plan.accepted==2
    assert plan.rejected==0


def test_batch_plan_exposes_rejection():
    planner=WorkerBatchPlanner(WorkerAdmission())
    plan=planner.plan(
        [WorkerBatchItem("1","p")],
        registrations=[],
        liveness={},
    )
    assert not plan.allowed
    assert plan.rejected==1


@pytest.mark.parametrize("item_id,principal",[("","p"),("x","")])
def test_batch_item_requires_identity_fields(item_id,principal):
    with pytest.raises(ValueError):
        WorkerBatchItem(item_id,principal)

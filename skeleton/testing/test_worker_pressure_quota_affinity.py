"""Backpressure, quota, affinity, and capacity tests."""

from __future__ import annotations

import pytest

from skeleton.shells.worker_affinity import AffinityMode,AffinityTerm,JobRequirements,WorkerPlacement
from skeleton.shells.worker_backpressure import BackpressureController,BackpressurePolicy,BackpressureSample,BackpressureState
from skeleton.shells.worker_capacity import CapacityDemand,CapacityView,WorkerCapacity,WorkerCapacityCatalog
from skeleton.shells.worker_heartbeat import LivenessView,WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistration,WorkerRole
from skeleton.shells.worker_quota import WorkerQuota,WorkerQuotaLedger


def registration(worker_id,*,role=WorkerRole.GENERAL,labels=None,features=(),enabled=True):
    identity=WorkerIdentity(worker_id,1,role=role,labels=labels or {},features=frozenset(features))
    return WorkerRegistration(identity,worker_id,0.0,0.0,enabled=enabled)


def live(worker_id,inflight=0,state=WorkerLiveness.HEALTHY):
    return LivenessView(worker_id,1,state,0.0,1,False,inflight)


def sample(*,queued=0,claimed=0,ok=10,failed=0,latency=10,at=0):
    return BackpressureSample(queued,claimed,1,0,ok,failed,latency,at)


def test_backpressure_default_open():
    controller=BackpressureController()
    decision=controller.observe(sample())
    assert decision.state is BackpressureState.OPEN
    assert decision.accepts_new_work


def test_backpressure_high_queue_throttles():
    controller=BackpressureController(BackpressurePolicy(queue_high_watermark=10,queue_critical_watermark=20))
    decision=controller.observe(sample(queued=10))
    assert decision.state is BackpressureState.THROTTLED
    assert decision.bounded_parallelism(8)==4


def test_backpressure_critical_queue_pauses():
    controller=BackpressureController(BackpressurePolicy(queue_high_watermark=10,queue_critical_watermark=20))
    decision=controller.observe(sample(queued=20))
    assert decision.state is BackpressureState.PAUSED
    assert decision.bounded_parallelism(8)==0


def test_backpressure_failure_ratio_can_pause():
    policy=BackpressurePolicy(failure_ratio_high=.2,failure_ratio_critical=.5,ewma_alpha=1)
    controller=BackpressureController(policy)
    decision=controller.observe(sample(ok=1,failed=2))
    assert decision.state is BackpressureState.PAUSED


def test_backpressure_latency_can_throttle():
    policy=BackpressurePolicy(latency_high_ms=100,latency_critical_ms=1000,ewma_alpha=1)
    controller=BackpressureController(policy)
    assert controller.observe(sample(latency=100)).state is BackpressureState.THROTTLED


def test_backpressure_recovery_requires_hysteresis():
    policy=BackpressurePolicy(queue_high_watermark=1,queue_critical_watermark=2,recovery_samples=2,ewma_alpha=1)
    controller=BackpressureController(policy)
    assert controller.observe(sample(queued=2)).state is BackpressureState.PAUSED
    assert controller.observe(sample(queued=0)).state is BackpressureState.PAUSED
    assert controller.observe(sample(queued=0)).state is BackpressureState.THROTTLED
    assert controller.observe(sample(queued=0)).state is BackpressureState.THROTTLED
    assert controller.observe(sample(queued=0)).state is BackpressureState.OPEN


def test_backpressure_reset_clears_state():
    controller=BackpressureController(BackpressurePolicy(queue_high_watermark=1,queue_critical_watermark=2))
    controller.observe(sample(queued=2))
    controller.reset()
    assert controller.state is BackpressureState.OPEN


@pytest.mark.parametrize("parallelism",[0,-1])
def test_bounded_parallelism_requires_positive(parallelism):
    decision=BackpressureController().observe(sample())
    with pytest.raises(ValueError):
        decision.bounded_parallelism(parallelism)


def test_quota_reserve_and_complete():
    now=[0.0]
    ledger=WorkerQuotaLedger(WorkerQuota(max_inflight=2),clock=lambda:now[0])
    reservation=ledger.reserve("tenant")
    assert ledger.usage("tenant").inflight==1
    usage=ledger.complete(reservation,ok=True,output_bytes=5)
    assert usage.inflight==0
    assert usage.output_bytes==5


def test_quota_inflight_bound():
    ledger=WorkerQuotaLedger(WorkerQuota(max_inflight=1))
    first=ledger.reserve("tenant")
    assert not ledger.inspect("tenant").allowed
    ledger.release(first)
    assert ledger.inspect("tenant").allowed


def test_quota_start_window_resets_but_preserves_inflight():
    now=[0.0]
    ledger=WorkerQuotaLedger(
        WorkerQuota(max_inflight=2,max_starts_per_window=1,window_seconds=10),
        clock=lambda:now[0],
    )
    first=ledger.reserve("tenant")
    assert not ledger.inspect("tenant").allowed
    now[0]=10
    assert ledger.inspect("tenant").allowed
    assert ledger.usage("tenant").inflight==1
    ledger.release(first)


def test_quota_failure_limit():
    ledger=WorkerQuotaLedger(WorkerQuota(max_failures_per_window=1))
    first=ledger.reserve("tenant")
    ledger.complete(first,ok=False)
    decision=ledger.inspect("tenant")
    assert not decision.allowed
    assert "failure" in decision.reason


def test_quota_output_limit():
    ledger=WorkerQuotaLedger(WorkerQuota(max_output_bytes_per_window=5))
    first=ledger.reserve("tenant")
    ledger.complete(first,ok=True,output_bytes=5)
    assert not ledger.inspect("tenant").allowed


def test_quota_double_complete_rejected():
    ledger=WorkerQuotaLedger()
    reservation=ledger.reserve("tenant")
    ledger.complete(reservation,ok=True)
    with pytest.raises(RuntimeError):
        ledger.complete(reservation,ok=True)


def test_quota_release_does_not_refund_start():
    ledger=WorkerQuotaLedger(WorkerQuota(max_starts_per_window=1))
    reservation=ledger.reserve("tenant")
    ledger.release(reservation)
    assert not ledger.inspect("tenant").allowed


def test_affinity_required_label_filters():
    regs=[
        registration("a",labels={"zone":"x"}),
        registration("b",labels={"zone":"y"}),
    ]
    views={r.identity.worker_id:live(r.identity.worker_id) for r in regs}
    req=JobRequirements(affinity=(AffinityTerm("zone","x",AffinityMode.REQUIRED),))
    decision=WorkerPlacement().evaluate(regs,views,req)
    assert decision.selected.worker_id=="a"
    assert "b" in decision.rejected


def test_affinity_preferred_label_orders():
    regs=[
        registration("a",labels={"zone":"x"}),
        registration("b",labels={"zone":"y"}),
    ]
    views={r.identity.worker_id:live(r.identity.worker_id) for r in regs}
    req=JobRequirements(affinity=(AffinityTerm("zone","y",AffinityMode.PREFERRED,weight=50),))
    assert WorkerPlacement().evaluate(regs,views,req).selected.worker_id=="b"


def test_affinity_avoid_penalizes():
    regs=[registration("a",labels={"spot":"yes"}),registration("b")]
    views={r.identity.worker_id:live(r.identity.worker_id) for r in regs}
    req=JobRequirements(affinity=(AffinityTerm("spot","yes",AffinityMode.AVOID,weight=100),))
    assert WorkerPlacement().evaluate(regs,views,req).selected.worker_id=="b"


def test_affinity_required_role_and_feature():
    regs=[
        registration("a",role=WorkerRole.BUILDER,features={"git"}),
        registration("b",role=WorkerRole.TESTER,features={"git"}),
    ]
    views={r.identity.worker_id:live(r.identity.worker_id) for r in regs}
    req=JobRequirements(required_role=WorkerRole.BUILDER,required_features=frozenset({"git"}))
    assert WorkerPlacement().select(regs,views,req).identity.worker_id=="a"


@pytest.mark.parametrize("state",[WorkerLiveness.UNKNOWN,WorkerLiveness.STALE])
def test_affinity_rejects_nonlive(state):
    reg=registration("a")
    decision=WorkerPlacement().evaluate([reg],{"a":live("a",state=state)})
    assert not decision.placed


def test_affinity_late_allowed_only_when_configured():
    reg=registration("a")
    views={"a":live("a",state=WorkerLiveness.LATE)}
    assert not WorkerPlacement().evaluate([reg],views).placed
    assert WorkerPlacement().evaluate([reg],views,JobRequirements(allow_late_workers=True)).placed


def test_affinity_prefers_lower_inflight_after_equal_affinity():
    regs=[registration("a"),registration("b")]
    views={"a":live("a",inflight=5),"b":live("b",inflight=1)}
    assert WorkerPlacement().evaluate(regs,views).selected.worker_id=="b"


def test_capacity_validates_reserved_bounds():
    with pytest.raises(ValueError):
        WorkerCapacity(max_inflight=1,reserved_inflight=2)


def test_capacity_view_can_fit():
    view=CapacityView("a",1,WorkerCapacity(max_inflight=4,max_weight=10),1,2,WorkerLiveness.HEALTHY)
    assert view.can_fit(CapacityDemand(2,5))
    assert not view.can_fit(CapacityDemand(4,5))


def test_capacity_nonhealthy_cannot_fit():
    view=CapacityView("a",1,WorkerCapacity(max_inflight=4,max_weight=10),0,0,WorkerLiveness.LATE)
    assert not view.can_fit(CapacityDemand())


def test_capacity_catalog_defaults_and_override():
    catalog=WorkerCapacityCatalog(WorkerCapacity(max_inflight=2,max_weight=2))
    assert catalog.get("a").max_inflight==2
    catalog.set("a",WorkerCapacity(max_inflight=5,max_weight=5))
    assert catalog.get("a").max_inflight==5
    assert catalog.remove("a")
    assert catalog.get("a").max_inflight==2

"""Bounded standalone tests for Dragon's shared resource-admission foundation.

This slice has no crawler, provider, UI, hardware probe or background worker.
It verifies that planning is not execution authority and shared grants remain
owned until the actual worker acknowledges stop.
"""
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_resource_session import (
    DragonResourceSession, HardwareSample, SessionTask, plan_resources,
)
from skeleton.kernel.global_resource_scheduler import (
    GlobalResourcePolicy, GlobalResourceScheduler, PlanePolicy, ResourceVector,
)


def hardware(**overrides):
    return replace(HardwareSample(256 * 1024**2, 4, .1, .9, True, False, 10), **overrides)


def ledger():
    return GlobalResourceScheduler(GlobalResourcePolicy(
        ResourceVector(cpu_millis=2000, memory_mb=128, provider_tokens=100),
        (PlanePolicy("interactive", 2, ResourceVector(), 1.0),
         PlanePolicy("background", 1, ResourceVector(), 1.0)),
    ))


@pytest.mark.parametrize(("changes", "reason"), [
    ({"sampled_at": 0}, "stale_telemetry"),
    ({"thermal_limited": True}, "thermal_or_pressure"),
    ({"pressure": .96}, "thermal_or_pressure"),
    ({"available_memory_bytes": 1024}, "memory_reserve"),
])
def test_planning_fails_closed_for_invalid_operating_conditions(changes, reason):
    decision = plan_resources(hardware(**changes), now=10, foreground=True)
    assert decision.effort == "defer"
    assert decision.memory_bytes == 0
    assert decision.reason == reason


@pytest.mark.parametrize(("field", "value"), [
    ("pressure", float("nan")), ("cpu_units", True), ("available_memory_bytes", -1),
    ("charging", 1), ("battery_fraction", 2), ("sampled_at", "now"),
])
def test_bad_hardware_values_are_rejected(field, value):
    with pytest.raises(ValueError):
        hardware(**{field: value})


@pytest.mark.parametrize("now", [None, "now", True, -1, float("nan")])
def test_bad_observation_clock_is_rejected(now):
    with pytest.raises(ValueError):
        plan_resources(hardware(), now=now, foreground=True)


def test_low_battery_denies_idle_but_not_user_work():
    sample = hardware(battery_fraction=.1, charging=False)
    assert not plan_resources(sample, now=10, foreground=False).background_allowed
    assert plan_resources(sample, now=10, foreground=True).memory_bytes > 0


def test_local_plan_never_grants_execution_permission():
    session = DragonResourceSession()
    result = session.dispatch((SessionTask("chat", "user", 1024, 1),), hardware(), now=10)
    assert result.foreground_ready
    assert not result.execution_authorized
    session.stopped("chat")


def test_pending_background_blocks_foreground_until_actual_stop():
    session = DragonResourceSession()
    bg = SessionTask("learn", "acquisition", 16 * 1024**2, 1)
    user = SessionTask("chat", "user", 16 * 1024**2, 2)
    assert session.dispatch((bg,), hardware(), now=10).admitted == ("learn",)
    blocked = session.dispatch((user,), hardware(), now=10)
    assert blocked.checkpoint_requested == ("learn",)
    assert not blocked.foreground_ready
    assert blocked.reason == "draining_background"
    session.stopped("learn")
    assert session.dispatch((user,), hardware(), now=10).foreground_ready
    session.stopped("chat")


def test_atomic_foreground_batch_must_fit_or_admit_nothing():
    session = DragonResourceSession()
    tasks = (SessionTask("chat_a", "user", 1024, 2), SessionTask("chat_b", "user", 1024, 2))
    rejected = session.dispatch(tasks, hardware(), now=10)
    assert rejected.admitted == ()
    assert not rejected.foreground_ready
    accepted = session.dispatch(tasks[:1], hardware(), now=10)
    assert accepted.admitted == ("chat_a",)
    session.stopped("chat_a")


def test_two_tenants_share_reservations_and_release_only_on_stop():
    scheduler = ledger()
    a = DragonResourceSession(global_resources=scheduler, tenant="a")
    b = DragonResourceSession(global_resources=scheduler, tenant="b")
    task = SessionTask("chat", "user", 1024, 2, provider_tokens=80)
    admitted = a.dispatch((task,), hardware(), now=10)
    assert admitted.execution_authorized
    assert scheduler.usage("interactive").provider_tokens == 80
    denied = b.dispatch((task,), hardware(), now=10)
    assert not denied.execution_authorized
    assert not denied.admitted
    a.stopped("chat")
    assert scheduler.usage("interactive").empty
    assert b.dispatch((task,), hardware(), now=10).execution_authorized
    b.stopped("chat")


def test_provider_limit_is_enforced_before_worker_admission():
    scheduler = ledger()
    session = DragonResourceSession(global_resources=scheduler, tenant="a")
    denied = session.dispatch((SessionTask("chat", "user", 1024, 1, provider_tokens=101),), hardware(), now=10)
    assert not denied.execution_authorized
    assert not denied.admitted
    assert scheduler.usage("interactive").empty


def test_global_priority_preserves_user_first():
    scheduler = ledger()
    session = DragonResourceSession(global_resources=scheduler, tenant="a")
    session.dispatch((SessionTask("chat", "user", 1024, 1),), hardware(), now=10)
    assert scheduler.active_grants()[0].priority == 0
    session.stopped("chat")
    session.dispatch((SessionTask("learn", "acquisition", 1024, 1),), hardware(), now=10)
    assert scheduler.active_grants()[0].priority == 6
    session.stopped("learn")

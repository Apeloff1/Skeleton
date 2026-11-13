"""Canonical KV reclamation under measured memory headroom."""
from __future__ import annotations
import pytest
from skeleton.ai.model_runtime.admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError


def _scheduler() -> RuntimeAdmissionScheduler:
    return RuntimeAdmissionScheduler(AdmissionLimits(
        max_active_requests=4, max_queued_requests=16, max_batch_size=4,
        max_tokens_per_batch=1000, kv_capacity_bytes=100,
    ))


def _retain(scheduler: RuntimeAdmissionScheduler, name: str, size: int, *, pinned: bool = False) -> None:
    scheduler.submit(BatchRequest(name, 1, 1, 0), kv_bytes=size, pinned_kv=pinned)
    decision = scheduler.admit()
    assert name in decision.admitted
    scheduler.complete(name, retain_kv=True)


def test_oldest_retained_kv_evicted_first() -> None:
    scheduler = _scheduler()
    _retain(scheduler, "old", 30)
    _retain(scheduler, "new", 30)
    receipt = scheduler.trim_retained_kv(target_bytes=35)
    assert receipt.evicted == ("old",)
    assert receipt.reclaimed_bytes == 30
    assert receipt.resident_bytes == 30
    assert receipt.snapshot_digest == scheduler.snapshot()["digest"]


def test_pinned_kv_is_never_implicitly_reclaimed() -> None:
    scheduler = _scheduler()
    _retain(scheduler, "pinned", 60, pinned=True)
    _retain(scheduler, "free", 20)
    before = scheduler.snapshot()
    with pytest.raises(ModelRuntimeError, match="active or pinned"):
        scheduler.trim_retained_kv(target_bytes=40)
    assert scheduler.snapshot() == before


def test_active_kv_is_never_reclaimed() -> None:
    scheduler = _scheduler()
    scheduler.submit(BatchRequest("active", 1, 1, 0), kv_bytes=80)
    assert scheduler.admit().admitted == ("active",)
    before = scheduler.snapshot()
    with pytest.raises(ModelRuntimeError, match="active or pinned"):
        scheduler.trim_retained_kv(target_bytes=10)
    assert scheduler.snapshot() == before


def test_headroom_reclamation_preserves_explicit_reserve() -> None:
    scheduler = _scheduler()
    _retain(scheduler, "one", 30)
    _retain(scheduler, "two", 30)
    receipt = scheduler.reclaim_for_headroom(available_memory_bytes=50, reserve_bytes=20)
    assert receipt.target_bytes == 30
    assert receipt.resident_bytes == 30
    assert receipt.evicted == ("one",)


def test_repeated_reclamation_is_idempotent() -> None:
    scheduler = _scheduler()
    _retain(scheduler, "one", 30)
    first = scheduler.trim_retained_kv(target_bytes=30)
    snapshot = scheduler.snapshot()
    second = scheduler.trim_retained_kv(target_bytes=30)
    assert first.evicted == second.evicted == ()
    assert scheduler.snapshot() == snapshot


@pytest.mark.parametrize("target", [True, -1, 101, 1.5])
def test_invalid_reclamation_target_does_not_mutate(target: object) -> None:
    scheduler = _scheduler()
    _retain(scheduler, "one", 30)
    before = scheduler.snapshot()
    with pytest.raises(ModelRuntimeError):
        scheduler.trim_retained_kv(target_bytes=target)
    assert scheduler.snapshot() == before


@pytest.mark.parametrize("available,reserve", [(None, 0), (10, -1), (True, 0), (10, True)])
def test_unknown_or_invalid_headroom_is_not_zero(available: object, reserve: object) -> None:
    scheduler = _scheduler()
    with pytest.raises(ModelRuntimeError):
        scheduler.reclaim_for_headroom(available_memory_bytes=available, reserve_bytes=reserve)

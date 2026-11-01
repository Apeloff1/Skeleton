"""Per-token CPU pressure guard regressions with deterministic OS probe doubles."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget
from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
from skeleton.ai.model_runtime import native_token_pressure as pressure_module
from skeleton.ai.model_runtime.native_token_pressure import (
    NativePressureInterrupted, NativeTokenPressureGuard,
)

P = DispatchPermit(
    lease_id="b" * 64, request_id="r", generation=1,
    checkpoint_digest="c" * 64, tokens=2, bytes_reserved=32,
)


def budget(*, tokens=2, slots=1, ram=4096, pressure=0):
    return MeasuredStreamBudget(
        available_ram_bytes=ram, reserved_ram_bytes=0,
        token_budget=tokens, stream_slots=slots,
        pressure_ppm=pressure, thermal_hold=False, measurement="os_probe",
    )


def probe(monkeypatch, readings):
    iterator = iter(readings)

    def sample(self, *, token_budget, storage_path):
        item = next(iterator)
        if isinstance(item, BaseException):
            raise item
        return item, {
            "measurement": "os_probe",
            "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
        }
    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)


def test_pressure_healthy_callbacks_preserve_single_flight(monkeypatch):
    probe(monkeypatch, [budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    interrupt = guard.start(P)
    interrupt()
    interrupt()
    assert guard.status().samples == 2
    assert not guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)
    guard.finish(success=True)
    assert not guard.status().stopped


def test_pressure_rise_aborts_and_remains_stopped(monkeypatch):
    probe(monkeypatch, [budget(), budget(slots=0)])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    interrupt = guard.start(P)
    interrupt()
    with pytest.raises(NativePressureInterrupted, match="pressure hold"):
        interrupt()
    assert guard.status().stopped
    guard.finish(success=False)
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_missing_telemetry_fails_closed(monkeypatch):
    probe(monkeypatch, [OSError("unavailable")])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="unavailable"):
        guard.start(P)()
    assert guard.status().stopped


def test_probe_count_is_hard_bound(monkeypatch):
    probe(monkeypatch, [budget()])
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_probes=1,
    )
    interrupt = guard.start(P)
    interrupt()
    with pytest.raises(NativePressureInterrupted, match="probe budget"):
        interrupt()
    assert guard.status().samples == 1


def test_unqualified_permit_denied_before_sampling():
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="CPU-only"):
        guard.start(replace(P, device_qualified=True))


@pytest.mark.parametrize("limit", [0, True, 4097])
def test_probe_budget_validation(limit):
    with pytest.raises(ValueError, match="probe count"):
        NativeTokenPressureGuard(
            LiveStreamBudgetSampler(), storage_path=".", max_probes=limit,
        )


def test_unobserved_success_cannot_reset_guard_to_available():
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    guard.start(P)
    with pytest.raises(NativePressureInterrupted, match="unverified"):
        guard.finish(success=True)
    assert guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_one_callback_is_not_proof_of_postflight_and_model_probes(monkeypatch):
    probe(monkeypatch, [budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    interrupt = guard.start(P)
    interrupt()
    with pytest.raises(NativePressureInterrupted, match="unverified"):
        guard.finish(success=True)
    assert guard.status().stopped


def test_monotonic_deadline_interrupts_before_another_token(monkeypatch):
    probe(monkeypatch, [budget()])
    clock = iter((0, 100, 200, 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    callback = guard.start(P)
    callback()
    with pytest.raises(NativePressureInterrupted, match="deadline"):
        callback()
    assert guard.status().samples == 1
    assert guard.status().stopped
    guard.finish(success=False)


def test_probe_time_counts_toward_execution_deadline(monkeypatch):
    probe(monkeypatch, [budget()])
    clock = iter((0, 10, 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    with pytest.raises(NativePressureInterrupted, match="deadline"):
        guard.start(P)()
    assert guard.status().samples == 1
    assert guard.status().stopped


def test_clock_regression_quarantines_active_native_lease(monkeypatch):
    clock = iter((1000, 999))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="regressed"):
        guard.start(P)()
    assert guard.status().stopped


def test_deadline_expiry_at_finish_cannot_certify_success(monkeypatch):
    probe(monkeypatch, [budget(), budget()])
    clock = iter((0, 10, 20, 30, 40, 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    callback = guard.start(P)
    callback()
    callback()
    with pytest.raises(NativePressureInterrupted, match="deadline"):
        guard.finish(success=True)
    assert guard.status().samples == 2
    assert guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_monotonic_clock_failure_at_start_is_fail_closed(monkeypatch):
    def broken_clock():
        raise OSError("clock failed")
    monkeypatch.setattr(pressure_module, "monotonic_ns", broken_clock)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="unavailable"):
        guard.start(P)
    assert guard.status().stopped


@pytest.mark.parametrize("duration", [0, True, 999_999, 86_400_000_000_001])
def test_native_execution_duration_must_be_bounded(duration):
    with pytest.raises(ValueError, match="duration"):
        NativeTokenPressureGuard(
            LiveStreamBudgetSampler(), storage_path=".",
            max_duration_ns=duration,
        )


def test_native_pressure_guard_burns_successful_lease_and_fences_old_callback(monkeypatch):
    probe(monkeypatch, [budget(), budget(), budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    old_callback = guard.start(P)
    old_callback()
    old_callback()
    guard.finish(success=True)
    with pytest.raises(NativePressureInterrupted, match="replay"):
        guard.start(P)
    assert guard.status().stopped


def test_native_pressure_old_callback_cannot_sample_new_lease(monkeypatch):
    probe(monkeypatch, [budget(), budget(), budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    old_callback = guard.start(P)
    old_callback()
    old_callback()
    guard.finish(success=True)
    new_permit = replace(P, lease_id="d" * 64, request_id="next")
    new_callback = guard.start(new_permit)
    with pytest.raises(NativePressureInterrupted, match="no longer active"):
        old_callback()
    assert guard.status().samples == 0
    new_callback()
    new_callback()
    guard.finish(success=True)
    assert not guard.status().stopped


@pytest.mark.parametrize("field,value", [
    ("tokens", True), ("generation", True), ("bytes_reserved", True),
    ("lease_id", "not-hex"), ("checkpoint_digest", "x" * 64),
    ("request_id", "\\ud800"),
])
def test_native_pressure_rejects_forged_permit_types_without_sampling(field, value):
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="canonical typed permit"):
        guard.start(replace(P, **{field: value}))
    assert guard.status().samples == 0


def test_native_pressure_guard_lifetime_capacity_is_bounded(monkeypatch):
    monkeypatch.setattr(pressure_module, "MAX_USED_LEASES", 1)
    probe(monkeypatch, [budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    callback = guard.start(P)
    callback()
    callback()
    guard.finish(success=True)
    with pytest.raises(NativePressureInterrupted, match="capacity"):
        guard.start(replace(P, lease_id="e" * 64, request_id="next"))
    assert guard.status().stopped

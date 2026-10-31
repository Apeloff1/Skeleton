"""Per-token CPU pressure guard regressions with deterministic OS probe doubles."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget
from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
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

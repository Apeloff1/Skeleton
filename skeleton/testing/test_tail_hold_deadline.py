"""Conservative bounded HOLD lifetime for cooperative local CPU inference."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.model_runtime.tail_inflight_guard import (
    InFlightCPUResourceGuard, InFlightPressureDenied, InFlightPressurePolicy,
)
from skeleton.app.offline_cpu_thermal import CPUThermalSensor
from skeleton.app.offline_resources import LocalResourceSnapshot


def policy():
    return InFlightPressurePolicy(
        min_ram_bytes=1024, min_disk_bytes=1024,
        max_cpu_load_ppm=900_000, max_memory_pressure_ppm=900_000,
        max_generated_tokens=64, resume_good_samples=2,
        max_hold_duration_ns=100,
    )


def resources(*, available=4096):
    return LocalResourceSnapshot(
        total_ram_bytes=8192, available_ram_bytes=available,
        total_disk_bytes=8192, free_disk_bytes=4096,
        cpu_count=2, cpu_load_ratio=0.1,
        total_swap_bytes=1024, free_swap_bytes=1024,
        memory_pressure_ratio=0.1,
    )


def thermal():
    return (CPUThermalSensor("cpu", "cpu", 45.0, 90.0),)


def make(clock, resource=None):
    return InFlightCPUResourceGuard(
        policy(), storage_path=".", simulated=True,
        resource_probe=resource or (lambda _: resources(available=1)),
        thermal_probe=thermal, clock=clock,
    )


def test_hold_expires_irreversibly_even_if_resources_recover():
    ticks = iter((100, 201))
    guard = make(lambda: next(ticks))
    assert guard.start().state == "hold"
    with pytest.raises(InFlightPressureDenied, match="hold_deadline_exceeded"):
        guard.resume()
    assert guard.status().state == "aborted"
    assert guard.status().authorized_quantum_tokens == 0
    with pytest.raises(InFlightPressureDenied):
        guard.start()


def test_status_fences_stale_hold_without_resume():
    ticks = iter((100, 201))
    guard = make(lambda: next(ticks))
    guard.start()
    with pytest.raises(InFlightPressureDenied, match="hold_deadline_exceeded"):
        guard.status()
    assert guard.status().state == "aborted"


def test_repeated_unhealthy_samples_do_not_reset_original_hold_deadline():
    ticks = iter((100, 150, 175, 201))
    guard = make(lambda: next(ticks))
    assert guard.start().state == "hold"
    assert guard.resume().state == "hold"
    with pytest.raises(InFlightPressureDenied, match="hold_deadline_exceeded"):
        guard.resume()
    assert guard.status().state == "aborted"


def test_successful_hysteresis_clears_hold_deadline():
    ticks = iter((100, 150, 175, 180))
    calls = 0

    def resource(_):
        nonlocal calls
        calls += 1
        return resources(available=1 if calls == 1 else 4096)

    guard = make(lambda: next(ticks), resource)
    assert guard.start().state == "hold"
    assert guard.resume().state == "hold"
    assert guard.resume().state == "running"
    assert guard.status().state == "running"


def test_clock_regression_during_hold_aborts_without_replay():
    ticks = iter((200, 199))
    guard = make(lambda: next(ticks))
    guard.start()
    with pytest.raises(InFlightPressureDenied, match="monotonic_clock_unavailable"):
        guard.resume()
    assert guard.status().state == "aborted"


@pytest.mark.parametrize("invalid", [0, -1, True, 3_600_000_000_001])
def test_invalid_hold_policy_denied(invalid):
    with pytest.raises(ValueError, match="bounded token or hysteresis"):
        replace(policy(), max_hold_duration_ns=invalid)

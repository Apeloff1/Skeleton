"""Deterministic CPU in-flight pressure and thermal hold regressions."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.model_runtime.tail_inflight_guard import (
    InFlightCPUResourceGuard, InFlightPressureDenied,
    InFlightPressurePolicy,
)
from skeleton.app.offline_cpu_thermal import CPUThermalSensor
from skeleton.app.offline_resources import LocalResourceSnapshot


def policy():
    return InFlightPressurePolicy(
        min_ram_bytes=256 << 20, min_disk_bytes=512 << 20,
        max_cpu_load_ppm=850_000, max_memory_pressure_ppm=750_000,
        max_generated_tokens=512, max_quantum_tokens=64,
        resume_good_samples=2,
    )


def snapshot(**changes):
    data = {
        "total_ram_bytes": 8 << 30,
        "available_ram_bytes": 4 << 30,
        "total_disk_bytes": 100 << 30,
        "free_disk_bytes": 50 << 30,
        "cpu_count": 8,
        "cpu_load_ratio": 0.2,
        "total_swap_bytes": 2 << 30,
        "free_swap_bytes": 2 << 30,
        "memory_pressure_ratio": 0.1,
    }
    data.update(changes)
    return LocalResourceSnapshot(**data)


def healthy_thermal():
    return (CPUThermalSensor("thermal_zone0", "cpu", 50.0, 90.0),)


def guard(resource=None, thermal=None, **options):
    return InFlightCPUResourceGuard(
        policy(), storage_path=".", simulated=True,
        resource_probe=resource or (lambda path: snapshot()),
        thermal_probe=thermal or healthy_thermal, **options,
    )


def test_simulated_probe_never_grants_production_execution():
    g = guard()
    decision = g.start()
    assert decision.state == "running"
    assert decision.continue_execution is False
    assert decision.gpu_device_qualified is False
    assert g.checkpoint(generated_tokens=32).generated_tokens == 32
    assert g.complete().state == "completed"
    with pytest.raises(InFlightPressureDenied):
        g.start()


def test_unknown_thermal_is_a_hold_not_qualification():
    g = guard(thermal=lambda: ())
    d = g.start()
    assert d.state == "hold" and not d.continue_execution
    assert d.reason == "unknown_thermal_trip"
    with pytest.raises(InFlightPressureDenied):
        g.checkpoint(generated_tokens=1)


def test_measured_trip_forces_hold():
    g = guard(thermal=lambda: (
        CPUThermalSensor("thermal_zone0", "cpu", 92.0, 90.0),
    ))
    d = g.start()
    assert d.reason == "measured_thermal_hold"
    assert d.state == "hold"


def test_ram_collapse_during_stream_pauses():
    calls = 0

    def resources(path):
        nonlocal calls
        calls += 1
        return snapshot() if calls == 1 else snapshot(available_ram_bytes=1)

    g = guard(resource=resources)
    assert g.start().state == "running"
    decision = g.checkpoint(generated_tokens=16)
    assert decision.state == "hold"
    assert decision.reason == "memory_or_disk_pressure"
    assert decision.generated_tokens == 16


def test_resume_requires_multiple_fresh_good_samples():
    calls = 0

    def resources(path):
        nonlocal calls
        calls += 1
        return snapshot(available_ram_bytes=1) if calls == 1 else snapshot()

    g = guard(resource=resources)
    assert g.start().state == "hold"
    assert g.resume().state == "hold"
    assert g.resume().state == "running"
    assert g.checkpoint(generated_tokens=10).state == "running"


def test_unknown_telemetry_resets_resume_hysteresis():
    calls = 0

    def resources(path):
        nonlocal calls
        calls += 1
        if calls == 1 or calls == 3:
            raise OSError("simulated telemetry outage")
        return snapshot()

    g = guard(resource=resources)
    assert g.start().state == "hold"
    assert g.resume().state == "hold"
    assert g.resume().state == "hold"
    assert g.resume().state == "hold"
    assert g.resume().state == "running"


@pytest.mark.parametrize("changes,reason", [
    ({"free_disk_bytes": 1}, "memory_or_disk_pressure"),
    ({"cpu_load_ratio": 0.99}, "cpu_or_memory_pressure"),
    ({"memory_pressure_ratio": 0.99}, "cpu_or_memory_pressure"),
    ({"free_swap_bytes": 0}, "swap_exhaustion"),
])
def test_resource_pressure_fails_closed(changes, reason):
    g = guard(resource=lambda path: snapshot(**changes))
    d = g.start()
    assert d.state == "hold" and d.reason == reason


def test_token_budget_aborts_irreversibly():
    g = InFlightCPUResourceGuard(
        replace(policy(), max_generated_tokens=32),
        storage_path=".", simulated=True,
        resource_probe=lambda path: snapshot(),
        thermal_probe=healthy_thermal,
    )
    assert g.start().state == "running"
    d = g.checkpoint(generated_tokens=33)
    assert d.state == "aborted" and d.reason == "token_budget_exhausted"
    with pytest.raises(InFlightPressureDenied):
        g.resume()


def test_abort_is_terminal_and_payload_free():
    g = guard()
    assert g.start().state == "running"
    d = g.abort()
    assert d.state == "aborted" and d.generated_tokens == 0
    assert not hasattr(d, "prompt")
    with pytest.raises(InFlightPressureDenied):
        g.complete()


def test_complete_reprobes_and_denies_late_pressure():
    calls = 0

    def resources(path):
        nonlocal calls
        calls += 1
        return snapshot() if calls == 1 else snapshot(cpu_load_ratio=1.0)

    g = guard(resource=resources)
    assert g.start().state == "running"
    assert g.complete().state == "hold"


def test_injected_probe_requires_simulation():
    with pytest.raises(ValueError, match="simulation"):
        InFlightCPUResourceGuard(
            policy(), storage_path=".", resource_probe=lambda path: snapshot(),
        )


@pytest.mark.parametrize("bad", [True, -1, 65, 4096])
def test_bad_quantum_rejected_without_mutation(bad):
    g = guard()
    g.start()
    before = g.status()
    with pytest.raises(ValueError, match="quantum"):
        g.checkpoint(generated_tokens=bad)
    assert g.status() == before


def test_unknown_resource_snapshot_is_not_trusted():
    g = guard(resource=lambda path: object())
    assert g.start().reason == "unknown_resource_telemetry"


def test_no_restart_state_is_implicitly_reconstructed():
    old = guard()
    old.start()
    old.checkpoint(generated_tokens=12)
    fresh = guard()
    assert fresh.status().state == "new"
    assert fresh.status().generated_tokens == 0


def test_quantum_admission_clamps_to_remaining_budget_and_prevents_overrun():
    g = InFlightCPUResourceGuard(
        replace(policy(), max_generated_tokens=70),
        storage_path=".", simulated=True,
        resource_probe=lambda path: snapshot(),
        thermal_probe=healthy_thermal,
    )
    assert g.start().authorized_quantum_tokens == 0
    first = g.admit_quantum(requested_tokens=64)
    assert first.authorized_quantum_tokens == 64
    assert not first.continue_execution  # simulation never authorizes a device
    with pytest.raises(InFlightPressureDenied, match="previous quantum"):
        g.admit_quantum(requested_tokens=1)
    assert g.checkpoint(generated_tokens=64).generated_tokens == 64
    last = g.admit_quantum(requested_tokens=64)
    assert last.authorized_quantum_tokens == 6
    with pytest.raises(InFlightPressureDenied, match="unaccounted"):
        g.checkpoint(generated_tokens=7)
    assert g.status().state == "aborted"
    assert g.status().authorized_quantum_tokens == 0


def test_outstanding_quantum_blocks_completion_until_accounted():
    g = guard()
    g.start()
    g.admit_quantum(requested_tokens=8)
    with pytest.raises(InFlightPressureDenied, match="outstanding"):
        g.complete()
    assert g.checkpoint(generated_tokens=5).generated_tokens == 5
    assert g.complete().state == "completed"


def test_fresh_quantum_probe_holds_when_memory_collapses():
    readings = iter((snapshot(), snapshot(available_ram_bytes=1)))
    g = guard(resource=lambda path: next(readings))
    assert g.start().state == "running"
    d = g.admit_quantum(requested_tokens=8)
    assert d.state == "hold"
    assert d.authorized_quantum_tokens == 0
    assert not d.continue_execution


@pytest.mark.parametrize("bad", [True, 0, -1, 4097])
def test_bad_requested_quantum_cannot_mutate_state(bad):
    g = guard()
    g.start()
    before = g.status()
    with pytest.raises(ValueError, match="requested token quantum"):
        g.admit_quantum(requested_tokens=bad)
    assert g.status() == before


def test_quantum_deadline_fences_unaccounted_inference_without_replay():
    ticks = iter((100, 151))
    g = InFlightCPUResourceGuard(
        replace(policy(), max_quantum_duration_ns=50),
        storage_path=".", simulated=True,
        resource_probe=lambda path: snapshot(),
        thermal_probe=healthy_thermal,
        clock=lambda: next(ticks),
    )
    g.start()
    assert g.admit_quantum(requested_tokens=8).authorized_quantum_tokens == 8
    with pytest.raises(InFlightPressureDenied, match="quantum_deadline_exceeded"):
        g.checkpoint(generated_tokens=8)
    assert g.status().state == "aborted"
    assert g.status().generated_tokens == 0
    assert g.status().authorized_quantum_tokens == 0
    with pytest.raises(InFlightPressureDenied):
        g.resume()


def test_status_does_not_report_expired_quantum_as_authorized():
    ticks = iter((100, 101, 300))
    g = InFlightCPUResourceGuard(
        replace(policy(), max_quantum_duration_ns=50),
        storage_path=".", simulated=True,
        resource_probe=lambda path: snapshot(),
        thermal_probe=healthy_thermal,
        clock=lambda: next(ticks),
    )
    g.start()
    g.admit_quantum(requested_tokens=2)
    assert g.status().authorized_quantum_tokens == 2
    with pytest.raises(InFlightPressureDenied, match="quantum_deadline_exceeded"):
        g.status()
    assert g.status().state == "aborted"


def test_clock_regression_aborts_quantum_fail_closed():
    ticks = iter((200, 199))
    g = InFlightCPUResourceGuard(
        policy(), storage_path=".", simulated=True,
        resource_probe=lambda path: snapshot(),
        thermal_probe=healthy_thermal,
        clock=lambda: next(ticks),
    )
    g.start()
    g.admit_quantum(requested_tokens=1)
    with pytest.raises(InFlightPressureDenied, match="monotonic_clock_unavailable"):
        g.checkpoint(generated_tokens=1)
    assert g.status().state == "aborted"
    assert g.status().authorized_quantum_tokens == 0


def test_injected_clock_requires_simulation_and_policy_is_bounded():
    with pytest.raises(ValueError, match="simulation"):
        InFlightCPUResourceGuard(
            policy(), storage_path=".", clock=lambda: 1,
        )
    for invalid in (True, 0, -1, 30_000_000_001):
        with pytest.raises(ValueError, match="bounded token or hysteresis"):
            replace(policy(), max_quantum_duration_ns=invalid)

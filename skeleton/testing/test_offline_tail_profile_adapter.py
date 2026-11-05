"""Synthetic probe-bound regressions for the canonical offline tail adapter.

No test claims that simulated sensors qualify a real CPU, GPU or thermal trip.
"""
from __future__ import annotations

import pytest

import skeleton.app.offline_tail_profile_adapter as adapter
from skeleton.app.offline_cpu_thermal import CPUThermalSensor
from skeleton.app.offline_resource_fabric import GPUResource
from skeleton.app.offline_resources import LocalResourcePressure, LocalResourceSnapshot
from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming
from skeleton.ai.model_runtime.tail_latency_profile import LocalTailProfiler, ProfileIdentity


def identity() -> ProfileIdentity:
    return ProfileIdentity(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 40,
        "native", "simulated-cpu", "simulated",
    )


def snapshot() -> LocalResourceSnapshot:
    return LocalResourceSnapshot(
        total_ram_bytes=1 << 30,
        available_ram_bytes=1 << 29,
        total_disk_bytes=1 << 40,
        free_disk_bytes=1 << 39,
        cpu_count=4,
        cpu_load_ratio=0.25,
        total_swap_bytes=1 << 30,
        free_swap_bytes=1 << 29,
        memory_pressure_ratio=0.1,
    )


def timing() -> ExecutionTiming:
    return ExecutionTiming("r1", 0, 1_000_000, 11_000_000, 10, 20, 5)


def thermal(*, temperature: float = 40, trip: float | None = 80):
    return {
        "schema": "skeleton.offline.cpu-thermal.v1",
        "measured": True,
        "trip_measured": trip is not None,
        "thermal_backpressure": trip is not None and temperature >= trip,
        "transitions": 0,
        "sensors": [{
            "zone": "cpu", "kind": "package",
            "temperature_c": temperature, "trip_c": trip,
        }],
    }


def test_live_adapter_reports_canonical_ram_and_thermal(monkeypatch) -> None:
    monkeypatch.setattr(adapter, "probe_local_resources", lambda path: snapshot())
    monkeypatch.setattr(
        adapter, "probe_cpu_thermal",
        lambda: (CPUThermalSensor("cpu", "package", 40, 80),),
    )
    profiler = LocalTailProfiler(identity())
    receipt = adapter.LocalTailObservationCapture(profiler).capture(timing())
    assert receipt.request_id == "r1"
    assert receipt.ram_available_bytes == 1 << 29
    assert receipt.thermal_measured
    assert not receipt.gpu_measured
    assert receipt.profile_checkpoint_digest == profiler.checkpoint()["digest"]
    assert profiler.checkpoint()["records"][0]["resource"]["thermal"] == "measured_ok"


def test_unavailable_thermal_is_not_measured_ok() -> None:
    result = adapter._from_observations(snapshot(), thermal(trip=None), None)
    assert result.thermal == "unavailable"


def test_thermal_trip_produces_explicit_hold() -> None:
    result = adapter._from_observations(snapshot(), thermal(temperature=90, trip=80), None)
    assert result.thermal == "measured_hold"


def test_nvml_dedicated_vram_does_not_count_shared_ram_twice() -> None:
    gpu = GPUResource(
        "nvidia0", "nvidia", 1 << 30, 1 << 29,
        measurement="nvml", temperature_c=40, thermal_limit_c=80,
    )
    result = adapter._from_observations(snapshot(), thermal(), gpu)
    assert result.gpu_free_bytes == 1 << 29
    assert result.gpu_total_bytes == 1 << 30


def test_drm_dedicated_vram_is_separate_from_host_backed_gtt() -> None:
    gpu = GPUResource(
        "card0", "drm", 1 << 30, 1 << 29,
        shared_total_bytes=1 << 30, shared_free_bytes=1 << 29,
        shared_with_system_ram=True, measurement="linux_drm_sysfs",
    )
    result = adapter._from_observations(snapshot(), thermal(), gpu)
    assert result.gpu_free_bytes == 1 << 29
    assert result.gpu_total_bytes == 1 << 30


def test_metal_unified_working_set_is_not_free_vram() -> None:
    gpu = GPUResource(
        "Apple Silicon Metal", "apple", 0, 0,
        shared_with_system_ram=True, measurement="metal_unified_working_set",
        recommended_working_set_bytes=1 << 30, current_allocated_bytes=1 << 29,
    )
    result = adapter._from_observations(snapshot(), thermal(), gpu)
    assert result.gpu_free_bytes is None
    assert result.gpu_total_bytes is None


def test_ambiguous_gpu_identity_fails_without_record(monkeypatch) -> None:
    monkeypatch.setattr(adapter, "probe_local_resources", lambda path: snapshot())
    monkeypatch.setattr(adapter, "probe_cpu_thermal", lambda: ())
    gpu = GPUResource("same", "nvidia", 100, 50, measurement="nvml")
    monkeypatch.setattr(adapter, "probe_gpu_resources", lambda: (gpu, gpu))
    profiler = LocalTailProfiler(identity())
    capture = adapter.LocalTailObservationCapture(profiler, gpu_device="same")
    with pytest.raises(ValueError, match="ambiguous"):
        capture.capture(timing())
    assert profiler.checkpoint()["records"] == []


def test_unavailable_os_resource_probe_fails_closed(monkeypatch) -> None:
    def unavailable(_path):
        raise LocalResourcePressure("cannot measure RAM")
    monkeypatch.setattr(adapter, "probe_local_resources", unavailable)
    profiler = LocalTailProfiler(identity())
    capture = adapter.LocalTailObservationCapture(profiler)
    with pytest.raises(LocalResourcePressure):
        capture.capture(timing())
    assert profiler.checkpoint()["records"] == []


def test_unselected_gpu_is_not_inferred_from_other_devices(monkeypatch) -> None:
    monkeypatch.setattr(adapter, "probe_local_resources", lambda path: snapshot())
    monkeypatch.setattr(adapter, "probe_cpu_thermal", lambda: ())
    gpu = GPUResource("other", "nvidia", 100, 50, measurement="nvml")
    monkeypatch.setattr(adapter, "probe_gpu_resources", lambda: (gpu,))
    profiler = LocalTailProfiler(identity())
    receipt = adapter.LocalTailObservationCapture(
        profiler, gpu_device="missing",
    ).capture(timing())
    assert not receipt.gpu_measured

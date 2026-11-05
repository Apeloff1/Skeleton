"""Canonical offline-app adapter for measured local model timing profiles.

Resource readings are captured after the timed execution. They do not imply
kernel allocation ownership, GPU coherency or time-aligned peak memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming
from skeleton.ai.model_runtime.tail_latency_profile import (
    LocalTailProfiler, ResourceObservation,
)

from .offline_cpu_thermal import CPUThermalController, probe_cpu_thermal
from .offline_resource_fabric import GPUResource, probe_gpu_resources
from .offline_resources import LocalResourceSnapshot, probe_local_resources


@dataclass(frozen=True, slots=True)
class CapturedResourceReceipt:
    request_id: str
    ram_available_bytes: int
    gpu_measured: bool
    thermal_measured: bool
    profile_checkpoint_digest: str


def _from_observations(
    snapshot: LocalResourceSnapshot,
    thermal: dict[str, object],
    gpu: GPUResource | None,
) -> ResourceObservation:
    if not isinstance(snapshot, LocalResourceSnapshot):
        raise ValueError("canonical local resource snapshot required")
    if type(thermal) is not dict or set(thermal) != {
        "schema", "measured", "trip_measured", "thermal_backpressure",
        "transitions", "sensors",
    }:
        raise ValueError("invalid canonical thermal snapshot")
    if thermal["schema"] != "skeleton.offline.cpu-thermal.v1":
        raise ValueError("unexpected thermal schema")
    if type(thermal["trip_measured"]) is not bool or type(thermal["thermal_backpressure"]) is not bool:
        raise ValueError("invalid thermal telemetry")
    if gpu is not None and not isinstance(gpu, GPUResource):
        raise ValueError("canonical GPUResource required")
    gpu_trip = (
        gpu is not None and gpu.temperature_c is not None
        and gpu.thermal_limit_c is not None
    )
    gpu_hold = bool(gpu is not None and gpu.thermal_throttled)
    hold = thermal["thermal_backpressure"] or gpu_hold
    measured = thermal["trip_measured"] or gpu_trip
    thermal_state = (
        "measured_hold" if hold else "measured_ok" if measured else "unavailable"
    )
    # UMA/GTT memory is host-backed, not a second independent VRAM pool.
    # The Metal recommended working set is advisory, not free VRAM.
    dedicated = (
        gpu is not None and gpu.measurement in {"nvml", "linux_drm_sysfs"}
        and gpu.dedicated_total_bytes > 0
    )
    return ResourceObservation(
        ram_available_bytes=snapshot.available_ram_bytes,
        ram_total_bytes=snapshot.total_ram_bytes,
        swap_free_bytes=snapshot.free_swap_bytes,
        swap_total_bytes=snapshot.total_swap_bytes,
        cpu_load_ppm=min(1_000_000, max(0, int(snapshot.cpu_load_ratio * 1_000_000))),
        thermal=thermal_state,
        gpu_free_bytes=gpu.dedicated_free_bytes if dedicated else None,
        gpu_total_bytes=gpu.dedicated_total_bytes if dedicated else None,
    )


class LocalTailObservationCapture:
    """Bind real app probes to the model runtime's canonical profile window.

    The caller must use a trusted ExecutionTiming from actual model execution.
    The profiler's identity remains operator-owned and immutable. This adapter
    does not invoke inference or read prompt/model payloads.
    """

    def __init__(
        self,
        profiler: LocalTailProfiler,
        *,
        storage_path: str | Path = ".",
        gpu_device: str | None = None,
    ) -> None:
        if not isinstance(profiler, LocalTailProfiler):
            raise ValueError("LocalTailProfiler required")
        if gpu_device is not None and (type(gpu_device) is not str or not gpu_device):
            raise ValueError("gpu_device must be a nonempty identity")
        self.profiler = profiler
        self.storage_path = storage_path
        self.gpu_device = gpu_device

    def capture(self, timing: ExecutionTiming) -> CapturedResourceReceipt:
        if not isinstance(timing, ExecutionTiming):
            raise ValueError("canonical ExecutionTiming required")
        # No record is admitted if the host probe fails. Unknown GPU is
        # reported as unknown rather than silently promoted to free VRAM.
        snapshot = probe_local_resources(self.storage_path)
        controller = CPUThermalController()
        controller.observe(probe_cpu_thermal())
        thermal = controller.snapshot()
        gpu = None
        if self.gpu_device is not None:
            devices = probe_gpu_resources()
            matches = [device for device in devices if device.device == self.gpu_device]
            if len(matches) > 1:
                raise ValueError("ambiguous GPU identity")
            if matches:
                gpu = matches[0]
        observation = _from_observations(snapshot, thermal, gpu)
        self.profiler.record(timing, observation)
        return CapturedResourceReceipt(
            timing.request_id, observation.ram_available_bytes,
            observation.gpu_free_bytes is not None,
            observation.thermal != "unavailable",
            str(self.profiler.checkpoint()["digest"]),
        )


__all__ = [
    "CapturedResourceReceipt", "LocalTailObservationCapture",
]

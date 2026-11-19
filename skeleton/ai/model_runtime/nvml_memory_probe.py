"""Linux NVML memory telemetry for canonical local-model device placement.

No CUDA context, hosted provider, model activation or vendor Python SDK is used.
A failed probe is unknown, never a fabricated device with zero load.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import sys
from typing import Any

from .flgb_model_runtime import DeviceDescriptor, MAX_DEVICES


class NVMLProbeError(ValueError):
    """A native probe returned inconsistent or untrusted device telemetry."""


class _MemoryInfo(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_uint64),
        ("free", ctypes.c_uint64),
        ("used", ctypes.c_uint64),
    ]


@dataclass(frozen=True, slots=True)
class GpuMemoryObservation:
    """One observed NVML ordinal, including devices with zero headroom.

    Ordinals are probe-local identity, not stable CUDA runtime identifiers.
    No allocation, MIG partition, device visibility or loader equivalence is
    inferred from this row.
    """
    device_id: str
    total_bytes: int
    free_bytes: int
    used_bytes: int

    def __post_init__(self) -> None:
        if (type(self.device_id) is not str or not self.device_id
                or len(self.device_id) > 256
                or any(ord(ch) < 32 for ch in self.device_id)):
            raise NVMLProbeError("invalid measured device identity")
        if any(type(value) is not int or not 0 <= value < 1 << 63
               for value in (self.total_bytes, self.free_bytes, self.used_bytes)):
            raise NVMLProbeError("invalid per-device GPU memory")
        if not self.total_bytes or self.free_bytes + self.used_bytes > self.total_bytes:
            raise NVMLProbeError("inconsistent per-device GPU memory")


@dataclass(frozen=True, slots=True)
class NativeGpuMemoryReceipt:
    source: str
    status: str
    devices: tuple[DeviceDescriptor, ...]
    measured_total_bytes: int
    measured_free_bytes: int
    observations: tuple[GpuMemoryObservation, ...] = ()

    def __post_init__(self) -> None:
        if self.source not in {"linux_nvml", "unavailable", "simulated_nvml"}:
            raise NVMLProbeError("unknown native probe source")
        if self.status not in {"measured", "unavailable"}:
            raise NVMLProbeError("invalid native probe status")
        if self.status == "unavailable":
            if self.source != "unavailable" or self.devices:
                raise NVMLProbeError("unavailable GPU probe cannot publish measured provenance or devices")
            if self.measured_total_bytes != 0 or self.measured_free_bytes != 0:
                raise NVMLProbeError("unavailable GPU probe cannot publish measured memory")
        elif self.source == "unavailable":
            raise NVMLProbeError("measured GPU probe requires measured provenance")
        for value in (self.measured_total_bytes, self.measured_free_bytes):
            if type(value) is not int or value < 0 or value >= 1 << 63:
                raise NVMLProbeError("invalid aggregate GPU memory")
        if self.measured_free_bytes > self.measured_total_bytes:
            raise NVMLProbeError("free GPU memory exceeds physical total")
        if type(self.observations) is not tuple or len(self.observations) > MAX_DEVICES or any(
            not isinstance(row, GpuMemoryObservation) for row in self.observations
        ):
            raise NVMLProbeError("invalid per-device observation set")
        if self.observations:
            if self.status != "measured":
                raise NVMLProbeError("unavailable probe cannot carry device observations")
            ids = {row.device_id for row in self.observations}
            if len(ids) != len(self.observations):
                raise NVMLProbeError("duplicate measured device identity")
            if (sum(row.total_bytes for row in self.observations) != self.measured_total_bytes
                    or sum(row.free_bytes for row in self.observations) != self.measured_free_bytes):
                raise NVMLProbeError("per-device observations disagree with aggregate memory")
            expected = {row.device_id: row.free_bytes for row in self.observations if row.free_bytes}
            actual = {row.device_id: row.memory_bytes for row in self.devices}
            if len(actual) != len(self.devices) or actual != expected or any(
                row.kind != "cuda" or not row.available for row in self.devices
            ):
                raise NVMLProbeError("per-device observations disagree with placement devices")

    def snapshot(self) -> dict[str, object]:
        return {
            "schema": "skeleton.ai.native-gpu-memory.v1",
            "source": self.source,
            "status": self.status,
            "devices": [
                {"device_id": item.device_id, "kind": item.kind,
                 "free_bytes": item.memory_bytes, "available": item.available}
                for item in self.devices
            ],
            "measured_total_bytes": self.measured_total_bytes,
            "measured_free_bytes": self.measured_free_bytes,
            "device_qualification": "not_assessed",
            "per_device_observations": [
                {"device_id": row.device_id, "total_bytes": row.total_bytes,
                 "free_bytes": row.free_bytes, "used_bytes": row.used_bytes}
                for row in self.observations
            ],
            "identity_scope": "probe_local_ordinal",
        }


def _bind(library: Any, name: str, arguments: list[object]) -> Any:
    function = getattr(library, name, None)
    if function is None:
        raise NVMLProbeError("NVML API entrypoint unavailable")
    function.argtypes = arguments
    function.restype = ctypes.c_int
    return function


def _probe_library(library: Any, *, source: str, max_devices: int) -> NativeGpuMemoryReceipt:
    """Query real or explicitly simulated NVML ABI with strict range checks."""
    init = _bind(library, "nvmlInit_v2", [])
    shutdown = _bind(library, "nvmlShutdown", [])
    count_fn = _bind(library, "nvmlDeviceGetCount_v2", [ctypes.POINTER(ctypes.c_uint)])
    handle_fn = _bind(library, "nvmlDeviceGetHandleByIndex_v2", [
        ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
    ])
    memory_fn = _bind(library, "nvmlDeviceGetMemoryInfo", [
        ctypes.c_void_p, ctypes.POINTER(_MemoryInfo)
    ])
    if init() != 0:
        raise NVMLProbeError("NVML initialization failed")
    try:
        count = ctypes.c_uint()
        if count_fn(ctypes.byref(count)) != 0 or count.value > max_devices:
            raise NVMLProbeError("NVML device count unavailable or exceeds budget")
        devices: list[DeviceDescriptor] = []
        observations: list[GpuMemoryObservation] = []
        total = free = 0
        for index in range(count.value):
            handle = ctypes.c_void_p()
            if handle_fn(index, ctypes.byref(handle)) != 0 or not handle.value:
                raise NVMLProbeError("NVML device handle unavailable")
            info = _MemoryInfo()
            if memory_fn(handle, ctypes.byref(info)) != 0:
                raise NVMLProbeError("NVML device memory unavailable")
            if (info.total <= 0 or info.total >= 1 << 63
                    or info.free > info.total or info.used > info.total
                    or info.free + info.used > info.total):
                raise NVMLProbeError("inconsistent NVML memory counters")
            total += int(info.total)
            free += int(info.free)
            if total >= 1 << 63 or free >= 1 << 63:
                raise NVMLProbeError("aggregate GPU memory overflow")
            device_id = "cuda:" + str(index)
            observations.append(GpuMemoryObservation(device_id, int(info.total), int(info.free), int(info.used)))
            if info.free:
                devices.append(DeviceDescriptor(device_id, "cuda", int(info.free)))
        return NativeGpuMemoryReceipt(source, "measured", tuple(devices), total, free, tuple(observations))
    finally:
        shutdown()


def probe_linux_nvidia_memory(*, max_devices: int = 32) -> NativeGpuMemoryReceipt:
    """Probe actual NVML; unavailable libraries remain explicit unknown."""
    if type(max_devices) is not int or not 1 <= max_devices <= min(32, MAX_DEVICES):
        raise NVMLProbeError("invalid NVML device budget")
    if not sys.platform.startswith("linux"):
        return NativeGpuMemoryReceipt("unavailable", "unavailable", (), 0, 0)
    try:
        library = ctypes.CDLL("libnvidia-ml.so.1")
    except OSError:
        return NativeGpuMemoryReceipt("unavailable", "unavailable", (), 0, 0)
    try:
        return _probe_library(library, source="linux_nvml", max_devices=max_devices)
    except (NVMLProbeError, OSError, TypeError, ValueError):
        return NativeGpuMemoryReceipt("unavailable", "unavailable", (), 0, 0)


__all__ = ["NVMLProbeError", "GpuMemoryObservation", "NativeGpuMemoryReceipt", "probe_linux_nvidia_memory"]

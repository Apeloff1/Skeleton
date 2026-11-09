"""Canonical device placement contracts and native, provenance-tagged probes."""
from .flgb_model_runtime import DeviceDescriptor, ModelRuntimeError, Placement, plan_device_placement
from .nvml_memory_probe import NVMLProbeError, NativeGpuMemoryReceipt, probe_linux_nvidia_memory

__all__ = [
    "DeviceDescriptor", "ModelRuntimeError", "Placement", "plan_device_placement",
    "NVMLProbeError", "NativeGpuMemoryReceipt", "probe_linux_nvidia_memory",
]

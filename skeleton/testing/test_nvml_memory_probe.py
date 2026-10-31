"""NVML probe contract tests; fake ABI is explicitly simulated, not device proof."""
from __future__ import annotations
import ctypes
import pytest

from skeleton.ai.model_runtime.nvml_memory_probe import (
    NVMLProbeError, NativeGpuMemoryReceipt, _MemoryInfo, _probe_library,
    probe_linux_nvidia_memory,
)


class _Function:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class _SimulatedNVML:
    def __init__(self, *, total=4096, free=3072, count=1):
        self.total = total
        self.free = free
        self.count = count
        self.shutdowns = 0
        self.nvmlInit_v2 = _Function(lambda: 0)
        self.nvmlShutdown = _Function(self.shutdown)
        self.nvmlDeviceGetCount_v2 = _Function(self.device_count)
        self.nvmlDeviceGetHandleByIndex_v2 = _Function(self.handle)
        self.nvmlDeviceGetMemoryInfo = _Function(self.memory)

    def shutdown(self):
        self.shutdowns += 1
        return 0

    def device_count(self, ptr):
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint))[0] = self.count
        return 0

    def handle(self, index, ptr):
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(index + 1)
        return 0

    def memory(self, handle, ptr):
        info = ctypes.cast(ptr, ctypes.POINTER(_MemoryInfo))[0]
        info.total = self.total
        info.free = self.free
        info.used = self.total - self.free if self.free <= self.total else 0
        return 0


def test_simulated_abi_reports_measured_free_bytes_without_activation() -> None:
    lib = _SimulatedNVML()
    receipt = _probe_library(lib, source="simulated_nvml", max_devices=4)
    assert receipt.status == "measured"
    assert receipt.devices[0].device_id == "cuda:0"
    assert receipt.devices[0].memory_bytes == 3072
    assert receipt.snapshot()["device_qualification"] == "not_assessed"
    assert lib.shutdowns == 1


def test_zero_free_memory_is_not_a_usable_placement() -> None:
    receipt = _probe_library(_SimulatedNVML(free=0), source="simulated_nvml", max_devices=4)
    assert receipt.measured_total_bytes == 4096
    assert receipt.devices == ()


@pytest.mark.parametrize("total,free", [(0, 0), (100, 101), (1 << 63, 1)])
def test_inconsistent_counters_fail_closed(total: int, free: int) -> None:
    lib = _SimulatedNVML(total=total, free=free)
    with pytest.raises(NVMLProbeError):
        _probe_library(lib, source="simulated_nvml", max_devices=4)
    assert lib.shutdowns == 1


def test_count_limit_enforced_before_handle_query() -> None:
    lib = _SimulatedNVML(count=10)
    with pytest.raises(NVMLProbeError, match="count"):
        _probe_library(lib, source="simulated_nvml", max_devices=2)
    assert lib.shutdowns == 1


@pytest.mark.parametrize("budget", [0, -1, True, 33, 999])
def test_public_device_budget_validation(budget: object) -> None:
    with pytest.raises(NVMLProbeError):
        probe_linux_nvidia_memory(max_devices=budget)


def test_unavailable_receipt_cannot_claim_measured_devices() -> None:
    with pytest.raises(NVMLProbeError):
        NativeGpuMemoryReceipt("unavailable", "unavailable", (
            _probe_library(_SimulatedNVML(), source="simulated_nvml", max_devices=1).devices[0],
        ), 4096, 3072)



@pytest.mark.parametrize("source,status,total,free", [
    ("unavailable", "unavailable", 4096, 0),
    ("unavailable", "unavailable", 0, 1),
    ("linux_nvml", "unavailable", 0, 0),
    ("simulated_nvml", "unavailable", 0, 0),
    ("unavailable", "measured", 0, 0),
])
def test_unavailable_receipt_rejects_fabricated_counters_or_source(
    source: str, status: str, total: int, free: int
) -> None:
    with pytest.raises(NVMLProbeError):
        NativeGpuMemoryReceipt(source, status, (), total, free)

def test_actual_probe_never_invents_gpu_when_unavailable() -> None:
    result = probe_linux_nvidia_memory()
    assert result.source in {"linux_nvml", "unavailable"}
    if result.status == "unavailable":
        assert result.devices == ()
        assert result.measured_total_bytes == 0

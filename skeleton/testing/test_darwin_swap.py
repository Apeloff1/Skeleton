"""macOS swap ABI simulation and explicit unsupported-platform receipts."""
from __future__ import annotations
import ctypes
import pytest
from skeleton.ai.runtime.inference.darwin_swap import (
    DarwinSwapError, _XSWUsage, _probe_sysctl, interpret_darwin_swap, probe_darwin_swap,
)


def test_darwin_swap_bytes_are_not_confused_with_page_counts() -> None:
    state = interpret_darwin_swap(4096, 1024, 3072)
    assert state.used_fraction == 0.25
    assert state.available_bytes == 3072
    assert state.source == "darwin_swap"


@pytest.mark.parametrize("total,used,available", [
    (-1, 0, 0), (100, 101, 0), (100, 10, 101),
    (100, 90, 20), (1 << 63, 1, 1),
])
def test_inconsistent_swap_counters_fail_closed(total: int, used: int, available: int) -> None:
    with pytest.raises(DarwinSwapError):
        interpret_darwin_swap(total, used, available)


def test_disabled_swap_remains_unknown() -> None:
    state = interpret_darwin_swap(0, 0, 0)
    assert state.used_fraction is None


def test_simulated_macos_sysctl_abi() -> None:
    class Function:
        argtypes = None
        restype = None
        def __call__(self, name, output, size, new_value, new_size):
            assert name == b"vm.swapusage"
            info = ctypes.cast(output, ctypes.POINTER(_XSWUsage))[0]
            info.total = 4096
            info.used = 1024
            info.available = 3072
            info.page_size = 4096
            ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t))[0] = ctypes.sizeof(_XSWUsage)
            return 0
    class Simulated:
        sysctlbyname = Function()
    state = _probe_sysctl(Simulated())
    assert state.used_fraction == 0.25


def test_platform_probe_never_fabricates_mchip_swap() -> None:
    result = probe_darwin_swap()
    assert result.source in {"darwin_swap", "darwin_swap_unavailable"}
    if result.source == "darwin_swap_unavailable":
        assert result.used_fraction is None

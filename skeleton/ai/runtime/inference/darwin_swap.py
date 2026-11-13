"""Native macOS virtual-memory swap telemetry for local AI resource receipts."""
from __future__ import annotations
import ctypes
from dataclasses import dataclass
import sys
from typing import Any


class DarwinSwapError(ValueError):
    """Native vm.swapusage counters are invalid or unavailable."""


class _XSWUsage(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_uint64),
        ("available", ctypes.c_uint64),
        ("used", ctypes.c_uint64),
        ("page_size", ctypes.c_uint32),
        ("encrypted", ctypes.c_int32),
    ]


@dataclass(frozen=True, slots=True)
class DarwinSwapState:
    used_fraction: float | None
    available_bytes: int | None
    source: str

    def __post_init__(self) -> None:
        if self.source not in {"darwin_swap", "darwin_swap_unavailable"}:
            raise DarwinSwapError("invalid macOS swap source")
        if self.used_fraction is not None and (
            type(self.used_fraction) is not float or not 0 <= self.used_fraction <= 1
        ):
            raise DarwinSwapError("invalid macOS swap fraction")
        if self.available_bytes is not None and (
            type(self.available_bytes) is not int or not 0 <= self.available_bytes < 1 << 63
        ):
            raise DarwinSwapError("invalid macOS available swap bytes")


def interpret_darwin_swap(total: int, used: int, available: int) -> DarwinSwapState:
    for value in (total, used, available):
        if type(value) is not int or not 0 <= value < 1 << 63:
            raise DarwinSwapError("invalid macOS swap counter")
    if total == 0:
        return DarwinSwapState(None, None, "darwin_swap_unavailable")
    if used > total or available > total or used + available > total:
        raise DarwinSwapError("inconsistent macOS swap counters")
    return DarwinSwapState(float(used / total), available, "darwin_swap")


def _probe_sysctl(library: Any) -> DarwinSwapState:
    function = getattr(library, "sysctlbyname", None)
    if function is None:
        raise DarwinSwapError("macOS sysctlbyname unavailable")
    function.argtypes = [
        ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p, ctypes.c_size_t,
    ]
    function.restype = ctypes.c_int
    info = _XSWUsage()
    length = ctypes.c_size_t(ctypes.sizeof(info))
    if function(b"vm.swapusage", ctypes.byref(info), ctypes.byref(length), None, 0) != 0:
        raise DarwinSwapError("macOS vm.swapusage unavailable")
    if length.value != ctypes.sizeof(info):
        raise DarwinSwapError("unexpected macOS swap structure version")
    return interpret_darwin_swap(int(info.total), int(info.used), int(info.available))


def probe_darwin_swap() -> DarwinSwapState:
    """Actual sysctlbyname on Darwin; other platforms remain explicitly unknown."""
    if sys.platform != "darwin":
        return DarwinSwapState(None, None, "darwin_swap_unavailable")
    try:
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        return _probe_sysctl(library)
    except (OSError, AttributeError, TypeError, ValueError):
        return DarwinSwapState(None, None, "darwin_swap_unavailable")

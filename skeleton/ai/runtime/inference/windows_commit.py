"""Native Windows system commit-charge pressure for local AI admission."""
from __future__ import annotations
import ctypes
from dataclasses import dataclass
import sys
from typing import Any


class WindowsCommitError(ValueError):
    """Windows virtual-memory commit telemetry is invalid."""


class _PerformanceInformation(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", ctypes.c_ulong),
        ("ProcessCount", ctypes.c_ulong),
        ("ThreadCount", ctypes.c_ulong),
    ]


@dataclass(frozen=True, slots=True)
class WindowsCommitState:
    used_fraction: float | None
    available_bytes: int | None
    source: str

    def __post_init__(self) -> None:
        if self.source not in {"windows_commit", "windows_commit_unavailable"}:
            raise WindowsCommitError("invalid Windows commit source")
        if self.used_fraction is not None and (
            type(self.used_fraction) is not float or not 0 <= self.used_fraction <= 1
        ):
            raise WindowsCommitError("invalid commit fraction")
        if self.available_bytes is not None and (
            type(self.available_bytes) is not int or not 0 <= self.available_bytes < 1 << 63
        ):
            raise WindowsCommitError("invalid commit headroom")


def interpret_windows_commit(
    committed_pages: int, limit_pages: int, page_size: int
) -> WindowsCommitState:
    """Interpret real GetPerformanceInfo page counters without overflow."""
    for value in (committed_pages, limit_pages, page_size):
        if type(value) is not int or not 0 <= value < 1 << 63:
            raise WindowsCommitError("invalid Windows page counter")
    if not 0 < limit_pages or not 0 < page_size <= 1 << 20:
        raise WindowsCommitError("missing commit limit or page size")
    if limit_pages * page_size >= 1 << 63:
        raise WindowsCommitError("Windows commit capacity overflows byte contract")
    if committed_pages > limit_pages:
        raise WindowsCommitError("commit charge exceeds system limit")
    return WindowsCommitState(
        float(committed_pages / limit_pages),
        (limit_pages - committed_pages) * page_size,
        "windows_commit",
    )


def _probe_psapi(psapi: Any) -> WindowsCommitState:
    function = getattr(psapi, "GetPerformanceInfo", None)
    if function is None:
        raise WindowsCommitError("GetPerformanceInfo unavailable")
    function.argtypes = [ctypes.POINTER(_PerformanceInformation), ctypes.c_ulong]
    function.restype = ctypes.c_int
    info = _PerformanceInformation()
    info.cb = ctypes.sizeof(info)
    if not function(ctypes.byref(info), info.cb):
        raise WindowsCommitError("GetPerformanceInfo failed")
    return interpret_windows_commit(
        int(info.CommitTotal), int(info.CommitLimit), int(info.PageSize)
    )


def probe_windows_commit() -> WindowsCommitState:
    """Actual Windows PSAPI probe; never claim data from unsupported hosts."""
    if sys.platform != "win32":
        return WindowsCommitState(None, None, "windows_commit_unavailable")
    try:
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        return _probe_psapi(psapi)
    except (OSError, AttributeError, TypeError, ValueError):
        return WindowsCommitState(None, None, "windows_commit_unavailable")

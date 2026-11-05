"""Read-only physical memory availability observations for local-first Jeeves.

This module only asks the host for aggregate counters and never reads model
files, private prompts, process memory or user content. Cgroup/container,
driver allocation, GPU, WSL2 and device-pressure certification remain held.
"""
from __future__ import annotations
from dataclasses import dataclass
import ctypes
import os

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold

_MAX_BYTES = (1 << 63) - 1
_MAX_RESERVATION = 1 << 40


class _MemoryStatusEx(ctypes.Structure):
    """Windows MEMORYSTATUSEX; no process creation or privileged access."""
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _windows_physical() -> tuple[int, int] | None:
    """Query physical RAM via the documented Windows kernel API, if present."""
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        query = kernel.GlobalMemoryStatusEx
        query.argtypes = [ctypes.POINTER(_MemoryStatusEx)]
        query.restype = ctypes.c_int
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not query(ctypes.byref(status)):
            return None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _posix_physical() -> tuple[int, int] | None:
    """Observe current host physical pages, not a cgroup/WSL quota claim."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        page_bytes = os.sysconf("SC_PAGE_SIZE")
        if (type(pages) is not int or type(available_pages) is not int
                or type(page_bytes) is not int
                or not 1 <= page_bytes <= 1048576
                or not 0 <= available_pages <= pages
                or pages <= 0):
            return None
        return pages * page_bytes, available_pages * page_bytes
    except (AttributeError, OSError, ValueError, TypeError):
        return None


@dataclass(frozen=True, slots=True)
class MemoryObservation:
    reserved_bytes: int
    total_bytes: int | None
    available_bytes: int | None
    source: str

    def __post_init__(self) -> None:
        if (type(self.reserved_bytes) is not int
                or not 1 <= self.reserved_bytes <= _MAX_RESERVATION):
            raise LaptopGateHold("finite native RAM reservation required")
        if self.source not in ("windows_physical", "posix_physical", "unknown"):
            raise LaptopGateHold("unrecognized host memory sensor")
        if (self.total_bytes is None) != (self.available_bytes is None):
            raise LaptopGateHold("partial physical RAM observation")
        if self.total_bytes is None:
            if self.source != "unknown":
                raise LaptopGateHold("unknown physical RAM must be marked unknown")
        else:
            if (type(self.total_bytes) is not int
                    or type(self.available_bytes) is not int
                    or not 0 <= self.available_bytes <= self.total_bytes <= _MAX_BYTES
                    or self.total_bytes == 0
                    or self.source == "unknown"):
                raise LaptopGateHold("invalid physical RAM counters")

    @property
    def fits_observed_ram(self) -> bool:
        return (self.available_bytes is not None
                and self.reserved_bytes <= self.available_bytes)

    def to_record(self) -> dict[str, object]:
        """Never convert free physical RAM to a native-startup grant."""
        return {
            "schema": "jeeves.laptop_ops.host_ram.v1",
            "reserved_bytes": self.reserved_bytes,
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
            "sensor": self.source,
            "fits_observed_ram": self.fits_observed_ram,
            "cgroup_or_wsl2_limit_verified": False,
            "gpu_allocation_verified": False,
            "native_model_started": False,
            "physical_device_qualified": False,
            "release_certified": False,
        }


def observe_ram(reserved_bytes: int) -> MemoryObservation:
    """Read one conservative aggregate physical snapshot without model IO."""
    if (type(reserved_bytes) is not int
            or not 1 <= reserved_bytes <= _MAX_RESERVATION):
        raise LaptopGateHold("invalid finite model memory reservation")
    windows = os.name == "nt"
    raw = _windows_physical() if windows else _posix_physical()
    source = "windows_physical" if windows else "posix_physical"
    if raw is not None:
        try:
            return MemoryObservation(reserved_bytes, raw[0], raw[1], source)
        except (LaptopGateHold, TypeError, ValueError, IndexError):
            pass
    return MemoryObservation(reserved_bytes, None, None, "unknown")


__all__ = ["MemoryObservation", "observe_ram"]

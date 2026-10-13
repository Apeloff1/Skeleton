"""Read-only, conservative hardware-aware planning for sparse local AI training.

Resource observation is only used to select a *training text preparation*
budget. It never approves model execution, GPU availability, accelerator
support, power limits or fit of transformer weights/optimizer states.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Callable, Mapping

GIB = 1024 ** 3
MIB = 1024 ** 2
SCHEMA = "skeleton.offline_resource_admission.v1"
_LIMIT_FILES = (
    "/sys/fs/cgroup/memory.max",
    "/sys/fs/cgroup/memory/memory.limit_in_bytes",
)
_USAGE_FILES = (
    "/sys/fs/cgroup/memory.current",
    "/sys/fs/cgroup/memory/memory.usage_in_bytes",
)
_PROFILE = {
    "low-memory": (36, 8192),
    "consumer": (48, 12288),
    "workstation": (72, 16384),
}


class ResourceAdmissionError(ValueError):
    """Unsafe caller limits or inconsistent platform resource readings."""


@dataclass(frozen=True, slots=True)
class ResourceObservation:
    physical_ram_bytes: int | None
    available_ram_bytes: int | None
    cgroup_free_bytes: int | None
    logical_cpu_count: int | None
    platform: str
    memory_source: str
    cpu_source: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA,
            "physical_ram_bytes": self.physical_ram_bytes,
            "available_ram_bytes": self.available_ram_bytes,
            "cgroup_free_bytes": self.cgroup_free_bytes,
            "logical_cpu_count": self.logical_cpu_count,
            "platform": self.platform,
            "memory_source": self.memory_source,
            "cpu_source": self.cpu_source,
            "gpu_verified": False,
            "model_execution_fit_verified": False,
        }


def _positive(value: object) -> int | None:
    if type(value) is not int or value <= 0 or value >= (1 << 62):
        return None
    return value


def _read_linux_meminfo(read_text: Callable[[str], str]) -> tuple[int | None, int | None]:
    try:
        lines = read_text("/proc/meminfo")
    except (OSError, UnicodeError, KeyError):
        return None, None
    values: dict[str, int] = {}
    for line in lines.splitlines():
        key, delimiter, remaining = line.partition(":")
        if not delimiter or key not in ("MemTotal", "MemAvailable", "MemFree"):
            continue
        items = remaining.strip().split()
        if len(items) != 2 or items[1] != "kB" or not items[0].isascii():
            continue
        try:
            val = int(items[0]) * 1024
        except ValueError:
            continue
        if _positive(val) is not None:
            values[key] = val
    total = values.get("MemTotal")
    # Available bytes without a validated physical ceiling could be a
    # malformed/injected value. Fail conservatively instead of escalating.
    if total is None:
        return None, None
    free = values.get("MemAvailable") or values.get("MemFree")
    if free is not None and free > total:
        free = total
    return total, free


def _read_cgroup_free(read_text: Callable[[str], str]) -> int | None:
    """Use v2/v1 limit - current, ignoring 'max' and implausible host ceilings."""
    for limit_path, used_path in zip(_LIMIT_FILES, _USAGE_FILES):
        try:
            max_text = read_text(limit_path).strip()
            used_text = read_text(used_path).strip()
        except (OSError, UnicodeError, KeyError):
            continue
        if max_text == "max":
            continue
        try:
            ceiling, used = int(max_text), int(used_text)
        except ValueError:
            continue
        if _positive(ceiling) is None or used < 0 or used >= (1 << 62):
            continue
        # Cgroup v1 commonly reports a huge sentinel for no memory limit.
        if ceiling >= (1 << 60):
            continue
        return max(0, ceiling - used)
    return None


def _windows_memory_status() -> tuple[int | None, int | None]:
    """Read Windows RAM with a native read-only API; no shell process."""
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None
        total, free = _positive(int(status.ullTotalPhys)), _positive(int(status.ullAvailPhys))
        if total is None or free is None:
            return None, None
        return total, min(free, total)
    except (AttributeError, OSError, TypeError, ValueError):
        return None, None


def _linux_effective_cpus(
    read_text: Callable[[str], str],
    *,
    affinity: Callable[[], int | None] | None = None,
) -> int | None:
    """Clamp logical CPUs to cpuset/affinity and cgroup quota when known."""
    upper: list[int] = []
    if affinity is not None:
        try:
            usable = _positive(affinity())
            if usable is not None:
                upper.append(usable)
        except (OSError, ValueError, TypeError):
            pass
    for path in ("/sys/fs/cgroup/cpu.max",):
        try:
            parts = read_text(path).strip().split()
        except (OSError, UnicodeError, KeyError):
            continue
        if len(parts) != 2 or parts[0] == "max":
            continue
        try:
            quota, period = map(int, parts)
        except ValueError:
            continue
        if quota > 0 and period > 0:
            upper.append(max(1, quota // period))
    # The v1 cgroup CPU quota format uses two independent paths.
    try:
        quota = int(read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").strip())
        period = int(read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us").strip())
        if quota > 0 and period > 0:
            upper.append(max(1, quota // period))
    except (OSError, UnicodeError, ValueError):
        pass
    return min(upper) if upper else None


def observe_resources(
    *,
    platform: str | None = None,
    read_text: Callable[[str], str] | None = None,
    cpu_count: Callable[[], int | None] | None = None,
    sysconf: Callable[[str], int] | None = None,
    windows_memory: Callable[[], tuple[int | None, int | None]] | None = None,
    cpu_affinity: Callable[[], int | None] | None = None,
) -> ResourceObservation:
    """Observe device resources with injectable probes; no shell/network/GPU calls."""
    current_platform = platform or sys.platform
    if current_platform not in ("linux", "darwin", "win32"):
        current_platform = "unknown"
    reader = read_text or (lambda name: Path(name).read_text(encoding="ascii"))
    cpu = cpu_count or os.cpu_count
    sysconf = sysconf or getattr(os, "sysconf", lambda _name: None)
    try:
        cpus = _positive(cpu())
    except (OSError, TypeError, ValueError):
        cpus = None
    physical = available = cgroup = None
    memory_source = "unknown"
    if current_platform == "linux":
        physical, available = _read_linux_meminfo(reader)
        cgroup = _read_cgroup_free(reader)
        if physical is not None:
            memory_source = "linux_proc"
        if cpu_affinity is None:
            def _actual_affinity() -> int | None:
                try:
                    return len(os.sched_getaffinity(0))
                except (AttributeError, OSError):
                    return None
            cpu_affinity = _actual_affinity
        constrained = _linux_effective_cpus(reader, affinity=cpu_affinity)
        if constrained is not None:
            cpus = min(cpus, constrained) if cpus is not None else constrained
    elif current_platform == "win32":
        probe = windows_memory or _windows_memory_status
        physical, available = probe()
        if physical is not None and available is not None and 0 < available <= physical:
            memory_source = "windows_global_memory_status"
        else:
            physical = available = None
    if physical is None:
        try:
            pages = sysconf("SC_PHYS_PAGES")
            size = sysconf("SC_PAGE_SIZE")
            if _positive(pages) is not None and _positive(size) is not None:
                physical = _positive(pages * size)
                if physical is not None:
                    memory_source = "sysconf_physical"
        except (AttributeError, OSError, ValueError, TypeError):
            pass
    # Physical RAM is a ceiling, never proof of *available* memory.
    # macOS and unknown platforms without a free-memory probe stay on the
    # smallest profile, even if total installed RAM is large.
    limits = [value for value in (available, cgroup) if value is not None]
    if limits and physical is not None:
        limits.append(physical)
    conservative = min(limits) if limits else None
    return ResourceObservation(
        physical_ram_bytes=physical,
        available_ram_bytes=conservative,
        cgroup_free_bytes=cgroup,
        logical_cpu_count=cpus,
        platform=current_platform,
        memory_source=memory_source,
        cpu_source="os_cpu_count" if cpus is not None else "unknown",
    )


def select_sparse_profile(
    observation: ResourceObservation,
    *,
    ceiling_profile: str = "workstation",
    reserve_bytes: int = 512 * MIB,
) -> dict[str, object]:
    """Resource-aware auto policy, never unconditionally increases dataset size."""
    if ceiling_profile not in _PROFILE:
        raise ResourceAdmissionError("unknown sparse training profile ceiling")
    if type(reserve_bytes) is not int or reserve_bytes < 0 or reserve_bytes > 16 * GIB:
        raise ResourceAdmissionError("invalid reserved memory allowance")
    available = observation.available_ram_bytes
    cpus = observation.logical_cpu_count
    usable = max(0, available - reserve_bytes) if available is not None else None

    # Unknown resource measurements choose the smallest prepared dataset.
    if usable is None or cpus is None:
        selected = "low-memory"
        reason = "resources_unmeasured_conservative"
    elif usable >= 8 * GIB and cpus >= 8:
        selected = "workstation"
        reason = "resource_threshold_workstation"
    elif usable >= 2 * GIB and cpus >= 4:
        selected = "consumer"
        reason = "resource_threshold_consumer"
    else:
        selected = "low-memory"
        reason = "resource_threshold_low_memory"
    order = ("low-memory", "consumer", "workstation")
    if order.index(selected) > order.index(ceiling_profile):
        selected = ceiling_profile
        reason = "operator_profile_ceiling"
    count, bytes_cap = _PROFILE[selected]
    return {
        "schema_version": SCHEMA,
        "mode": "auto",
        "selected_profile": selected,
        "reason": reason,
        "training_record_limit": count,
        "training_text_byte_cap": bytes_cap,
        "reserved_memory_bytes": reserve_bytes,
        "observed_usable_ram_bytes": usable,
        "observed_cpu_count": cpus,
        "observation": observation.as_dict(),
        "weights_or_optimizer_fit_verified": False,
        "hardware_benchmark_performed": False,
        "accelerator_available_claimed": False,
    }


__all__ = [
    "GIB", "MIB", "SCHEMA", "ResourceAdmissionError",
    "ResourceObservation", "observe_resources", "select_sparse_profile",
]

"""Live hardware-pressure admission for device-local, memory-backed AI files.

No fixed user file, document or corpus quotas. Current operations that still
materialize document text in RAM must fit *live* headroom. Low resources cause
recoverable backpressure, never silent truncation, eviction, or a policy bypass.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import math
import os
from pathlib import Path
import shutil


class LocalResourcePressure(RuntimeError):
    """Insufficient measurable headroom for the requested local operation."""


@dataclass(frozen=True)
class LocalResourceSnapshot:
    total_ram_bytes: int
    available_ram_bytes: int
    total_disk_bytes: int
    free_disk_bytes: int
    cpu_count: int
    cpu_load_ratio: float
    total_swap_bytes: int = 0
    free_swap_bytes: int = 0
    memory_pressure_ratio: float = 0.0

    def __post_init__(self) -> None:
        for name in ("total_ram_bytes", "available_ram_bytes",
                     "total_disk_bytes", "free_disk_bytes", "cpu_count",
                     "total_swap_bytes", "free_swap_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"invalid hardware reading: {name}")
        if (self.total_ram_bytes < self.available_ram_bytes
                or self.total_disk_bytes < self.free_disk_bytes
                or self.total_swap_bytes < self.free_swap_bytes
                or self.cpu_count < 1 or self.total_ram_bytes == 0
                or self.total_disk_bytes == 0
                or not math.isfinite(self.cpu_load_ratio)
                or self.cpu_load_ratio < 0
                or not math.isfinite(self.memory_pressure_ratio)
                or not 0 <= self.memory_pressure_ratio <= 1):
            raise ValueError("inconsistent hardware measurements")

    @property
    def resident_document_budget(self) -> int:
        # Six copies cover decoder, Python text, chunks and SQLite/FTS work.
        # Recomputed at admission, not a fixed product/user file ceiling.
        # Swap/pagefile is not interchangeable with physical RAM. If it is
        # heavily committed, spill earlier rather than forcing OS paging.
        swap_used = (
            1 - self.free_swap_bytes / self.total_swap_bytes
            if self.total_swap_bytes else 0.0
        )
        pressure = max(self.memory_pressure_ratio, max(0.0, swap_used - 0.5))
        return int(self.available_ram_bytes * 0.45 * (1 - pressure * 0.8)) // 6

    @property
    def disk_document_budget(self) -> int:
        # SQLite body+FTS+WAL can amplify a newly stored source. Preserve
        # proportional free/total disk headroom for the OS and other apps.
        reserve = max(int(self.total_disk_bytes * 0.01),
                      int(self.free_disk_bytes * 0.10))
        return max(0, self.free_disk_bytes - reserve) // 4

    @property
    def should_spill_early(self) -> bool:
        # In physical-memory contention, pagefile availability is monitored
        # but never used as a reason to force whole documents into RAM.
        swap_filled = (
            1 - self.free_swap_bytes / self.total_swap_bytes
            if self.total_swap_bytes else 0.0
        )
        return self.memory_pressure_ratio >= 0.20 or swap_filled >= 0.85

    @property
    def read_chunk_bytes(self) -> int:
        # A transfer buffer, NOT a maximum file length.
        chunk = min(1024 * 1024, max(8 * 1024,
                    self.available_ram_bytes // 1024))
        if self.cpu_load_ratio >= 0.85 or self.should_spill_early:
            chunk = max(8 * 1024, chunk // 4)
        elif self.cpu_load_ratio >= 0.65:
            chunk = max(8 * 1024, chunk // 2)
        return chunk

    @property
    def suggested_index_jobs(self) -> int:
        # Each source is processed serially today. Bound *work admitted per
        # invocation*, not the number of stored jobs or documents.
        memory_share = self.available_ram_bytes / self.total_ram_bytes
        cpu_share = max(0.0, 1.0 - min(1.0, self.cpu_load_ratio))
        pressure_share = 1.0 - self.memory_pressure_ratio
        if self.should_spill_early:
            pressure_share *= 0.5
        return max(1, int(self.cpu_count * memory_share * cpu_share
                          * pressure_share))

    def as_dict(self) -> dict[str, int | float]:
        return {
            "total_ram_bytes": self.total_ram_bytes,
            "available_ram_bytes": self.available_ram_bytes,
            "total_disk_bytes": self.total_disk_bytes,
            "free_disk_bytes": self.free_disk_bytes,
            "cpu_count": self.cpu_count,
            "cpu_load_ratio": self.cpu_load_ratio,
            "total_swap_bytes": self.total_swap_bytes,
            "free_swap_bytes": self.free_swap_bytes,
            "memory_pressure_ratio": self.memory_pressure_ratio,
            "should_spill_early": self.should_spill_early,
            "resident_document_budget": self.resident_document_budget,
            "disk_document_budget": self.disk_document_budget,
            "read_chunk_bytes": self.read_chunk_bytes,
            "suggested_index_jobs": self.suggested_index_jobs,
        }


def _read_counter(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="ascii").strip()
        return int(value) if value.isdecimal() else None
    except (OSError, UnicodeError, ValueError):
        return None


def _linux_memory() -> tuple[int, int] | None:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                key, _, raw = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    if not all(values.get(k, 0) > 0 for k in ("MemTotal", "MemAvailable")):
        return None
    total, available = values["MemTotal"], values["MemAvailable"]
    # Respect a Docker/WSL/container memory ceiling, not only host RAM.
    for maximum, usage in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
         "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        ceiling = _read_counter(Path(maximum))
        used = _read_counter(Path(usage))
        if ceiling is not None and used is not None and 0 < ceiling < total:
            total = ceiling
            available = min(available, max(0, ceiling - used))
            break
    return total, min(total, available)


def _linux_swap() -> tuple[int, int]:
    """Swap under the effective cgroup ceiling; unknown reports zero."""
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                key, _, raw = line.partition(":")
                if key in {"SwapTotal", "SwapFree"}:
                    values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return 0, 0
    total = max(0, values.get("SwapTotal", 0))
    free = min(total, max(0, values.get("SwapFree", 0)))
    for ceiling_path, usage_path in (
        ("/sys/fs/cgroup/memory.swap.max",
         "/sys/fs/cgroup/memory.swap.current"),
        ("/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes",
         "/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes"),
    ):
        ceiling = _read_counter(Path(ceiling_path))
        used = _read_counter(Path(usage_path))
        if ceiling is not None and used is not None and ceiling < total:
            total = max(0, ceiling)
            free = min(free, max(0, ceiling - used))
            break
    return total, free


def _linux_memory_pressure() -> float:
    try:
        with open("/proc/pressure/memory", encoding="ascii") as handle:
            first = handle.readline()
        if first.startswith("some "):
            for field in first.split():
                if field.startswith("avg10="):
                    return min(1.0, max(0.0, float(field.split("=", 1)[1]) / 100))
    except (OSError, ValueError):
        pass
    return 0.0


def _windows_memory_status() -> tuple[int, int, int, int] | None:
    """GlobalMemoryStatusEx pagefile values are *commit* capacity estimates."""
    if os.name != "nt":
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
            ("total_phys", ctypes.c_ulonglong),
            ("avail_phys", ctypes.c_ulonglong),
            ("total_page", ctypes.c_ulonglong),
            ("avail_page", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("avail_virtual", ctypes.c_ulonglong),
            ("avail_extended", ctypes.c_ulonglong),
        ]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total_swap = max(0, status.total_page - status.total_phys)
            free_swap = min(total_swap, max(0, status.avail_page - status.avail_phys))
            return status.total_phys, status.avail_phys, total_swap, free_swap
    except (AttributeError, OSError):
        return None
    return None


def _windows_memory() -> tuple[int, int] | None:
    status = _windows_memory_status()
    return status[:2] if status else None


def probe_local_resources(storage_path: str | Path = ".") -> LocalResourceSnapshot:
    """Sample resource headroom for the target storage volume *now*."""
    windows = _windows_memory_status() if os.name == "nt" else None
    memory = _linux_memory() if os.name != "nt" else (
        (windows[0], windows[1]) if windows else None
    )
    swap = _linux_swap() if os.name != "nt" else (
        (windows[2], windows[3]) if windows else (0, 0)
    )
    pressure = _linux_memory_pressure() if os.name != "nt" else 0.0
    if memory is None:
        # Optional dependency improves support on macOS and other platforms.
        try:
            import psutil  # type: ignore[import-not-found]
            mem = psutil.virtual_memory()
            memory = int(mem.total), int(mem.available)
            sw = psutil.swap_memory()
            swap = int(sw.total), int(sw.free)
        except (ImportError, OSError, AttributeError):
            raise LocalResourcePressure(
                "Cannot measure available RAM; refusing unbounded in-memory indexing"
            ) from None
    try:
        target = Path(storage_path).expanduser()
        volume = target if target.is_dir() else target.parent
        disk = shutil.disk_usage(volume)
    except OSError as exc:
        raise LocalResourcePressure("Cannot measure local storage headroom") from exc
    cores = max(1, os.cpu_count() or 1)
    # cgroup CPU quotas can be smaller than the visible host core count.
    try:
        quota_file = Path("/sys/fs/cgroup/cpu.max")
        parts = quota_file.read_text(encoding="ascii").split()
        if len(parts) == 2 and parts[0].isdecimal() and parts[1].isdecimal():
            quota, period = int(parts[0]), int(parts[1])
            if period > 0:
                cores = min(cores, max(1, math.ceil(quota / period)))
    except (OSError, UnicodeError, ValueError):
        pass
    try:
        load = os.getloadavg()[0] / cores
    except (AttributeError, OSError):
        # Windows does not expose Unix load averages. Prefer actual CPU usage
        # when psutil is available; no invented pressure measurement.
        try:
            import psutil  # type: ignore[import-not-found]
            load = psutil.cpu_percent(interval=None) / 100.0
        except (ImportError, OSError, AttributeError):
            load = 0.0
    return LocalResourceSnapshot(
        total_ram_bytes=int(memory[0]),
        available_ram_bytes=int(memory[1]),
        total_disk_bytes=int(disk.total),
        free_disk_bytes=int(disk.free),
        cpu_count=cores,
        cpu_load_ratio=max(0.0, load),
        total_swap_bytes=swap[0],
        free_swap_bytes=swap[1],
        memory_pressure_ratio=pressure,
    )


def admit_resident_document(
    snapshot: LocalResourceSnapshot, size_bytes: int, *, write: bool = False
) -> None:
    """Admit a full-text RAM operation only if present hardware can sustain it."""
    if type(size_bytes) is not int or size_bytes < 0:
        raise ValueError("invalid source size")
    if size_bytes > snapshot.resident_document_budget or (
        snapshot.should_spill_early and size_bytes > snapshot.read_chunk_bytes
    ):
        raise LocalResourcePressure(
            "Available RAM is under pressure for this source; free memory "
            "or use chunk-indexed storage. No data was truncated."
        )
    if write and size_bytes > snapshot.disk_document_budget:
        raise LocalResourcePressure(
            "Insufficient disk/WAL headroom to index source safely; "
            "free storage and retry. Existing index remains unchanged."
        )


__all__ = [
    "LocalResourcePressure", "LocalResourceSnapshot",
    "probe_local_resources", "admit_resident_document",
]

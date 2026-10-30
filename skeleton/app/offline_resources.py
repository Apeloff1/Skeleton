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

    def __post_init__(self) -> None:
        for name in ("total_ram_bytes", "available_ram_bytes",
                     "total_disk_bytes", "free_disk_bytes", "cpu_count"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"invalid hardware reading: {name}")
        if (self.total_ram_bytes < self.available_ram_bytes
                or self.total_disk_bytes < self.free_disk_bytes
                or self.cpu_count < 1 or self.total_ram_bytes == 0
                or self.total_disk_bytes == 0
                or not math.isfinite(self.cpu_load_ratio)
                or self.cpu_load_ratio < 0):
            raise ValueError("inconsistent hardware measurements")

    @property
    def resident_document_budget(self) -> int:
        # Six copies cover decoder, Python text, chunks and SQLite/FTS work.
        # Recomputed at admission, not a fixed product/user file ceiling.
        return int(self.available_ram_bytes * 0.45) // 6

    @property
    def disk_document_budget(self) -> int:
        # SQLite body+FTS+WAL can amplify a newly stored source. Preserve
        # proportional free/total disk headroom for the OS and other apps.
        reserve = max(int(self.total_disk_bytes * 0.01),
                      int(self.free_disk_bytes * 0.10))
        return max(0, self.free_disk_bytes - reserve) // 4

    @property
    def read_chunk_bytes(self) -> int:
        # A transfer buffer, NOT a maximum file length.
        chunk = min(1024 * 1024, max(8 * 1024,
                    self.available_ram_bytes // 1024))
        if self.cpu_load_ratio >= 0.85:
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
        return max(1, int(self.cpu_count * memory_share * cpu_share))

    def as_dict(self) -> dict[str, int | float]:
        return {
            "total_ram_bytes": self.total_ram_bytes,
            "available_ram_bytes": self.available_ram_bytes,
            "total_disk_bytes": self.total_disk_bytes,
            "free_disk_bytes": self.free_disk_bytes,
            "cpu_count": self.cpu_count,
            "cpu_load_ratio": self.cpu_load_ratio,
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


def _windows_memory() -> tuple[int, int] | None:
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
            return status.total_phys, status.avail_phys
    except (AttributeError, OSError):
        return None
    return None


def probe_local_resources(storage_path: str | Path = ".") -> LocalResourceSnapshot:
    """Sample resource headroom for the target storage volume *now*."""
    memory = _linux_memory() or _windows_memory()
    if memory is None:
        # Optional dependency improves support on macOS and other platforms.
        try:
            import psutil  # type: ignore[import-not-found]
            mem = psutil.virtual_memory()
            memory = int(mem.total), int(mem.available)
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
    try:
        load = os.getloadavg()[0] / cores
    except (AttributeError, OSError):
        load = 0.0
    return LocalResourceSnapshot(
        total_ram_bytes=int(memory[0]),
        available_ram_bytes=int(memory[1]),
        total_disk_bytes=int(disk.total),
        free_disk_bytes=int(disk.free),
        cpu_count=cores,
        cpu_load_ratio=max(0.0, load),
    )


def admit_resident_document(
    snapshot: LocalResourceSnapshot, size_bytes: int, *, write: bool = False
) -> None:
    """Admit a full-text RAM operation only if present hardware can sustain it."""
    if type(size_bytes) is not int or size_bytes < 0:
        raise ValueError("invalid source size")
    if size_bytes > snapshot.resident_document_budget:
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

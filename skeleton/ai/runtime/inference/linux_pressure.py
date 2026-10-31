"""Bounded Linux memory PSI sampling for the canonical local inference runtime."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
import math
import os

class PressureTelemetryError(ValueError):
    """Kernel PSI is malformed, rather than a zero-pressure observation."""

@dataclass(frozen=True, slots=True)
class LinuxMemoryPressure:
    some_avg10: float | None
    full_avg10: float | None
    source: str

    def __post_init__(self) -> None:
        for value in (self.some_avg10, self.full_avg10):
            if value is not None and (type(value) is not float or not math.isfinite(value) or not 0 <= value <= 1):
                raise PressureTelemetryError("invalid PSI fraction")
        if self.source not in {"linux_cgroup_psi", "linux_host_psi", "linux_psi_unavailable", "linux_psi_invalid"}:
            raise PressureTelemetryError("invalid PSI source")

def parse_linux_memory_psi(raw: str) -> tuple[float, float | None]:
    """Parse kernel 10-second partial/full stalls; reject duplicate and nonfinite fields."""
    if type(raw) is not str or not 1 <= len(raw) <= 4096 or not raw.isascii():
        raise PressureTelemetryError("PSI must be bounded ASCII")
    records: dict[str, float] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5 or parts[0] not in {"some", "full"} or parts[0] in records:
            raise PressureTelemetryError("invalid or duplicate PSI class")
        fields: dict[str, str] = {}
        for item in parts[1:]:
            key, sep, value = item.partition("=")
            if not sep or key in fields:
                raise PressureTelemetryError("invalid PSI field")
            fields[key] = value
        if set(fields) != {"avg10", "avg60", "avg300", "total"}:
            raise PressureTelemetryError("incomplete PSI record")
        try:
            averages = [float(fields[name]) for name in ("avg10", "avg60", "avg300")]
        except ValueError as exc:
            raise PressureTelemetryError("invalid PSI average") from exc
        if any(not math.isfinite(value) or not 0 <= value <= 100 for value in averages):
            raise PressureTelemetryError("PSI percentage out of range")
        if (not fields["total"].isascii() or not fields["total"].isdecimal()
                or len(fields["total"]) > 20 or int(fields["total"]) >= 1 << 64):
            raise PressureTelemetryError("invalid PSI microsecond counter")
        records[parts[0]] = averages[0] / 100.0
    if "some" not in records:
        raise PressureTelemetryError("missing PSI some record")
    return records["some"], records.get("full")

def read_linux_memory_pressure(
    read_text: Callable[[str], str], *, cgroup_directory: str | None = None
) -> LinuxMemoryPressure:
    """Prefer cgroup-v2 pressure; never launder malformed scoped data via host PSI."""
    if not callable(read_text):
        raise TypeError("read_text must be callable")
    paths: list[tuple[str, str]] = []
    if cgroup_directory is not None:
        if type(cgroup_directory) is not str or not os.path.isabs(cgroup_directory) or "\x00" in cgroup_directory:
            raise PressureTelemetryError("invalid cgroup directory")
        paths.append((os.path.join(cgroup_directory, "memory.pressure"), "linux_cgroup_psi"))
    paths.append(("/proc/pressure/memory", "linux_host_psi"))
    for path, source in paths:
        try:
            raw = read_text(path)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError):
            return LinuxMemoryPressure(None, None, "linux_psi_invalid")
        try:
            some, full = parse_linux_memory_psi(raw)
        except PressureTelemetryError:
            return LinuxMemoryPressure(None, None, "linux_psi_invalid")
        return LinuxMemoryPressure(some, full, source)
    return LinuxMemoryPressure(None, None, "linux_psi_unavailable")

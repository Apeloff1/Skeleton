"""Bounded Linux cgroup/host IO stall pressure for local inference backpressure."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
import os

from .linux_pressure import PressureTelemetryError, parse_linux_memory_psi


@dataclass(frozen=True, slots=True)
class LinuxIOPressure:
    some_avg10: float | None
    full_avg10: float | None
    source: str

    def __post_init__(self) -> None:
        if self.source not in {"linux_cgroup_io_psi", "linux_host_io_psi", "linux_io_psi_unavailable", "linux_io_psi_invalid"}:
            raise PressureTelemetryError("invalid IO PSI provenance")
        for value in (self.some_avg10, self.full_avg10):
            if value is not None and (type(value) is not float or not 0 <= value <= 1):
                raise PressureTelemetryError("invalid IO PSI fraction")


def read_linux_io_pressure(
    read_text: Callable[[str], str], *, cgroup_directory: str | None = None
) -> LinuxIOPressure:
    """Prefer scoped cgroup-v2 io.pressure, never mask unreadable scoped data."""
    if not callable(read_text):
        raise TypeError("read_text must be callable")
    paths: list[tuple[str, str]] = []
    if cgroup_directory is not None:
        if type(cgroup_directory) is not str or not os.path.isabs(cgroup_directory) or "\x00" in cgroup_directory:
            raise PressureTelemetryError("invalid cgroup IO directory")
        paths.append((os.path.join(cgroup_directory, "io.pressure"), "linux_cgroup_io_psi"))
    paths.append(("/proc/pressure/io", "linux_host_io_psi"))
    for path, source in paths:
        try:
            raw = read_text(path)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError):
            return LinuxIOPressure(None, None, "linux_io_psi_invalid")
        try:
            some, full = parse_linux_memory_psi(raw)
        except PressureTelemetryError:
            return LinuxIOPressure(None, None, "linux_io_psi_invalid")
        return LinuxIOPressure(some, full, source)
    return LinuxIOPressure(None, None, "linux_io_psi_unavailable")

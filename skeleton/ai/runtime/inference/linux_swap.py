"""Measured Linux host/cgroup swap occupancy for offline resource receipts."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
import os


class SwapTelemetryError(ValueError):
    """Swap telemetry is malformed or unavailable, not zero utilization."""


@dataclass(frozen=True, slots=True)
class LinuxSwapState:
    used_fraction: float | None
    available_bytes: int | None
    source: str

    def __post_init__(self) -> None:
        if self.used_fraction is not None and (
            type(self.used_fraction) is not float or not 0 <= self.used_fraction <= 1
        ):
            raise SwapTelemetryError("invalid swap fraction")
        if self.available_bytes is not None and (
            type(self.available_bytes) is not int or not 0 <= self.available_bytes < 1 << 63
        ):
            raise SwapTelemetryError("invalid available swap bytes")
        if self.source not in {"linux_cgroup_swap", "linux_host_swap", "linux_swap_unavailable", "linux_swap_invalid"}:
            raise SwapTelemetryError("invalid swap source")


def _host_swap(raw: str) -> LinuxSwapState:
    if type(raw) is not str or len(raw) > 16384 or not raw.isascii():
        raise SwapTelemetryError("invalid bounded /proc/meminfo")
    values: dict[str, int] = {}
    for line in raw.splitlines():
        name, sep, data = line.partition(":")
        if name not in {"SwapTotal", "SwapFree"}:
            continue
        if not sep or name in values:
            raise SwapTelemetryError("duplicate or malformed swap counter")
        parts = data.strip().split()
        if len(parts) != 2 or parts[1] != "kB" or not parts[0].isascii() or not parts[0].isdecimal():
            raise SwapTelemetryError("invalid swap counter unit")
        value = int(parts[0]) * 1024
        if value >= 1 << 63:
            raise SwapTelemetryError("swap counter overflow")
        values[name] = value
    if set(values) != {"SwapTotal", "SwapFree"} or values["SwapTotal"] == 0:
        return LinuxSwapState(None, None, "linux_swap_unavailable")
    total, free = values["SwapTotal"], values["SwapFree"]
    if free > total:
        raise SwapTelemetryError("host swap free exceeds total")
    return LinuxSwapState(float((total - free) / total), free, "linux_host_swap")


def read_linux_swap(
    read_text: Callable[[str], str], *, cgroup_directory: str | None = None
) -> LinuxSwapState:
    """Use bounded cgroup-v2 swap if finite, else host; invalid scoped data denies fallback."""
    if not callable(read_text):
        raise TypeError("read_text must be callable")
    if cgroup_directory is not None:
        if type(cgroup_directory) is not str or not os.path.isabs(cgroup_directory) or "\x00" in cgroup_directory:
            raise SwapTelemetryError("invalid swap cgroup directory")
        try:
            maximum = read_text(os.path.join(cgroup_directory, "memory.swap.max"))
        except FileNotFoundError:
            maximum = "max"
        except (OSError, ValueError, UnicodeError):
            return LinuxSwapState(None, None, "linux_swap_invalid")
        if maximum != "max":
            try:
                if not maximum.isascii() or not maximum.isdecimal():
                    raise SwapTelemetryError("invalid cgroup swap maximum")
                limit = int(maximum)
                current_raw = read_text(os.path.join(cgroup_directory, "memory.swap.current"))
                if not current_raw.isascii() or not current_raw.isdecimal():
                    raise SwapTelemetryError("invalid cgroup swap usage")
                current = int(current_raw)
                if not 0 < limit < 1 << 63 or not 0 <= current < 1 << 63:
                    raise SwapTelemetryError("cgroup swap counter outside range")
            except (OSError, ValueError, UnicodeError):
                return LinuxSwapState(None, None, "linux_swap_invalid")
            return LinuxSwapState(
                float(min(1.0, current / limit)), max(0, limit - current), "linux_cgroup_swap"
            )
    try:
        return _host_swap(read_text("/proc/meminfo"))
    except (OSError, ValueError, UnicodeError):
        return LinuxSwapState(None, None, "linux_swap_invalid")

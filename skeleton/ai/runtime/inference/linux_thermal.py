"""Bounded Linux sysfs thermal headroom for local inference backpressure.

Only real kernel critical-trip measurements authorize a thermal decision.
"""
from __future__ import annotations
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import glob
import re
from itertools import islice


class ThermalTelemetryError(ValueError):
    """Kernel thermal metadata cannot be interpreted safely."""


@dataclass(frozen=True, slots=True)
class LinuxThermalState:
    level: str | None
    minimum_headroom_c: float | None
    measured_zones: int
    source: str

    def __post_init__(self) -> None:
        if self.level not in {None, "normal", "elevated", "critical"}:
            raise ThermalTelemetryError("invalid thermal level")
        if type(self.measured_zones) is not int or not 0 <= self.measured_zones <= 64:
            raise ThermalTelemetryError("invalid measured zone count")
        if self.source not in {"linux_sysfs_thermal", "unavailable"}:
            raise ThermalTelemetryError("invalid thermal provenance")


def _millidegrees(value: str) -> int:
    if type(value) is not str or not 1 <= len(value) <= 16:
        raise ThermalTelemetryError("invalid thermal temperature")
    try:
        measured = int(value.strip(), 10)
    except ValueError as exc:
        raise ThermalTelemetryError("non-numeric thermal temperature") from exc
    if not -50000 <= measured <= 200000:
        raise ThermalTelemetryError("thermal temperature outside plausible sensor range")
    return measured


def sample_linux_thermal(
    read_text: Callable[[str], str],
    *,
    paths: Iterable[str] | None = None,
    max_zones: int = 64,
) -> LinuxThermalState:
    """Use only critical/hot trip points; unknown zones prevent false normality."""
    if not callable(read_text):
        raise TypeError("read_text must be callable")
    if type(max_zones) is not int or not 1 <= max_zones <= 64:
        raise ThermalTelemetryError("invalid thermal zone budget")
    selected = list(islice(
        glob.iglob("/sys/class/thermal/thermal_zone[0-9]*") if paths is None else paths,
        max_zones + 1,
    ))
    if len(selected) > max_zones:
        return LinuxThermalState(None, None, 0, "unavailable")
    if len(set(selected)) != len(selected):
        return LinuxThermalState(None, None, 0, "unavailable")
    minimum: int | None = None
    unknown = False
    measured = 0
    for path in sorted(selected):
        if type(path) is not str or not re.fullmatch(r"/sys/class/thermal/thermal_zone[0-9]+", path):
            raise ThermalTelemetryError("invalid thermal sysfs path")
        try:
            current = _millidegrees(read_text(path + "/temp"))
        except (OSError, ValueError, UnicodeError):
            unknown = True
            continue
        critical: list[int] = []
        for index in range(16):
            try:
                kind = read_text(path + f"/trip_point_{index}_type").strip().lower()
                if kind not in {"critical", "hot"}:
                    continue
                limit = _millidegrees(read_text(path + f"/trip_point_{index}_temp"))
                critical.append(limit)
            except FileNotFoundError:
                continue
            except (OSError, ValueError, UnicodeError):
                unknown = True
        if not critical:
            unknown = True
            continue
        headroom = min(critical) - current
        minimum = headroom if minimum is None else min(minimum, headroom)
        measured += 1
    if minimum is None:
        return LinuxThermalState(None, None, 0, "unavailable")
    if minimum <= 5000:
        level = "critical"
    elif minimum <= 15000:
        level = "elevated"
    elif unknown:
        level = None
    else:
        level = "normal"
    return LinuxThermalState(level, minimum / 1000.0, measured, "linux_sysfs_thermal")

"""Linux CPU/SOC thermal trip telemetry for adaptive offline inference staging.

Only kernel-reported trip temperatures authorize a thermal hold. Unknown
sensor types, absent trips and non-Linux platforms never invent thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
import math
import os
import re
import stat
from pathlib import Path
import sys
import threading


@dataclass(frozen=True, slots=True)
class CPUThermalSensor:
    zone: str
    kind: str
    temperature_c: float
    trip_c: float | None

    def __post_init__(self) -> None:
        # Thermal sensor identity is used to fence CPU authorization.
        # Reject injected non-string or control-text identities.
        if any(
            type(value) is not str or not 1 <= len(value) <= 128
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) > 126 for ch in value)
            for value in (self.zone, self.kind)
        ):
            raise ValueError("invalid thermal sensor identity")
        for value in (self.temperature_c, self.trip_c):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not -50 <= value <= 200
            ):
                raise ValueError("invalid measured thermal value")


def _open_pinned_root(root: str | Path) -> int:
    """Open every Linux sysfs ancestor without following a symlink."""
    path = os.fspath(root)
    if type(path) is not str or not path.startswith("/") or "\x00" in path:
        raise ValueError("absolute sysfs root required")
    if any(part in (".", "..") for part in path.split("/")):
        raise ValueError("sysfs parent traversal forbidden")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open("/", flags)
    try:
        for part in path.split("/"):
            if not part:
                continue
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_pinned_ascii(zone_fd: int, name: str, limit: int) -> str:
    """Descriptor/name identity-fenced bounded sysfs attribute read."""
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError("invalid thermal attribute name")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(name, flags, dir_fd=zone_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("non-regular thermal attribute")
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=zone_fd, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_mtime_ns, s.st_ctime_ns)
        if (identity(before) != identity(after) or identity(after) != identity(named)
                or not raw or len(raw) > limit):
            raise ValueError("thermal attribute changed or exceeded read bound")
        return raw.decode("ascii", errors="strict").strip()
    finally:
        os.close(fd)


def _pinned_temperature(zone_fd: int, name: str) -> float | None:
    try:
        raw = _read_pinned_ascii(zone_fd, name, 64)
        digits = raw[1:] if raw.startswith("-") else raw
        if not digits or any(ch < "0" or ch > "9" for ch in digits):
            return None
        value = int(raw) / 1000
        return value if -50 <= value <= 200 else None
    except (OSError, UnicodeError, ValueError):
        return None


def probe_cpu_thermal(root: str | Path = "/sys/devices/virtual/thermal") -> tuple[CPUThermalSensor, ...]:
    """Fail-closed, descriptor-pinned Linux CPU/SOC thermal inventory.

    Missing or mismatched trip type/temperature pairs, symlinks, unexpected
    names, inode replacement and oversized topology invalidate the whole
    observation. No GPU/SoC hardware qualification is inferred.
    """
    if sys.platform != "linux":
        return ()
    try:
        root_fd = _open_pinned_root(root)
    except (OSError, ValueError, TypeError):
        return ()
    try:
        zone_names: list[str] = []
        with os.scandir(root_fd) as entries:
            for entry in entries:
                name = entry.name
                if not name.startswith("thermal_zone"):
                    continue
                if (not re.fullmatch(r"thermal_zone[0-9]+", name)
                        or len(zone_names) >= 256):
                    return ()
                zone_names.append(name)
        result: list[CPUThermalSensor] = []
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        for name in sorted(zone_names):
            zone_fd = os.open(name, flags, dir_fd=root_fd)
            try:
                kind = _read_pinned_ascii(zone_fd, "type", 128)
                if not kind:
                    return ()
                if not any(word in kind.lower()
                           for word in ("cpu", "soc", "package", "x86_pkg")):
                    continue
                temp = _pinned_temperature(zone_fd, "temp")
                if temp is None:
                    return ()
                trip_temps: set[str] = set()
                trip_types: set[str] = set()
                scanned = 0
                with os.scandir(zone_fd) as entries:
                    for entry in entries:
                        scanned += 1
                        if scanned > 4096:
                            return ()
                        attr = entry.name
                        if not attr.startswith("trip_point_"):
                            continue
                        if attr.endswith("_temp") or "_temp" in attr:
                            if not re.fullmatch(r"trip_point_[0-9]+_temp", attr):
                                return ()
                            trip_temps.add(attr[len("trip_point_"):-len("_temp")])
                        elif attr.endswith("_type") or "_type" in attr:
                            if not re.fullmatch(r"trip_point_[0-9]+_type", attr):
                                return ()
                            trip_types.add(attr[len("trip_point_"):-len("_type")])
                if trip_temps != trip_types or len(trip_temps) > 64:
                    return ()
                trip: float | None = None
                for index in sorted(trip_temps, key=int):
                    trip_type = _read_pinned_ascii(zone_fd,
                        "trip_point_" + index + "_type", 64).lower()
                    if trip_type not in {"active", "passive", "hot", "critical"}:
                        return ()
                    measured = _pinned_temperature(zone_fd,
                        "trip_point_" + index + "_temp")
                    if measured is None:
                        return ()
                    trip = measured if trip is None else min(trip, measured)
                result.append(CPUThermalSensor(name, kind, temp, trip))
            finally:
                os.close(zone_fd)
        return tuple(result)
    except (OSError, ValueError, UnicodeError):
        return ()
    finally:
        os.close(root_fd)


class CPUThermalController:
    """Measured trip-point hysteresis; unknown samples preserve existing holds."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._last: tuple[CPUThermalSensor, ...] = ()
        self._baseline: tuple[tuple[str, str], ...] | None = None
        self._identity_drift = False
        self._hold = False
        self._transitions = 0

    def observe(self, sensors: tuple[CPUThermalSensor, ...]) -> None:
        if type(sensors) is not tuple or any(
            not isinstance(sensor, CPUThermalSensor) for sensor in sensors
        ):
            raise TypeError("typed thermal sensors required")
        with self._lock:
            self._last = sensors
            before = self._hold
            identity = tuple(sorted((s.zone, s.kind) for s in sensors))
            if sensors and self._baseline is None:
                if len(set(identity)) != len(identity):
                    self._identity_drift = True
                else:
                    self._baseline = identity
            elif self._baseline is not None and identity != self._baseline:
                # Sensor disappearance, substitution or kind drift must not
                # clear a previously measured thermal hold. Recovery requires
                # a new app-owned controller and fresh hardware qualification.
                self._identity_drift = True
            measured = [sensor for sensor in sensors if sensor.trip_c is not None]
            if self._identity_drift or (sensors and len(measured) != len(sensors)):
                self._hold = True
            elif measured:
                if any(sensor.temperature_c >= sensor.trip_c for sensor in measured):
                    self._hold = True
                elif all(sensor.temperature_c <= sensor.trip_c - 5 for sensor in measured):
                    self._hold = False
            if before != self._hold:
                self._transitions += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema": "skeleton.offline.cpu-thermal.v1",
                "measured": bool(self._last),
                "trip_measured": bool(self._last) and all(
                    s.trip_c is not None for s in self._last
                ),
                "sensor_identity_drift": self._identity_drift,
                "thermal_backpressure": self._hold,
                "transitions": self._transitions,
                "sensors": [
                    {
                        "zone": s.zone, "kind": s.kind,
                        "temperature_c": s.temperature_c,
                        "trip_c": s.trip_c,
                    }
                    for s in self._last
                ],
            }


__all__ = ["CPUThermalSensor", "CPUThermalController", "probe_cpu_thermal"]

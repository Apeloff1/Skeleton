"""Linux CPU/SOC thermal trip telemetry for adaptive offline inference staging.

Only kernel-reported trip temperatures authorize a thermal hold. Unknown
sensor types, absent trips and non-Linux platforms never invent thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
import math
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
        if not self.zone or not self.kind or len(self.zone) > 128 or len(self.kind) > 128:
            raise ValueError("invalid thermal sensor identity")
        for value in (self.temperature_c, self.trip_c):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not -50 <= value <= 200
            ):
                raise ValueError("invalid measured thermal value")


def _temperature(path: Path) -> float | None:
    try:
        raw = path.read_text(encoding="ascii").strip()
        milli = int(raw)
        value = milli / 1000
        return value if -50 <= value <= 200 else None
    except (OSError, UnicodeError, ValueError):
        return None


def probe_cpu_thermal(root: str | Path = "/sys/class/thermal") -> tuple[CPUThermalSensor, ...]:
    """Bounded Linux sysfs probe; only CPU/SOC zones with valid temperatures."""
    if sys.platform != "linux":
        return ()
    try:
        zones = sorted(islice(Path(root).glob("thermal_zone[0-9]*"), 257))
    except OSError:
        return ()
    if len(zones) > 256:
        return ()  # Unbounded host topology is not a trustworthy sample.
    result: list[CPUThermalSensor] = []
    for zone in zones:
        try:
            kind = (zone / "type").read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            continue
        if not kind or len(kind) > 128 or not any(
            word in kind.lower() for word in ("cpu", "soc", "package", "x86_pkg")
        ):
            continue
        temp = _temperature(zone / "temp")
        if temp is None:
            continue
        trip: float | None = None
        try:
            candidates = sorted(islice(zone.glob("trip_point_*_temp"), 65))
        except OSError:
            candidates = []
        if len(candidates) > 64:
            continue
        for candidate in candidates:
            kind_path = candidate.with_name(candidate.name.replace("_temp", "_type"))
            try:
                trip_type = kind_path.read_text(encoding="ascii").strip().lower()
            except (OSError, UnicodeError):
                continue
            if trip_type not in {"passive", "hot", "critical"}:
                continue
            measured = _temperature(candidate)
            if measured is not None:
                trip = measured if trip is None else min(trip, measured)
        try:
            result.append(CPUThermalSensor(zone.name, kind, temp, trip))
        except ValueError:
            continue
    return tuple(result)


class CPUThermalController:
    """Measured trip-point hysteresis; unknown samples preserve existing holds."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._last: tuple[CPUThermalSensor, ...] = ()
        self._hold = False
        self._transitions = 0

    def observe(self, sensors: tuple[CPUThermalSensor, ...]) -> None:
        if type(sensors) is not tuple or any(
            not isinstance(sensor, CPUThermalSensor) for sensor in sensors
        ):
            raise TypeError("typed thermal sensors required")
        with self._lock:
            self._last = sensors
            measured = [sensor for sensor in sensors if sensor.trip_c is not None]
            if not measured:
                return
            before = self._hold
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
                "trip_measured": any(s.trip_c is not None for s in self._last),
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

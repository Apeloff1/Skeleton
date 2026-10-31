"""OS-measured Linux I/O pressure for adaptive local source streaming.

The Linux PSI some/full avg10 percentages describe observed stalls, not disk
throughput, free bytes or a GPU allocation budget. Non-Linux is unsupported.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys
import threading


@dataclass(frozen=True, slots=True)
class IOPressure:
    scope: str
    some_avg10: float
    full_avg10: float
    some_total_us: int
    full_total_us: int

    def __post_init__(self) -> None:
        if self.scope not in {"cgroup", "host"}:
            raise ValueError("unknown IO pressure scope")
        for key in ("some_avg10", "full_avg10"):
            value = getattr(self, key)
            if (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or not 0 <= value <= 100):
                raise ValueError("invalid IO stall percentage")
        for key in ("some_total_us", "full_total_us"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError("invalid IO stall counter")


def _parse_psi(raw: str, scope: str) -> IOPressure | None:
    lines: dict[str, dict[str, str]] = {}
    try:
        for line in raw.splitlines():
            parts = line.split()
            if not parts or parts[0] in lines:
                return None
            fields = dict(part.split("=", 1) for part in parts[1:])
            if len(fields) != len(parts) - 1:
                return None
            lines[parts[0]] = fields
        if not {"some", "full"} <= lines.keys():
            return None
        return IOPressure(
            scope=scope,
            some_avg10=float(lines["some"]["avg10"]),
            full_avg10=float(lines["full"]["avg10"]),
            some_total_us=int(lines["some"]["total"]),
            full_total_us=int(lines["full"]["total"]),
        )
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def probe_io_pressure(
    cgroup_root: str | Path = "/sys/fs/cgroup",
    host_path: str | Path = "/proc/pressure/io",
) -> IOPressure | None:
    """Prefer process cgroup PSI, fall back to host PSI, never invent zero."""
    if sys.platform != "linux":
        return None
    for path, scope in (
        (Path(cgroup_root) / "io.pressure", "cgroup"),
        (Path(host_path), "host"),
    ):
        try:
            raw = path.read_text(encoding="ascii")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError):
            return None
        if len(raw) > 4096:
            return None
        return _parse_psi(raw, scope)
    return None


class IOPressureController:
    """Hysteresis for observed stalls; unknown readings retain prior hold."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sample: IOPressure | None = None
        self._congested = False
        self._observations = 0
        self._transitions = 0

    def observe(self, sample: IOPressure | None) -> None:
        if sample is not None and not isinstance(sample, IOPressure):
            raise TypeError("typed IO pressure required")
        with self._lock:
            self._sample = sample
            self._observations += 1
            if sample is None:
                return
            before = self._congested
            if sample.some_avg10 >= 15 or sample.full_avg10 >= 5:
                self._congested = True
            elif sample.some_avg10 <= 8 and sample.full_avg10 <= 2:
                self._congested = False
            if self._congested != before:
                self._transitions += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            sample = self._sample
            return {
                "schema": "skeleton.offline.io-pressure.v1",
                "measured": sample is not None,
                "scope": sample.scope if sample else None,
                "some_avg10_percent": sample.some_avg10 if sample else None,
                "full_avg10_percent": sample.full_avg10 if sample else None,
                "some_total_us": sample.some_total_us if sample else None,
                "full_total_us": sample.full_total_us if sample else None,
                "congested": self._congested,
                "observations": self._observations,
                "transitions": self._transitions,
            }


__all__ = ["IOPressure", "IOPressureController", "probe_io_pressure"]

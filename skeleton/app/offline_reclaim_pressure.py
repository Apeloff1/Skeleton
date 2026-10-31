"""Measured Linux reclaim/major-fault pressure for offline AI stream admission.

No arbitrary file quota or provider calls. The counters describe observed kernel
reclaim work, not model memory allocations or GPU residency. When telemetry is
missing it cannot authorize additional capacity or clear an existing hold.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import mmap
from pathlib import Path
import sys
import threading
import time
from typing import Mapping

SCHEMA = "skeleton.offline.reclaim-pressure.v1"
_MAX_STAT_BYTES = 64 * 1024
_MIN_INTERVAL_NS = 100_000_000
_RECOVERY_SAMPLES = 3


@dataclass(frozen=True)
class ReclaimCounters:
    scope: str
    scanned_pages: int
    reclaimed_pages: int
    major_faults: int

    def __post_init__(self) -> None:
        if self.scope not in {"cgroup_v2", "host_vmstat"}:
            raise ValueError("unknown kernel counter scope")
        if any(
            type(value) is not int or value < 0
            for value in (self.scanned_pages, self.reclaimed_pages, self.major_faults)
        ):
            raise ValueError("kernel counters must be non-negative integers")


def _read_stat(path: Path) -> dict[str, int] | None:
    """Read only a bounded, plain-text kernel stat file.

    Duplicated keys and non-decimal values are rejected instead of silently
    selecting the most convenient reading.
    """
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_STAT_BYTES + 1)
        if len(raw) > _MAX_STAT_BYTES:
            return None
        lines = raw.decode("ascii", errors="strict").splitlines()
    except (OSError, UnicodeError):
        return None
    counters: dict[str, int] = {}
    for line in lines:
        fields = line.split()
        if len(fields) != 2 or not fields[0].isidentifier() or not fields[1].isdecimal():
            return None
        if fields[0] in counters:
            return None
        counters[fields[0]] = int(fields[1])
    return counters if counters else None


def _host_total(values: Mapping[str, int], prefix: str) -> int | None:
    # Never sum a total with its subcategories: several kernel versions expose
    # both, which would double count reclaim activity.
    if prefix in values:
        return values[prefix]
    components = (prefix + "_kswapd", prefix + "_direct")
    if all(key in values for key in components):
        return sum(values[key] for key in components)
    return None


def probe_reclaim_counters(
    cgroup_path: str | Path = "/sys/fs/cgroup/memory.stat",
    host_path: str | Path = "/proc/vmstat",
) -> ReclaimCounters | None:
    """Prefer current cgroup's counters; label host fallback explicitly."""
    if sys.platform != "linux":
        return None
    cgroup = _read_stat(Path(cgroup_path))
    if cgroup is not None and all(
        key in cgroup for key in ("pgscan", "pgsteal", "pgmajfault")
    ):
        return ReclaimCounters(
            "cgroup_v2", cgroup["pgscan"], cgroup["pgsteal"], cgroup["pgmajfault"]
        )
    host = _read_stat(Path(host_path))
    if host is None:
        return None
    scanned = _host_total(host, "pgscan")
    reclaimed = _host_total(host, "pgsteal")
    major = host.get("pgmajfault")
    if scanned is None or reclaimed is None or major is None:
        return None
    return ReclaimCounters("host_vmstat", scanned, reclaimed, major)


class ReclaimPressureController:
    """Rate-normalized, hysteretic read-only pressure admission observer.

    A fast rise blocks high fan-out and shared-memory GPU plans. Three
    independent quiet intervals are required to clear the hold. Counter
    resets, missing telemetry and scope changes cannot fabricate recovery.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._last: ReclaimCounters | None = None
        self._last_ns: int | None = None
        self._hold = False
        self._quiet = 0
        self._samples = 0
        self._resets = 0
        self._scope = "unavailable"
        self._scan_rate: float | None = None
        self._fault_rate: float | None = None
        self._efficiency: float | None = None

    def observe(
        self, sample: ReclaimCounters | None, *,
        physical_ram_bytes: int, now_ns: int | None = None,
    ) -> None:
        if type(physical_ram_bytes) is not int or physical_ram_bytes <= 0:
            raise ValueError("measured physical RAM required")
        if sample is not None and not isinstance(sample, ReclaimCounters):
            raise ValueError("typed kernel counter sample required")
        instant = time.monotonic_ns() if now_ns is None else now_ns
        if type(instant) is not int or instant < 0:
            raise ValueError("monotonic timestamp required")
        with self._lock:
            self._samples += 1
            if sample is None:
                self._last = None
                self._last_ns = None
                self._scope = "unavailable"
                self._scan_rate = None
                self._fault_rate = None
                self._efficiency = None
                # Unknown is not a calm sample; keep any existing hold.
                return
            self._scope = sample.scope
            previous, previous_ns = self._last, self._last_ns
            if (
                previous is None or previous_ns is None
                or sample.scope != previous.scope
                or instant <= previous_ns
                or sample.scanned_pages < previous.scanned_pages
                or sample.reclaimed_pages < previous.reclaimed_pages
                or sample.major_faults < previous.major_faults
            ):
                if previous is not None:
                    self._resets += 1
                self._last = sample
                self._last_ns = instant
                self._scan_rate = None
                self._fault_rate = None
                self._efficiency = None
                return
            elapsed = instant - previous_ns
            if elapsed < _MIN_INTERVAL_NS:
                # Keep the older baseline to avoid an exaggerated near-zero
                # denominator on rapid successive HTTP/CLI observations.
                return
            scanned = sample.scanned_pages - previous.scanned_pages
            reclaimed = sample.reclaimed_pages - previous.reclaimed_pages
            faults = sample.major_faults - previous.major_faults
            physical_pages = max(1, physical_ram_bytes // mmap.PAGESIZE)
            seconds = elapsed / 1_000_000_000
            scan_fraction = scanned / physical_pages / seconds
            fault_fraction = faults / physical_pages / seconds
            efficiency = min(1.0, reclaimed / scanned) if scanned else None
            self._scan_rate = scan_fraction
            self._fault_rate = fault_fraction
            self._efficiency = efficiency
            stressed = (
                (scan_fraction >= 0.02 and efficiency is not None and efficiency < 0.75)
                or fault_fraction >= 0.0005
            )
            if stressed:
                self._hold = True
                self._quiet = 0
            else:
                self._quiet += 1
                if self._quiet >= _RECOVERY_SAMPLES:
                    self._hold = False
            self._last = sample
            self._last_ns = instant

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema": SCHEMA,
                "scope": self._scope,
                "backpressure": self._hold,
                "quiet_intervals": self._quiet,
                "samples": self._samples,
                "counter_resets": self._resets,
                "scanned_ram_fraction_per_s": (
                    None if self._scan_rate is None else round(self._scan_rate, 8)
                ),
                "major_fault_ram_fraction_per_s": (
                    None if self._fault_rate is None else round(self._fault_rate, 8)
                ),
                "reclaim_efficiency": (
                    None if self._efficiency is None else round(self._efficiency, 6)
                ),
                "telemetry_authority": "kernel_counters_observational_only",
            }


__all__ = ["ReclaimCounters", "ReclaimPressureController", "probe_reclaim_counters", "SCHEMA"]

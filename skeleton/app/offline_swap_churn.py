"""Measured Linux host swap page churn for adaptive offline source streaming.

Swap availability is not physical RAM. These kernel counters are cumulative;
the controller derives page I/O rates only from monotonic observed deltas.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys
import threading
import time
from typing import Callable


@dataclass(frozen=True, slots=True)
class SwapCounters:
    pages_in: int
    pages_out: int

    def __post_init__(self) -> None:
        if (type(self.pages_in) is not int or self.pages_in < 0
                or type(self.pages_out) is not int or self.pages_out < 0):
            raise ValueError("invalid Linux swap page counters")


def probe_swap_counters(path: str | Path = "/proc/vmstat") -> SwapCounters | None:
    """Read host-wide pswpin/pswpout; no Linux procfs means unknown."""
    if sys.platform != "linux":
        return None
    try:
        with open(path, encoding="ascii") as handle:
            values: dict[str, int] = {}
            for line in handle:
                parts = line.split()
                if len(parts) != 2:
                    return None
                if parts[0] not in {"pswpin", "pswpout"}:
                    continue
                if parts[0] in values or not parts[1].isascii() or not parts[1].isdecimal():
                    return None
                values[parts[0]] = int(parts[1])
        if set(values) != {"pswpin", "pswpout"}:
            return None
        return SwapCounters(values["pswpin"], values["pswpout"])
    except (OSError, UnicodeError, ValueError):
        return None


class SwapChurnController:
    """Adaptive swap-thrash pressure using measured RAM and page size.

    A high rate relative to total physical RAM throttles future source reads.
    Recovery uses a lower threshold. Counter reset or missing telemetry cannot
    silently release a previously observed pressure hold.
    """

    def __init__(
        self, *, clock_ns: Callable[[], int] = time.monotonic_ns,
        page_size: int | None = None,
    ) -> None:
        if not callable(clock_ns):
            raise TypeError("monotonic clock required")
        if page_size is None:
            try:
                page_size = int(os.sysconf("SC_PAGE_SIZE"))
            except (AttributeError, OSError, ValueError):
                page_size = None
        if page_size is not None and (type(page_size) is not int or page_size <= 0):
            raise ValueError("invalid measured page size")
        self._clock = clock_ns
        self._page_size = page_size
        self._lock = threading.RLock()
        self._previous: tuple[SwapCounters, int] | None = None
        self._last: SwapCounters | None = None
        self._last_now = 0
        self._rate_bps: int | None = None
        self._congested = False
        self._transitions = 0

    def observe(self, sample: SwapCounters | None, *, physical_ram_bytes: int) -> None:
        if sample is not None and not isinstance(sample, SwapCounters):
            raise TypeError("typed swap counters required")
        if sample is not None and self._page_size is None:
            raise ValueError("measured swap page size unavailable")
        if type(physical_ram_bytes) is not int or physical_ram_bytes <= 0:
            raise ValueError("measured physical RAM required")
        with self._lock:
            now = self._clock()
            if type(now) is not int or now < self._last_now:
                raise ValueError("nonmonotonic swap observation clock")
            self._last_now = now
            self._last = sample
            if sample is None:
                return
            previous = self._previous
            self._previous = (sample, now)
            if previous is None:
                return
            old, start = previous
            if sample.pages_in < old.pages_in or sample.pages_out < old.pages_out:
                return
            elapsed = now - start
            if elapsed <= 0:
                return
            delta = ((sample.pages_in - old.pages_in)
                     + (sample.pages_out - old.pages_out))
            self._rate_bps = delta * self._page_size * 1_000_000_000 // elapsed
            before = self._congested
            if self._rate_bps >= max(1, physical_ram_bytes // 500):
                self._congested = True
            elif self._rate_bps <= physical_ram_bytes // 2000:
                self._congested = False
            if self._congested != before:
                self._transitions += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema": "skeleton.offline.swap-churn.v1",
                "measured": self._last is not None,
                "scope": "host" if self._last else None,
                "pages_in": self._last.pages_in if self._last else None,
                "pages_out": self._last.pages_out if self._last else None,
                "page_bytes": self._page_size,
                "observed_bytes_per_second": self._rate_bps,
                "backpressure": self._congested,
                "transitions": self._transitions,
            }


__all__ = ["SwapCounters", "SwapChurnController", "probe_swap_counters"]

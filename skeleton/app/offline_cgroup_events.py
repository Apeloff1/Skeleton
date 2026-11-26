"""Linux cgroup-v2 event pressure for the canonical offline resource fabric."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import threading
import time
from typing import Callable


@dataclass(frozen=True, slots=True)
class CgroupEvents:
    scope: str
    high: int
    maximum: int
    oom: int
    oom_kill: int

    def __post_init__(self) -> None:
        if self.scope not in ("local", "hierarchical"):
            raise ValueError("unknown cgroup scope")
        for key in ("high", "maximum", "oom", "oom_kill"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError("invalid cgroup event counter")


def probe_cgroup_events(root: str | Path = "/sys/fs/cgroup") -> CgroupEvents | None:
    """Counters are cumulative; unavailable telemetry is not a zero reading."""
    if sys.platform != "linux":
        return None
    for name, scope in (("memory.events.local", "local"),
                        ("memory.events", "hierarchical")):
        try:
            raw = (Path(root) / name).read_text(encoding="ascii")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError):
            return None
        if len(raw) > 4096:
            return None
        values: dict[str, int] = {}
        for line in raw.splitlines():
            parts = line.split()
            if (len(parts) != 2 or parts[0] in values
                    or not parts[1].isascii() or not parts[1].isdecimal()):
                return None
            values[parts[0]] = int(parts[1])
        if not {"high", "max", "oom", "oom_kill"} <= values.keys():
            return None
        return CgroupEvents(scope, values["high"], values["max"],
                            values["oom"], values["oom_kill"])
    return None


class CgroupPressureTracker:
    """Lock-protected deltas and monotonic recovery holds, not a memory quota."""

    def __init__(self, *, clock_ns: Callable[[], int] = time.monotonic_ns):
        self._clock = clock_ns
        self._lock = threading.RLock()
        self._previous: CgroupEvents | None = None
        self._last: CgroupEvents | None = None
        self._high_until = 0
        self._oom_until = 0
        self._last_now = 0
        self._high_changes = 0
        self._oom_changes = 0

    def _now(self) -> int:
        now = self._clock()
        if type(now) is not int or now < self._last_now:
            raise ValueError("nonmonotonic cgroup observation clock")
        self._last_now = now
        return now

    def sample(self, events: CgroupEvents | None) -> None:
        if events is not None and not isinstance(events, CgroupEvents):
            raise TypeError("typed cgroup events required")
        with self._lock:
            now = self._now()
            previous = self._previous
            self._last = events
            if events is None:
                return
            self._previous = events
            if previous is None or previous.scope != events.scope:
                return
            if any(getattr(events, key) < getattr(previous, key)
                   for key in ("high", "maximum", "oom", "oom_kill")):
                return  # Counter reset must not clear an existing hold.
            if events.high > previous.high or events.maximum > previous.maximum:
                self._high_changes += 1
                self._high_until = max(self._high_until, now + 5_000_000_000)
            if events.oom > previous.oom or events.oom_kill > previous.oom_kill:
                self._oom_changes += 1
                self._oom_until = max(self._oom_until, now + 30_000_000_000)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            now = self._now()
            event = self._last
            return {
                "schema": "skeleton.offline.cgroup-pressure.v1",
                "measured": event is not None,
                "scope": event.scope if event else None,
                "high_events": event.high if event else None,
                "oom_events": event.oom if event else None,
                "oom_kill_events": event.oom_kill if event else None,
                "high_transitions": self._high_changes,
                "oom_transitions": self._oom_changes,
                "high_backpressure": now < self._high_until,
                "oom_backpressure": now < self._oom_until,
            }


__all__ = ["CgroupEvents", "CgroupPressureTracker", "probe_cgroup_events"]

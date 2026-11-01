"""Cgroup-v2 event delta monitor with bounded, fork-safe fail-closed custody.

Cumulative kernel counters cannot establish current pressure without a prior
same-process, same-cgroup, monotonic sample. A zero delta is not authorization.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from threading import Lock
from time import monotonic_ns

from .long_context_cgroup import _identity
from .long_context_host_pressure import _secure_directory

_MAX_EVENT_BYTES = 4096
_LINE = re.compile(rb"([a-z_]{1,32}) (0|[1-9][0-9]{0,18})")
_REQUIRED = {
    "memory.events": frozenset(("oom", "oom_kill")),
    "cpu.stat": frozenset(("nr_throttled",)),
}
_MAX_COUNT = 2**63 - 1


def _read_events(directory: int, name: str) -> tuple[dict[str, int], tuple[int, ...]]:
    if name not in _REQUIRED:
        raise ValueError("unsupported event source")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW |
                 getattr(os, "O_NONBLOCK", 0), dir_fd=directory)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid not in (0, os.geteuid())
                or before.st_nlink != 1):
            raise OSError("untrusted event inode")
        raw = os.read(fd, _MAX_EVENT_BYTES + 1)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not raw or len(raw) > _MAX_EVENT_BYTES
                or _identity(before) != _identity(after)
                or _identity(after) != _identity(named)):
            raise OSError("event source replaced or mutated")
        lines = raw.splitlines()
        if not 1 <= len(lines) <= 64:
            raise ValueError("invalid event line count")
        result: dict[str, int] = {}
        for line in lines:
            match = _LINE.fullmatch(line)
            if match is None:
                raise ValueError("invalid event line")
            key = match.group(1).decode("ascii")
            if key in result:
                raise ValueError("duplicate event counter")
            value = int(match.group(2))
            if value > _MAX_COUNT:
                raise ValueError("unbounded event counter")
            result[key] = value
        if not _REQUIRED[name].issubset(result):
            raise ValueError("missing required event counters")
        return result, _identity(after)
    finally:
        os.close(fd)


def _sample(root: Path) -> tuple[tuple[int, ...], dict[str, int]]:
    if os.name != "posix":
        raise OSError("cgroup event custody unavailable")
    directory = _secure_directory(root)
    try:
        info = os.fstat(directory)
        memory, memory_inode = _read_events(directory, "memory.events")
        cpu, cpu_inode = _read_events(directory, "cpu.stat")
        # Detect a source replaced after its own read but before the pair
        # is assembled. Cross-sample identities also fence silent resets.
        for name, expected in (("memory.events", memory_inode),
                               ("cpu.stat", cpu_inode)):
            named = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if _identity(named) != expected:
                raise OSError("event source replaced after read")
        reopened = _secure_directory(root)
        try:
            current = os.fstat(reopened)
            if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                raise OSError("cgroup event directory replaced")
        finally:
            os.close(reopened)
        return (
            info.st_dev, info.st_ino,
            memory_inode[0], memory_inode[1],
            cpu_inode[0], cpu_inode[1],
        ), {
            "oom": memory["oom"],
            "oom_kill": memory["oom_kill"],
            "nr_throttled": cpu["nr_throttled"],
        }
    finally:
        os.close(directory)


class CgroupEventMonitor:
    """Bounded in-memory transition monitor; never an execution admission gate.

    Transitions: baseline_required -> observed -> baseline_required on any
    invalid sample, counter reset, cgroup replacement or expired interval.
    A forked child must create a new monitor; it may not inherit a baseline.
    """

    def __init__(self, root: Path = Path("/sys/fs/cgroup"),
                 *, max_interval_ns: int = 5_000_000_000):
        if (type(max_interval_ns) is not int or
                not 1 <= max_interval_ns <= 60_000_000_000):
            raise ValueError("invalid sample interval")
        self._root = root
        self._max_interval_ns = max_interval_ns
        self._pid = os.getpid()
        self._lock = Lock()
        self._previous: tuple[tuple[int, ...], dict[str, int], int] | None = None

    def sample(self) -> dict[str, object]:
        if os.getpid() != self._pid:
            raise OSError("inherited cgroup monitor after fork")
        with self._lock:
            reasons: list[str] = []
            deltas: dict[str, int] | None = None
            state = "baseline_required"
            try:
                identity, counters = _sample(self._root)
                now = monotonic_ns()
                if type(now) is not int or now < 0:
                    raise ValueError("invalid monotonic clock")
                previous = self._previous
                if previous is None:
                    reasons.append("first_sample_unproven")
                else:
                    old_identity, old_counters, old_ns = previous
                    if old_identity != identity:
                        reasons.append("cgroup_identity_changed")
                    elif now <= old_ns:
                        reasons.append("monotonic_clock_regressed")
                    elif now - old_ns > self._max_interval_ns:
                        reasons.append("sample_interval_expired")
                    elif any(counters[k] < old_counters[k] for k in counters):
                        reasons.append("event_counter_regressed")
                    else:
                        deltas = {k: counters[k] - old_counters[k] for k in counters}
                        state = "observed"
                        if deltas["oom"] or deltas["oom_kill"]:
                            reasons.append("memory_oom_event")
                        if deltas["nr_throttled"]:
                            reasons.append("cpu_throttle_event")
                self._previous = (identity, counters, now)
            except (OSError, ValueError, OverflowError):
                self._previous = None
                reasons.append("event_observation_unavailable")
            return {
                "schema": "skeleton.ai.cgroup-event-monitor.v1",
                "state": state,
                "reasons": sorted(set(reasons)),
                "event_deltas": deltas,
                "scope_membership_attested": False,
                "pressure_signals_attested": False,
                "is_admission_grant": False,
                "is_execution_lease": False,
                "requires_live_backend_revalidation": True,
            }


__all__ = ["CgroupEventMonitor"]

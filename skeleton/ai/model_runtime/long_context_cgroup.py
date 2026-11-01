"""Bounded, non-authorizing cgroup-v2 CPU and memory pressure observations.

The configured cgroup directory is not proof of the process's membership.
Cgroup PSI and memory counters are sampled separately, not atomically.
No result here may be used as an execution lease or hardware attestation.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat

from .long_context_host_pressure import _avg10, _read_psi, _secure_directory, _state

_MAX_COUNTER_BYTES = 128
_COUNTER = re.compile(rb"(?:0|[1-9][0-9]{0,18})\n?")
_MAX_COUNTER = 2**63 - 1
_SEVERITY = {"normal": 0, "elevated": 1, "critical": 2}


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def _read_counter(directory: int, name: str, *, unlimited: bool = False) -> int | None:
    """Read one pinned cgroup scalar; never trust symlinks or mutable names."""
    if name not in ("memory.current", "memory.max"):
        raise ValueError("unsupported cgroup counter")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(name, flags, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid not in (0, os.geteuid())
                or before.st_nlink != 1):
            raise OSError("untrusted cgroup counter inode")
        raw = os.read(fd, _MAX_COUNTER_BYTES + 1)
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not raw or len(raw) > _MAX_COUNTER_BYTES
                or _identity(before) != _identity(after)
                or _identity(after) != _identity(named)):
            raise OSError("cgroup counter mutated or oversized")
        if unlimited and raw in (b"max", b"max\n"):
            return None
        if _COUNTER.fullmatch(raw) is None:
            raise ValueError("malformed cgroup counter")
        number = int(raw)
        if number > _MAX_COUNTER:
            raise ValueError("cgroup counter exceeds bound")
        return number
    finally:
        os.close(fd)


def _memory_state(current: int, limit: int | None, psi: str) -> str:
    if limit is None:
        return "unknown"
    if limit <= 0:
        raise ValueError("invalid cgroup memory limit")
    if current > limit:
        return "critical"
    percentage = current * 100 // limit
    ratio = "critical" if percentage >= 95 else (
        "elevated" if percentage >= 85 else "normal"
    )
    return max((ratio, psi), key=_SEVERITY.__getitem__)


def observe_cgroup_pressure(
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> dict[str, object]:
    """Read-only diagnostic; fixture root is never a trusted membership proof.

    Unknown, swapped, unsupported or malformed observations remain unknown.
    PSI may be normal while thermal/energy and device safety remain unknown.
    """
    signals = {"cpu": "unknown", "memory": "unknown",
               "thermal": "unknown", "energy": "unknown"}
    source = "unavailable"
    current: int | None = None
    limit: int | None = None
    directory = -1
    try:
        if os.name != "posix":
            raise OSError("cgroup v2 requires POSIX")
        directory = _secure_directory(cgroup_root)
        pinned = os.fstat(directory)
        cpu = _state(_avg10(_read_psi(directory, "cpu")),
                     elevated=10, critical=50)
        memory_psi = _state(_avg10(_read_psi(directory, "memory")),
                            elevated=5, critical=20)
        current = _read_counter(directory, "memory.current")
        limit = _read_counter(directory, "memory.max", unlimited=True)
        if current is None:
            raise ValueError("missing cgroup memory current")
        memory = _memory_state(current, limit, memory_psi)
        # A descriptor pins an inode, not the pathname visible to other users.
        reopened = _secure_directory(cgroup_root)
        try:
            visible = os.fstat(reopened)
            if ((pinned.st_dev, pinned.st_ino) !=
                    (visible.st_dev, visible.st_ino)):
                raise OSError("cgroup directory replaced")
        finally:
            os.close(reopened)
        signals["cpu"] = cpu
        signals["memory"] = memory
        source = "cgroup_v2_root_observation"
    except (OSError, ValueError, OverflowError):
        current = limit = None
    finally:
        if directory >= 0:
            os.close(directory)
    return {
        "schema": "skeleton.ai.long-context-cgroup-pressure.v1",
        "source": source,
        "signals": signals,
        "memory_current_bytes": current,
        "memory_limit_bytes": limit,
        "hold_reasons": sorted(
            key + "_" + value for key, value in signals.items()
            if value != "normal"
        ),
        "scope_membership_attested": False,
        "pressure_signals_attested": False,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "requires_live_backend_revalidation": True,
        "cross_file_snapshot_atomic": False,
    }


__all__ = ["observe_cgroup_pressure"]

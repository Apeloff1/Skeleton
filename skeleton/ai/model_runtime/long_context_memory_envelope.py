"""Read-only bounded Linux RAM/cgroup-v2 headroom observation for offline AI.

A two-sample memory envelope is a diagnostic, never allocation authority.
Unknown or changed kernel telemetry holds. No GPU, M-chip, Windows, or
non-Linux memory qualification is inferred from these counters.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import stat
import sys
from time import monotonic_ns
from typing import Callable

from .long_context_spool import LongContextSpoolError, _canonical

_MAX_COUNTER = 2**63 - 1
_MAX_SAMPLE_NS = 2_000_000_000
_MAX_READ = 16 * 1024
_DEFAULT_RESERVE = 128 * 1024 * 1024
_SCHEMA = "skeleton.ai.long-context-memory-envelope.v1"


def _counter(value: object, label: str, *, allow_zero: bool = True) -> int:
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= _MAX_COUNTER:
        raise LongContextSpoolError("invalid " + label)
    return value


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_gid, info.st_nlink, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def _kernel_read(root: Path, name: str) -> str:
    """Bounded descriptor-relative read, rejecting name/ancestor replacement.

    Kernel pseudo-files can report st_size=0 while returning bytes, so
    validate their descriptor identity and read bound rather than st_size.
    """
    if name not in {"meminfo", "memory.current", "memory.max", "memory.high"}:
        raise LongContextSpoolError("invalid kernel memory source")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    directory = os.open(root, flags | os.O_DIRECTORY)
    try:
        directory_before = os.fstat(directory)
        if not stat.S_ISDIR(directory_before.st_mode):
            raise LongContextSpoolError("memory source root not directory")
        fd = os.open(name, flags | getattr(os, "O_NONBLOCK", 0), dir_fd=directory)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_READ:
                raise LongContextSpoolError("memory source not bounded regular file")
            raw = os.read(fd, _MAX_READ + 1)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (len(raw) > _MAX_READ or not raw
                    or _identity(before) != _identity(after)
                    or _identity(after) != _identity(named)):
                raise LongContextSpoolError("memory source changed during read")
        finally:
            os.close(fd)
        visible = os.stat(root, follow_symlinks=False)
        if (_identity(directory_before) != _identity(os.fstat(directory))
                or _identity(directory_before) != _identity(visible)):
            raise LongContextSpoolError("memory source root replaced")
        try:
            return raw.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise LongContextSpoolError("memory source not ASCII") from exc
    finally:
        os.close(directory)


def _meminfo(text: str) -> tuple[int, int]:
    if type(text) is not str or len(text) > _MAX_READ:
        raise LongContextSpoolError("invalid meminfo")
    values: dict[str, int] = {}
    for line in text.splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            parts = line.split()
            if (len(parts) != 3 or parts[2] != "kB"
                    or parts[0] in values or not parts[1].isascii()
                    or not parts[1].isdecimal() or len(parts[1]) > 17):
                raise LongContextSpoolError("malformed meminfo")
            amount = int(parts[1]) * 1024
            values[parts[0]] = _counter(amount, "meminfo bytes", allow_zero=False)
    if set(values) != {"MemTotal:", "MemAvailable:"}:
        raise LongContextSpoolError("missing meminfo fields")
    total, available = values["MemTotal:"], values["MemAvailable:"]
    if available > total:
        raise LongContextSpoolError("meminfo available exceeds total")
    return total, available


def _cgroup_counter(text: str, *, optional_max: bool) -> int | None:
    if type(text) is not str or len(text) > 64:
        raise LongContextSpoolError("invalid cgroup memory counter")
    raw = text.strip()
    if optional_max and raw == "max":
        return None
    if not raw or not raw.isascii() or not raw.isdecimal() or len(raw) > 19:
        raise LongContextSpoolError("malformed cgroup memory counter")
    return _counter(int(raw), "cgroup memory counter")


def _sample(host_root: Path, cgroup_root: Path,
            reader: Callable[[Path, str], str]) -> tuple[int, int, int, int, int | None]:
    total, available = _meminfo(reader(host_root, "meminfo"))
    current = _cgroup_counter(reader(cgroup_root, "memory.current"), optional_max=False)
    maximum = _cgroup_counter(reader(cgroup_root, "memory.max"), optional_max=True)
    high = _cgroup_counter(reader(cgroup_root, "memory.high"), optional_max=True)
    if maximum is None:
        raise LongContextSpoolError("unbounded cgroup memory maximum")
    if current > maximum:
        raise LongContextSpoolError("cgroup memory usage exceeds limit")
    if high is not None and high > maximum:
        high = maximum
    return total, available, current, maximum, high


def observe_memory_envelope(
    *, requested_bytes: int = 0,
    host_root: Path = Path("/proc"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    reserve_bytes: int = _DEFAULT_RESERVE,
    clock: Callable[[], int] = monotonic_ns,
    reader: Callable[[Path, str], str] = _kernel_read,
) -> dict[str, object]:
    """Observe RAM headroom twice; never authorize an inference or allocation.

    A cgroup limit, current usage, or available host memory can change after
    this method returns. Backend must independently check and reserve memory.
    """
    _counter(requested_bytes, "requested bytes")
    _counter(reserve_bytes, "memory reserve")
    if requested_bytes > 1024**3 or reserve_bytes > 1024**4:
        raise LongContextSpoolError("memory envelope budget too large")
    if not callable(reader) or not callable(clock):
        raise LongContextSpoolError("invalid memory observer")
    result: dict[str, object] = {
        "schema": _SCHEMA,
        "state": "hold",
        "reason": "telemetry_unavailable",
        "requested_bytes": requested_bytes,
        "reserve_bytes": reserve_bytes,
        "observed_headroom_bytes": 0,
        "request_observed_sufficient": False,
        "host_available_bytes": None,
        "cgroup_remaining_bytes": None,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "is_memory_reservation": False,
        "cross_source_snapshot_atomic": False,
        "requires_live_backend_revalidation": True,
    }
    if os.name != "posix" or not sys.platform.startswith("linux"):
        result["reason"] = "unsupported_platform"
    else:
        try:
            start = clock()
            _counter(start, "start clock")
            first = _sample(host_root, cgroup_root, reader)
            second = _sample(host_root, cgroup_root, reader)
            end = clock()
            _counter(end, "end clock")
            if end <= start or end - start > _MAX_SAMPLE_NS:
                raise LongContextSpoolError("memory observation clock invalid")
            if first[0] != second[0] or first[3:] != second[3:]:
                raise LongContextSpoolError("memory limit changed during observation")
            total, _, _, maximum, high = second
            effective_max = min(maximum, high) if high is not None else maximum
            host_available = min(first[1], second[1])
            cgroup_used = max(first[2], second[2])
            remaining = max(0, effective_max - cgroup_used)
            headroom = max(0, min(host_available, remaining) - reserve_bytes)
            result.update({
                "state": "observed_headroom",
                "reason": "observed_only",
                "host_total_bytes": total,
                "host_available_bytes": host_available,
                "cgroup_effective_limit_bytes": effective_max,
                "cgroup_remaining_bytes": remaining,
                "observed_headroom_bytes": headroom,
                "request_observed_sufficient": requested_bytes <= headroom,
            })
        except (OSError, ValueError, OverflowError, TypeError, LongContextSpoolError):
            result["reason"] = "telemetry_unavailable"
    result["observation_digest"] = sha256(_canonical(result)).hexdigest()
    return result


__all__ = ["observe_memory_envelope"]

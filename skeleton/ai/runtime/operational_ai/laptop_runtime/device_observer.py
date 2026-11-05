"""Bounded, read-only Linux/WSL2 host and cgroup memory telemetry.

This observer never allocates a model, changes resource limits or certifies a
device. A container/WSL2 cgroup can be much smaller than /proc/meminfo's
host-wide figure; a known cap must reduce the *observed* free-memory estimate.
Unknown or malformed kernel telemetry is a hold, never an invented capacity.
"""
from __future__ import annotations

import os
from pathlib import Path

from .contracts import refuse

_MAX_MEMORY = 1 << 64
_CGROUP_V2_LIMIT = "/sys/fs/cgroup/memory.max"
_CGROUP_V2_CURRENT = "/sys/fs/cgroup/memory.current"
_CGROUP_V1_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
_CGROUP_V1_CURRENT = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
_MISSING = object()


def _kernel_integer(path: str, *, allow_max: bool = False):
    """Read a fixed kernel telemetry path with NOFOLLOW and finite bytes."""
    if (type(path) is not str or not path.startswith("/sys/fs/cgroup/")
            or ".." in Path(path).parts):
        refuse("untrusted kernel telemetry path")
    if not hasattr(os, "O_NOFOLLOW"):
        refuse("kernel nofollow support is required")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return _MISSING
    except OSError:
        refuse("kernel telemetry descriptor unavailable")
    try:
        raw = os.read(descriptor, 128)
        extra = os.read(descriptor, 1)
    except OSError:
        refuse("kernel telemetry read failed")
    finally:
        os.close(descriptor)
    if extra or not raw:
        refuse("unbounded or empty kernel telemetry")
    try:
        number = raw.strip().decode("ascii", "strict")
    except UnicodeError:
        refuse("kernel telemetry is not ASCII")
    if allow_max and number == "max":
        return None
    if not number.isascii() or not number.isdecimal():
        refuse("malformed kernel memory counter")
    result = int(number)
    if result < 0 or result > _MAX_MEMORY:
        refuse("kernel memory counter out of bounds")
    return result


def _cgroup_reading():
    """Return (version, limit, current), with explicit unlimited/absent cases."""
    limit = _kernel_integer(_CGROUP_V2_LIMIT, allow_max=True)
    if limit is not _MISSING:
        usage = _kernel_integer(_CGROUP_V2_CURRENT)
        if usage is _MISSING:
            refuse("incomplete cgroup v2 memory telemetry")
        if limit is not None and usage > limit:
            refuse("cgroup memory use exceeds reported limit")
        return 2, limit, usage
    limit = _kernel_integer(_CGROUP_V1_LIMIT)
    if limit is _MISSING:
        return None, None, None
    usage = _kernel_integer(_CGROUP_V1_CURRENT)
    if usage is _MISSING:
        refuse("incomplete cgroup v1 memory telemetry")
    # Linux v1 uses a very large page-aligned sentinel for an unlimited
    # cgroup, rather than v2's literal 'max'.
    if limit >= (1 << 60):
        return 1, None, usage
    if usage > limit:
        refuse("cgroup memory use exceeds reported limit")
    return 1, limit, usage


def _parse_meminfo(raw: str) -> dict[str, int]:
    if type(raw) is not str or len(raw) > 4096:
        refuse("unbounded host memory telemetry")
    expected = frozenset(("MemTotal", "MemAvailable", "SwapFree"))
    values: dict[str, int] = {}
    for line in raw.splitlines():
        key, sep, value = line.partition(":")
        if not sep or key not in expected:
            continue
        if key in values:
            refuse("duplicate host memory telemetry")
        tokens = value.strip().split()
        if (len(tokens) != 2 or tokens[1] != "kB"
                or not tokens[0].isascii() or not tokens[0].isdecimal()):
            refuse("malformed host memory telemetry")
        number = int(tokens[0])
        if number > _MAX_MEMORY // 1024:
            refuse("host memory counter overflow")
        values[key] = number * 1024
    if set(values) != expected:
        refuse("incomplete host memory telemetry")
    if (values["MemTotal"] <= 0
            or values["MemAvailable"] > values["MemTotal"]):
        refuse("invalid host available-memory reading")
    return values


def inspect_device(state_dir):
    """Observe an actual private state location without qualifying hardware."""
    if os.name != "posix":
        refuse("unknown device telemetry is an admission hold")
    if not isinstance(state_dir, (str, Path)):
        refuse("absolute state telemetry path required")
    if (not Path(state_dir).is_absolute() or ".." in Path(state_dir).parts
            or chr(0) in str(state_dir)):
        refuse("absolute state telemetry path required")
    try:
        with open("/proc/meminfo", "rt", encoding="ascii") as handle:
            meminfo = handle.read(4097)
        values = _parse_meminfo(meminfo)
        version, limit, usage = _cgroup_reading()
        observed_available = values["MemAvailable"]
        if limit is not None:
            observed_available = min(observed_available, limit - usage)
        record = os.statvfs(state_dir)
        if (type(record.f_bavail) is not int or record.f_bavail < 0
                or type(record.f_frsize) is not int or record.f_frsize <= 0):
            refuse("invalid state filesystem telemetry")
        free_bytes = record.f_bavail * record.f_frsize
        if free_bytes > _MAX_MEMORY:
            refuse("state filesystem size out of bounds")
        return {
            "schema": "laptop-device-observation.v1",
            "memory_total_bytes": values["MemTotal"],
            "memory_available_bytes": values["MemAvailable"],
            "swap_free_bytes": values["SwapFree"],
            "state_storage_available_bytes": free_bytes,
            "cgroup_version_observed": version,
            "cgroup_memory_limit_bytes": limit,
            "cgroup_memory_used_bytes": usage,
            "effective_memory_available_bytes": observed_available,
            "measurement_only": True,
            "qualified_device": False,
        }
    except (OSError, ValueError, UnicodeError, OverflowError):
        refuse("device telemetry unavailable or malformed")


__all__ = ["inspect_device"]

"""Capacity admission based on actual local host/cgroup resource headroom.

This controller can only reduce the existing four-slice global ceiling. It
does not allocate a worker, modify the Mongo lease, bypass a quota, or raise
resource entitlements. Missing measurements trigger conservative operation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
from pathlib import Path, PurePosixPath
import time
from typing import Callable

_MIB = 1024 * 1024
RESERVE_BYTES = 256 * _MIB
SLICE_BYTES = 640 * _MIB
MAX_SAMPLE_AGE = 2.
_MAX_READ = 16384
_MAX_ANCESTORS = 16


@dataclass(frozen=True)
class PressureSample:
    available_bytes: int | None
    cpu_cores: float | None
    memory_pressure: float | None
    cpu_pressure: float | None
    captured_monotonic: float


@dataclass(frozen=True)
class CapacityDecision:
    limit: int
    reasons: tuple[str, ...]
    sample: PressureSample
    desired_limit: int
    network_authority_expanded: bool = False


def _read(path: Path) -> str:
    try:
        with path.open("r", encoding="ascii", errors="strict") as stream:
            value = stream.read(_MAX_READ + 1)
        return value if len(value) <= _MAX_READ else ""
    except (OSError, UnicodeError):
        return ""


def _number(raw: str) -> int | None:
    val = raw.strip()
    if not val.isascii() or not val.isdecimal() or len(val) > 20:
        return None
    result = int(val)
    return result if result <= 2**63 - 1 else None


def _pressure(raw: str) -> float | None:
    for line in raw.splitlines():
        fields = line.split()
        if not fields or fields[0] != "some":
            continue
        for field in fields[1:]:
            if field.startswith("avg10="):
                try:
                    result = float(field.split("=", 1)[1]) / 100
                except ValueError:
                    return None
                if math.isfinite(result) and 0 <= result <= 1:
                    return result
    return None


def _cgroup_paths(raw: str, root: Path) -> tuple[Path, ...]:
    # Kernel-provided unified path, no caller-provided path or traversal.
    for line in raw.splitlines():
        if not line.startswith("0::/"):
            continue
        rel = PurePosixPath(line[4:])
        if rel.is_absolute() or any(part in {".", ".."} for part in rel.parts):
            return (root,)
        if len(rel.parts) > _MAX_ANCESTORS:
            return (root,)
        chunks = [root]
        for part in rel.parts:
            chunks.append(chunks[-1] / part)
        return tuple(chunks)
    return (root,)


def sample_pressure(*, reader: Callable[[Path], str] = _read,
                    clock: Callable[[], float] = time.monotonic) -> PressureSample:
    memory = []
    cpu = []
    mem_pressure = []
    cpu_pressure = []
    if hasattr(os, "sched_getaffinity"):
        try:
            affinity = len(os.sched_getaffinity(0))
            if affinity > 0:
                cpu.append(float(affinity))
        except OSError:
            pass
    count = os.cpu_count()
    if isinstance(count, int) and count > 0:
        cpu.append(float(count))
    for line in reader(Path("/proc/meminfo")).splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            amount = _number(parts[1]) if len(parts) == 3 and parts[2] == "kB" else None
            if amount is not None:
                memory.append(amount * 1024)
            break
    base = Path("/sys/fs/cgroup")
    paths = _cgroup_paths(reader(Path("/proc/self/cgroup")), base)
    for path in paths:
        maximum = _number(reader(path / "memory.max"))
        used = _number(reader(path / "memory.current"))
        high = _number(reader(path / "memory.high"))
        for bound in (maximum, high):
            if bound is not None and used is not None:
                memory.append(max(0, bound - used))
        limits = reader(path / "cpu.max").split()
        if len(limits) == 2:
            quota, period = map(_number, limits)
            if quota is not None and period is not None and quota > 0 and period > 0:
                cpu.append(quota / period)
        m = _pressure(reader(path / "memory.pressure"))
        c = _pressure(reader(path / "cpu.pressure"))
        if m is not None:
            mem_pressure.append(m)
        if c is not None:
            cpu_pressure.append(c)
    for name, output in (("memory", mem_pressure), ("cpu", cpu_pressure)):
        value = _pressure(reader(Path("/proc/pressure") / name))
        if value is not None:
            output.append(value)
    return PressureSample(min(memory) if memory else None,
                          min(cpu) if cpu else None,
                          max(mem_pressure) if mem_pressure else None,
                          max(cpu_pressure) if cpu_pressure else None, clock())


def desired_capacity(sample: PressureSample, *, ceiling: int, now: float) -> tuple[int, tuple[str, ...]]:
    if (not isinstance(sample, PressureSample) or type(ceiling) is not int or not 1 <= ceiling <= 4
            or not math.isfinite(now) or not math.isfinite(sample.captured_monotonic)):
        raise ValueError("invalid physical capacity sample")
    if not 0 <= now - sample.captured_monotonic <= MAX_SAMPLE_AGE:
        return 0, ("stale_measurement",)
    limit = ceiling
    reasons = []
    available = sample.available_bytes
    if available is None:
        limit = min(limit, 1)
        reasons.append("memory_unobserved")
    elif type(available) is not int or available < 0:
        return 0, ("invalid_memory",)
    else:
        headroom = max(0, available - RESERVE_BYTES)
        memory_limit = headroom // SLICE_BYTES
        limit = min(limit, memory_limit)
        if memory_limit < ceiling:
            reasons.append("memory_headroom")
    cores = sample.cpu_cores
    if cores is None:
        limit = min(limit, 1)
        reasons.append("cpu_unobserved")
    elif isinstance(cores, bool) or not math.isfinite(cores) or cores <= 0:
        return 0, ("invalid_cpu",)
    else:
        core_limit = max(1, math.floor(cores))
        limit = min(limit, core_limit)
        if core_limit < ceiling:
            reasons.append("cpu_quota")
    for signal, low, high, name in (
        (sample.memory_pressure, .08, .20, "memory_pressure"),
        (sample.cpu_pressure, .25, .70, "cpu_pressure"),
    ):
        if signal is None:
            continue
        if isinstance(signal, bool) or not math.isfinite(signal) or not 0 <= signal <= 1:
            return 0, ("invalid_pressure",)
        if signal >= high:
            limit = 0
            reasons.append(name + "_critical")
        elif signal >= low:
            limit = min(limit, 1)
            reasons.append(name + "_elevated")
    return max(0, limit), tuple(reasons or ["within_observed_budget"])


class ResourceGovernor:
    """Immediate downward adjustment; gradual recovery after stable samples."""
    def __init__(self, ceiling: int = 4):
        if type(ceiling) is not int or not 1 <= ceiling <= 4:
            raise ValueError("invalid existing physical ceiling")
        self.ceiling = ceiling
        self._limit = 1
        self._healthy_since: float | None = None
        self._last_increase: float | None = None
        self._last: CapacityDecision | None = None

    def observe(self, sample: PressureSample, *, now: float) -> CapacityDecision:
        desired, reasons = desired_capacity(sample, ceiling=self.ceiling, now=now)
        if desired < self._limit:
            self._limit = desired
            self._healthy_since = None
        elif desired > self._limit:
            if self._healthy_since is None:
                self._healthy_since = now
            if now - self._healthy_since >= 3 and (
                self._last_increase is None or now - self._last_increase >= 3
            ):
                self._limit += 1
                self._last_increase = now
                self._healthy_since = now
        else:
            self._healthy_since = None
        self._last = CapacityDecision(self._limit, reasons, sample, desired)
        return self._last

    def current(self) -> CapacityDecision:
        sample = sample_pressure()
        return self.observe(sample, now=time.monotonic())

    def projection(self) -> dict:
        # Do not disclose raw host memory or CPU quantities to a tenant.
        decision = self._last
        return {"effective_local_slots": decision.limit if decision else 1,
                "maximum_slots": self.ceiling,
                "desired_slots": decision.desired_limit if decision else 1,
                "reasons": list(decision.reasons) if decision else ["unobserved"],
                "network_authority_expanded": False}

"""Measured CPU/memory topology and conservative offline worker admission.

No network, model, GPU, or privileged OS control. Every unknown hardware
quantity is explicit and never silently treated as zero pressure.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
import platform
import re
import subprocess
import sys
from typing import Sequence

SCHEMA = "skeleton.offline.cpu-worker-budget.v1"
MAX_VISIBLE_CPUS = 4096


class CpuBudgetError(ValueError):
    """Invalid hardware evidence or worker admission policy."""


@dataclass(frozen=True, slots=True)
class CpuTopology:
    logical_visible: int
    physical_cores: int | None
    effective_cpus: float
    largest_l3_slice_bytes: int | None
    affinity_source: str
    quota_source: str
    cache_source: str
    platform: str

    def __post_init__(self) -> None:
        if type(self.logical_visible) is not int or not 1 <= self.logical_visible <= MAX_VISIBLE_CPUS:
            raise CpuBudgetError("invalid logical CPU count")
        if self.physical_cores is not None and (
            type(self.physical_cores) is not int or not 1 <= self.physical_cores <= self.logical_visible
        ):
            raise CpuBudgetError("invalid physical CPU count")
        if not math.isfinite(self.effective_cpus) or not 0 < self.effective_cpus <= self.logical_visible:
            raise CpuBudgetError("invalid effective CPU quota")
        if self.largest_l3_slice_bytes is not None and (
            type(self.largest_l3_slice_bytes) is not int or self.largest_l3_slice_bytes <= 0
        ):
            raise CpuBudgetError("invalid L3 cache observation")
        for label in (self.affinity_source, self.quota_source, self.cache_source, self.platform):
            if type(label) is not str or not 1 <= len(label) <= 80:
                raise CpuBudgetError("invalid topology evidence label")


@dataclass(frozen=True, slots=True)
class MemoryTopology:
    total_bytes: int | None
    available_bytes: int | None
    source: str

    def __post_init__(self) -> None:
        for value in (self.total_bytes, self.available_bytes):
            if value is not None and (type(value) is not int or value < 0):
                raise CpuBudgetError("invalid memory telemetry")
        if self.total_bytes is not None and self.available_bytes is not None:
            if self.available_bytes > self.total_bytes:
                raise CpuBudgetError("available memory exceeds total memory")
        if type(self.source) is not str or not 1 <= len(self.source) <= 80:
            raise CpuBudgetError("invalid memory source")


@dataclass(frozen=True, slots=True)
class CpuWorkerPlan:
    workers: int
    cpu_limit: int
    memory_limit: int | None
    reason: str
    digest: str
    topology: CpuTopology
    memory: MemoryTopology


def _bounded_text(path: str, limit: int = 4096) -> str | None:
    try:
        with open(path, "rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return None
        return raw.decode("ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        return None


def _positive_int(text: str | None) -> int | None:
    if text is None or not re.fullmatch(r"[0-9]{1,20}", text):
        return None
    value = int(text)
    return value if value > 0 else None


def _cgroup_cpu_quota() -> tuple[float | None, str]:
    """Read v2 then v1, with no attempt to mutate system cgroup controls."""
    v2 = _bounded_text("/sys/fs/cgroup/cpu.max", 256)
    if v2 is not None:
        parts = v2.split()
        if len(parts) == 2:
            period = _positive_int(parts[1])
            if parts[0] == "max" and period:
                return None, "cgroup-v2-unlimited"
            quota = _positive_int(parts[0])
            if quota and period:
                return quota / period, "cgroup-v2-cpu.max"
        return None, "cgroup-v2-unreadable"
    quota = _bounded_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", 64)
    period = _positive_int(_bounded_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us", 64))
    if quota == "-1" and period:
        return None, "cgroup-v1-unlimited"
    limited = _positive_int(quota)
    if limited and period:
        return limited / period, "cgroup-v1-cpu.cfs"
    return None, "unavailable"


def _linux_physical(visible: set[int]) -> int | None:
    cores: set[tuple[int, int]] = set()
    if len(visible) > MAX_VISIBLE_CPUS:
        return None
    for cpu in visible:
        base = f"/sys/devices/system/cpu/cpu{cpu}/topology"
        # Linux identifiers legitimately start at zero.
        raw_package = _bounded_text(base + "/physical_package_id", 32)
        raw_core = _bounded_text(base + "/core_id", 32)
        if raw_package is None or raw_core is None:
            return None
        if not re.fullmatch(r"[0-9]{1,8}", raw_package) or not re.fullmatch(r"[0-9]{1,8}", raw_core):
            return None
        cores.add((int(raw_package), int(raw_core)))
    return len(cores) or None


def _cache_size(text: str | None) -> int | None:
    if text is None:
        return None
    match = re.fullmatch(r"([0-9]{1,12})([KMG]?)", text.strip(), re.IGNORECASE)
    if not match:
        return None
    scale = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}[match.group(2).upper()]
    value = int(match.group(1)) * scale
    return value if 0 < value <= 1024**4 else None


def _linux_l3(visible: set[int]) -> int | None:
    maximum: int | None = None
    for cpu in sorted(visible)[:64]:
        base = f"/sys/devices/system/cpu/cpu{cpu}/cache"
        for index in range(8):
            prefix = f"{base}/index{index}"
            if _bounded_text(prefix + "/level", 16) != "3":
                continue
            if _bounded_text(prefix + "/type", 16) not in ("Unified", "Data"):
                continue
            size = _cache_size(_bounded_text(prefix + "/size", 32))
            if size is not None:
                maximum = max(maximum or 0, size)
    return maximum


def _sysctl_int(key: str) -> int | None:
    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", key], capture_output=True,
            text=True, timeout=1.5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or len(completed.stdout) > 64:
        return None
    return _positive_int(completed.stdout.strip())


def probe_cpu_topology() -> CpuTopology:
    system = platform.system()
    logical = max(1, min(os.cpu_count() or 1, MAX_VISIBLE_CPUS))
    affinity_source = "os.cpu_count-fallback"
    visible = set(range(logical))
    if hasattr(os, "sched_getaffinity"):
        try:
            affinity = set(os.sched_getaffinity(0))
            if 0 < len(affinity) <= MAX_VISIBLE_CPUS:
                visible = affinity
                logical = len(affinity)
                affinity_source = "os.sched_getaffinity"
        except OSError:
            pass
    logical = max(1, min(logical, MAX_VISIBLE_CPUS))
    physical = None
    cache = None
    quota = None
    quota_source = "unavailable"
    cache_source = "unavailable"
    if system == "Linux":
        physical = _linux_physical(visible)
        cache = _linux_l3(visible)
        cache_source = "linux-sysfs-largest-L3-slice" if cache is not None else "unavailable"
        quota, quota_source = _cgroup_cpu_quota()
    elif system == "Darwin":
        physical = _sysctl_int("hw.physicalcpu")
        cache = _sysctl_int("hw.l3cachesize")
        cache_source = "darwin-sysctl-hw.l3cachesize" if cache is not None else "unavailable"
        logical_sysctl = _sysctl_int("hw.logicalcpu")
        if affinity_source == "os.cpu_count-fallback" and logical_sysctl:
            logical = min(logical, logical_sysctl)
            affinity_source = "darwin-sysctl-hw.logicalcpu"
    elif system == "Windows":
        # os.cpu_count is a fallback, not a physical-core or NUMA claim.
        quota_source = "windows-job-quota-unavailable"
    if physical is not None:
        physical = min(physical, logical)
    effective = min(float(logical), quota) if quota is not None and quota > 0 else float(logical)
    return CpuTopology(logical, physical, effective, cache, affinity_source,
                       quota_source, cache_source, system)


def probe_memory_topology() -> MemoryTopology:
    system = platform.system()
    if system == "Linux":
        raw = _bounded_text("/proc/meminfo", 16384)
        if raw is not None:
            fields = {}
            for line in raw.splitlines():
                match = re.fullmatch(r"([A-Za-z_]+):\s*([0-9]+)\s+kB", line.strip())
                if match:
                    fields[match.group(1)] = int(match.group(2)) * 1024
            total = fields.get("MemTotal")
            available = fields.get("MemAvailable")
            if total and available is not None:
                limit = _positive_int(_bounded_text("/sys/fs/cgroup/memory.max", 64))
                used_raw = _bounded_text("/sys/fs/cgroup/memory.current", 64)
                used = int(used_raw) if used_raw is not None and re.fullmatch(r"[0-9]{1,20}", used_raw) else None
                source = "linux-proc-meminfo"
                if limit and used is not None and limit < total:
                    total = limit
                    available = min(available, max(0, limit - used))
                    source = "linux-proc-and-cgroup-v2"
                return MemoryTopology(total, min(available, total), source)
    if system == "Darwin":
        total = _sysctl_int("hw.memsize")
        return MemoryTopology(total, None, "darwin-sysctl-total-only" if total else "unavailable")
    if system == "Windows":
        try:
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return MemoryTopology(int(status.ullTotalPhys), int(status.ullAvailPhys),
                                      "windows-GlobalMemoryStatusEx")
        except (AttributeError, OSError, ValueError):
            pass
    return MemoryTopology(None, None, "unavailable")


def plan_cpu_workers(
    topology: CpuTopology,
    memory: MemoryTopology,
    *,
    operator_max_workers: int,
    bytes_per_worker: int,
    memory_reserve_bytes: int,
    interactive_cpu_reserve: int = 1,
    thermal_state: str = "unknown",
) -> CpuWorkerPlan:
    """Conservative planner; callers must enforce its returned concurrency."""
    if not isinstance(topology, CpuTopology) or not isinstance(memory, MemoryTopology):
        raise CpuBudgetError("measured topology objects required")
    for name, value in (
        ("operator_max_workers", operator_max_workers),
        ("bytes_per_worker", bytes_per_worker),
        ("memory_reserve_bytes", memory_reserve_bytes),
        ("interactive_cpu_reserve", interactive_cpu_reserve),
    ):
        if type(value) is not int or value < 0:
            raise CpuBudgetError(f"invalid {name}")
    if not 1 <= operator_max_workers <= 256 or bytes_per_worker == 0:
        raise CpuBudgetError("worker and memory policy must be bounded")
    if interactive_cpu_reserve > topology.logical_visible:
        raise CpuBudgetError("interactive reserve exceeds visible CPU set")
    if thermal_state not in ("normal", "warm", "critical", "unknown"):
        raise CpuBudgetError("invalid thermal state")
    cpu_limit = max(0, math.floor(topology.effective_cpus) - interactive_cpu_reserve)
    if cpu_limit == 0 and interactive_cpu_reserve == 0:
        cpu_limit = 1
    memory_limit = None
    if memory.available_bytes is not None:
        memory_limit = max(0, (memory.available_bytes - memory_reserve_bytes) // bytes_per_worker)
    workers = min(operator_max_workers, cpu_limit)
    reason = "within_measured_budget"
    if memory_limit is None:
        workers = min(workers, 1)
        reason = "memory_telemetry_unavailable"
    elif memory_limit < workers:
        workers = memory_limit
        reason = "memory_budget"
    if thermal_state == "critical":
        workers = 0
        reason = "thermal_critical"
    elif thermal_state in ("warm", "unknown") and workers > 1:
        workers = max(1, workers // 2)
        reason = "thermal_conservative"
    if cpu_limit == 0 and workers == 0 and reason == "within_measured_budget":
        reason = "cpu_reserved_for_interactive"
    body = {"schema": SCHEMA, "topology": asdict(topology), "memory": asdict(memory),
            "operator_max_workers": operator_max_workers, "bytes_per_worker": bytes_per_worker,
            "memory_reserve_bytes": memory_reserve_bytes,
            "interactive_cpu_reserve": interactive_cpu_reserve,
            "thermal_state": thermal_state, "workers": workers, "cpu_limit": cpu_limit,
            "memory_limit": memory_limit, "reason": reason}
    digest = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return CpuWorkerPlan(workers, cpu_limit, memory_limit, reason, digest, topology, memory)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton.app.offline_cpu_budget")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--memory-per-worker-mib", type=int, default=256)
    parser.add_argument("--memory-reserve-mib", type=int, default=512)
    parser.add_argument("--interactive-reserve", type=int, default=1)
    parser.add_argument("--thermal", choices=("normal", "warm", "critical", "unknown"),
                        default="unknown", help="operator-provided state, NOT measured thermal telemetry")
    args = parser.parse_args(argv)
    try:
        plan = plan_cpu_workers(
            probe_cpu_topology(), probe_memory_topology(),
            operator_max_workers=args.max_workers,
            bytes_per_worker=args.memory_per_worker_mib * 1024**2,
            memory_reserve_bytes=args.memory_reserve_mib * 1024**2,
            interactive_cpu_reserve=args.interactive_reserve,
            thermal_state=args.thermal,
        )
    except CpuBudgetError as exc:
        print("CPU budget rejected: " + str(exc), file=sys.stderr)
        return 2
    result = {"schema": SCHEMA, "workers": plan.workers, "cpu_limit": plan.cpu_limit,
              "memory_limit": plan.memory_limit, "reason": plan.reason,
              "digest": plan.digest, "cpu": asdict(plan.topology),
              "memory": asdict(plan.memory), "thermal_source": "operator-supplied"}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Observational CPU/RAM/cgroup profile for a real installed local GGUF.

This is advisory capacity estimation, NEVER automatic GPU/VRAM probing,
device approval, model rights review, hidden swap allocation or a claim that
unbounded inference will fit. The canonical isolated native admission remains
the only runtime authority. Unknown pressure measurements fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import stat

from .contracts import refuse
from .device_observer import inspect_device
from .installation import source_receipt
from .preflight import validate_native_shape

MIB = 1024 * 1024
GIB = 1024 * MIB
MAX_MEMORY_VALUE = 2**53 - 1
MAX_PROFILE_CAPACITY = 20_000_000_000


class DesktopCapacityHold(ValueError):
    """Host telemetry does not justify even a conservative local AI estimate."""


@dataclass(frozen=True, slots=True)
class CgroupObservation:
    memory_available_bytes: int | None
    cpu_quota_cores: int | None
    memory_bounded: bool
    cpu_bounded: bool
    source: str

    def __post_init__(self):
        if type(self.source) is not str or self.source not in (
            "cgroup-v2", "cgroup-v1", "no-cgroup-controller",
        ):
            raise DesktopCapacityHold("unsupported cgroup source observation")
        for name in ("memory_available_bytes", "cpu_quota_cores"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise DesktopCapacityHold("invalid cgroup quota value")
        if (type(self.memory_bounded) is not bool
                or type(self.cpu_bounded) is not bool):
            raise DesktopCapacityHold("invalid cgroup evidence flags")
        if self.memory_bounded and self.memory_available_bytes is None:
            raise DesktopCapacityHold("bounded cgroup memory lacks usage evidence")
        if self.cpu_bounded and self.cpu_quota_cores is None:
            raise DesktopCapacityHold("bounded cgroup CPU lacks quota evidence")


def _int(raw: str, *, allow_negative_one=False) -> int:
    if type(raw) is not str or len(raw) > 32:
        raise DesktopCapacityHold("untrusted finite kernel telemetry")
    value = raw.strip()
    if allow_negative_one and value == "-1":
        return -1
    if not value or not value.isascii() or not value.isdecimal():
        raise DesktopCapacityHold("malformed kernel resource number")
    result = int(value)
    if result > MAX_MEMORY_VALUE:
        raise DesktopCapacityHold("implausible kernel resource number")
    return result


def _read_kernel(path: Path) -> str:
    """Read bounded kernel-owned control text, no final symlink or trailing data."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise DesktopCapacityHold("kernel cgroup reading needs POSIX no-follow")
    fd = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise DesktopCapacityHold("kernel resource control not a regular file")
        content = os.read(fd, 129)
        if not 0 < len(content) <= 128:
            raise DesktopCapacityHold("missing or oversized kernel control")
        return content.decode("ascii", "strict").strip()
    finally:
        os.close(fd)


def _process_cgroup() -> tuple[str, str]:
    """Identify the actual process cgroup, not a guessed host root."""
    try:
        with open("/proc/self/cgroup", "rb") as stream:
            raw = stream.read(8193)
        if not 0 < len(raw) <= 8192:
            raise DesktopCapacityHold("missing bounded process cgroup mapping")
        lines = raw.decode("ascii", "strict").splitlines()
        if not 1 <= len(lines) <= 128:
            raise DesktopCapacityHold("untrusted process cgroup inventory")
        v2 = []
        v1 = []
        for line in lines:
            chunks = line.split(":", 2)
            if len(chunks) != 3:
                raise DesktopCapacityHold("malformed process cgroup mapping")
            version, controllers, location = chunks
            if (not location.startswith("/") or "\\" in location
                    or chr(0) in location or ".." in location.split("/")):
                raise DesktopCapacityHold("unsafe cgroup relative location")
            if version == "0" and controllers == "":
                v2.append(location)
            elif "memory" in controllers.split(","):
                v1.append(location)
        if len(v2) == 1:
            return "cgroup-v2", v2[0]
        if len(v2) > 1:
            raise DesktopCapacityHold("ambiguous unified cgroup mapping")
        if len(v1) == 1:
            return "cgroup-v1", v1[0]
        if len(v1) > 1:
            raise DesktopCapacityHold("ambiguous memory cgroup mapping")
        return "no-cgroup-controller", "/"
    except (OSError, ValueError, UnicodeError) as exc:
        raise DesktopCapacityHold("cgroup observation unavailable") from exc


def _cgroup_path(version: str, location: str) -> Path:
    if not location.startswith("/") or ".." in location.split("/"):
        raise DesktopCapacityHold("unsafe kernel resource cgroup path")
    root = (
        Path("/sys/fs/cgroup") if version == "cgroup-v2"
        else Path("/sys/fs/cgroup/memory")
    )
    selected = root / location.lstrip("/")
    if not selected.is_relative_to(root):
        raise DesktopCapacityHold("cgroup resource escaped known hierarchy")
    return selected


def _quota(quota: int, period: int) -> int | None:
    if quota == -1:
        return None
    if not (0 <= quota <= MAX_MEMORY_VALUE and 1 <= period <= MAX_MEMORY_VALUE):
        raise DesktopCapacityHold("invalid CPU controller quota")
    if quota == 0:
        raise DesktopCapacityHold("zero effective CPU quota")
    # Conservative floor rather than oversubscribing fractional CPU quotas.
    return max(1, quota // period)


def observe_cgroup() -> CgroupObservation:
    version, location = _process_cgroup()
    if version == "no-cgroup-controller":
        return CgroupObservation(None, None, False, False, version)
    root = _cgroup_path(version, location)
    try:
        if version == "cgroup-v2":
            limit_raw = _read_kernel(root / "memory.max")
            current = _int(_read_kernel(root / "memory.current"))
            cpu_fields = _read_kernel(root / "cpu.max").split()
            if len(cpu_fields) != 2:
                raise DesktopCapacityHold("invalid cgroup v2 CPU quota")
            limit = None if limit_raw == "max" else _int(limit_raw)
            quota = -1 if cpu_fields[0] == "max" else _int(cpu_fields[0])
            period = _int(cpu_fields[1])
        else:
            limit = _int(_read_kernel(root / "memory.limit_in_bytes"))
            current = _int(_read_kernel(root / "memory.usage_in_bytes"))
            quota = _int(_read_kernel(
                Path("/sys/fs/cgroup/cpu") / location.lstrip("/")
                / "cpu.cfs_quota_us"
            ), allow_negative_one=True)
            period = _int(_read_kernel(
                Path("/sys/fs/cgroup/cpu") / location.lstrip("/")
                / "cpu.cfs_period_us"
            ))
            # Old kernel uses a very large sentinel for an unlimited v1
            # memory controller. Never call that a real bound.
            if limit >= 2**50:
                limit = None
        if limit is not None and current > limit:
            raise DesktopCapacityHold("cgroup usage exceeds controller limit")
        free = None if limit is None else limit - current
        cpu = _quota(quota, period)
        return CgroupObservation(
            free, cpu, limit is not None, cpu is not None, version,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise DesktopCapacityHold("live cgroup pressure unavailable") from exc


def observe_cpu() -> int:
    logical = os.cpu_count()
    if type(logical) is not int or logical < 1 or logical > 4096:
        raise DesktopCapacityHold("unknown logical processor allocation")
    affinity = getattr(os, "sched_getaffinity", None)
    if callable(affinity):
        try:
            available = len(affinity(0))
        except OSError as exc:
            raise DesktopCapacityHold("unavailable effective CPU affinity") from exc
        if not 1 <= available <= 4096:
            raise DesktopCapacityHold("empty CPU affinity")
        return min(logical, available)
    return logical


def recommend(
    installed, observed: object, cgroup: CgroupObservation,
    *, available_cores: int,
) -> dict[str, object]:
    """Pure finite resource recommendation, not final native admission."""
    if (
        type(observed) is not dict
        or observed.get("measurement_only") is not True
        or observed.get("qualified_device") is not False
        or not isinstance(cgroup, CgroupObservation)
        or type(available_cores) is not int
        or not 1 <= available_cores <= 4096
    ):
        raise DesktopCapacityHold("trusted typed device observations required")
    from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
        InstalledModelReport,
    )
    if (
        type(installed) is not InstalledModelReport
        or installed.content_verified is not True
        or installed.rights_approved is not True
        or installed.release_certified is not False
    ):
        raise DesktopCapacityHold("installed source proof or rights approval absent")
    size = installed.model_bytes
    available = observed.get("memory_available_bytes")
    disk = observed.get("state_storage_available_bytes")
    if (
        type(size) is not int or size < 1
        or type(available) is not int or not 1 <= available <= MAX_MEMORY_VALUE
        or type(disk) is not int or not 0 <= disk <= MAX_MEMORY_VALUE
    ):
        raise DesktopCapacityHold("model or host measurement outside finite bound")
    if disk < 256 * MIB:
        raise DesktopCapacityHold("private SQLite state storage below floor")
    observed_memory = min(
        available, cgroup.memory_available_bytes
        if cgroup.memory_available_bytes is not None else available,
    )
    if observed_memory < 1:
        raise DesktopCapacityHold("no model-capable memory headroom")
    cpu = min(
        available_cores,
        cgroup.cpu_quota_cores
        if cgroup.cpu_quota_cores is not None else available_cores,
    )
    if cpu < 1:
        raise DesktopCapacityHold("CPU controller admits no native worker")
    # These are intentionally generous *estimated* CPU-side reservations,
    # not claims about actual GGUF attention geometry or allocator overhead.
    reserved_system = max(1 * GIB, available // 8)
    native_scratch = max(512 * MIB, min(2 * GIB, size // 3))
    estimated_kv = 512 * MIB
    required = size + native_scratch + estimated_kv + reserved_system
    if required > observed_memory:
        raise DesktopCapacityHold("installed model plus reserves exceed measured headroom")
    policy_budget = min(MAX_PROFILE_CAPACITY, observed_memory - reserved_system)
    if policy_budget < size + native_scratch + estimated_kv:
        raise DesktopCapacityHold("capacity broker cannot fit conservative model estimate")
    threads = max(1, min(8, cpu - 1 if cpu > 1 else 1))
    result = {
        "context": 2048,
        "max_output_tokens": 256,
        "threads": threads,
        "gpu_layers": 0,
        "inference_ms": 90000,
        "capacity_budget_bytes": policy_budget,
    }
    validate_native_shape(
        n_ctx=result["context"], max_new_tokens=result["max_output_tokens"],
        n_threads=result["threads"], gpu_layers=0,
        capacity_budget_bytes=result["capacity_budget_bytes"],
        capacity_slots=1, inference_ms=result["inference_ms"],
    )
    return {
        "schema": "jeeves.desktop.observed-profile.v1",
        "status": "conservative-advisory-profile-not-native-proof",
        "model_sha256": installed.model_sha256,
        "measured_model_bytes": size,
        "estimated_requirement_bytes": required,
        "observed_host_available_bytes": available,
        "effective_available_bytes": observed_memory,
        "state_free_bytes": disk,
        "cgroup_source": cgroup.source,
        "cgroup_memory_bounded": cgroup.memory_bounded,
        "cgroup_cpu_bounded": cgroup.cpu_bounded,
        "effective_cpu_cores": cpu,
        "recommendation": result,
        "gpu_memory_measured": False,
        "device_pressure_qualified": False,
        "release_certified": False,
    }


def plan_existing_model(model_root: str | Path, state_dir: str | Path):
    """Observe only on explicit operator request; never start a GGUF model."""
    from .desktop_provision import private_path
    model = source_receipt(private_path(model_root), require_rights=True)
    state = private_path(state_dir)
    host = inspect_device(state)
    cgroup = observe_cgroup()
    return recommend(model, host, cgroup, available_cores=observe_cpu())


__all__ = [
    "DesktopCapacityHold", "CgroupObservation", "observe_cgroup",
    "observe_cpu", "recommend", "plan_existing_model",
]

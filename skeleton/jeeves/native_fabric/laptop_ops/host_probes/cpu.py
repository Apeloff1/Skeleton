"""Conservative current-host CPU observation without starting a native model.

This is advisory CPU quota evidence, not a durable lease or proof that a
model can execute. Unknown cgroup/process affinity fails closed for quota
claims. No shell commands, network calls, filesystem reads or tools used.
"""
from __future__ import annotations

from dataclasses import dataclass
import os

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold

_MAX_CORES = 4096
_MAX_REQUEST_THREADS = 64


def _count(value: object) -> int | None:
    """Avoid bool-as-int acceptance and absurd broken platform telemetry."""
    return value if type(value) is int and 1 <= value <= _MAX_CORES else None


@dataclass(frozen=True, slots=True)
class CpuObservation:
    requested_threads: int
    logical_cores: int | None
    process_cores: int | None
    affinity_cores: int | None

    def __post_init__(self) -> None:
        if type(self.requested_threads) is not int or not 1 <= self.requested_threads <= 64:
            raise LaptopGateHold("invalid bounded native thread request")
        for value in (self.logical_cores, self.process_cores, self.affinity_cores):
            if value is not None and _count(value) is None:
                raise LaptopGateHold("invalid CPU source telemetry")

    @property
    def observed_ceiling(self) -> int | None:
        values = (self.logical_cores, self.process_cores, self.affinity_cores)
        valid = tuple(value for value in values if value is not None)
        return min(valid) if valid else None

    @property
    def process_quota_observed(self) -> bool:
        return self.process_cores is not None or self.affinity_cores is not None

    @property
    def request_fits_observed_limit(self) -> bool:
        limit = self.observed_ceiling
        return bool(self.process_quota_observed and limit is not None
                    and self.requested_threads <= limit)

    def to_record(self) -> dict[str, object]:
        """Share only aggregate counts. Never claim workload or device approval."""
        return {
            "schema": "jeeves.laptop_ops.host_cpu.v1",
            "requested_threads": self.requested_threads,
            "logical_cores": self.logical_cores,
            "process_cores": self.process_cores,
            "affinity_cores": self.affinity_cores,
            "observed_ceiling": self.observed_ceiling,
            "process_quota_observed": self.process_quota_observed,
            "request_fits_observed_limit": self.request_fits_observed_limit,
            "actual_cgroup_cpu_quota_verified": False,
            "model_started": False,
            "physical_device_qualified": False,
            "release_certified": False,
        }


def observe_cpu(requested_threads: int) -> CpuObservation:
    """Read OS-supplied CPU limits, treating any unknown quota conservatively."""
    if type(requested_threads) is not int or not 1 <= requested_threads <= _MAX_REQUEST_THREADS:
        raise LaptopGateHold("invalid bounded native thread request")
    logical: int | None = None
    process: int | None = None
    affinity: int | None = None
    try:
        logical = _count(os.cpu_count())
    except (OSError, ValueError, TypeError):
        pass
    # Python 3.13+ exposes process usable CPUs where supported.
    process_fn = getattr(os, "process_cpu_count", None)
    if callable(process_fn):
        try:
            process = _count(process_fn())
        except (OSError, ValueError, TypeError):
            pass
    affinity_fn = getattr(os, "sched_getaffinity", None)
    if callable(affinity_fn):
        try:
            members = affinity_fn(0)
            if type(members) in (set, frozenset):
                affinity = _count(len(members))
        except (OSError, ValueError, TypeError):
            pass
    return CpuObservation(requested_threads, logical, process, affinity)


__all__ = ["CpuObservation", "observe_cpu"]

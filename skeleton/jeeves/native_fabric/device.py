"""Source-verifiable laptop telemetry and explicit native-device readiness gaps.

No CPU/GPU/thermal sample is invented. Optional sensors remain unknown rather
than considered safe. This module accepts observations, not platform rights or
permission to activate a GGUF model; native readiness still requires the
existing approved installer and physical end-to-end qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import os
import platform
import time
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractHold, exact_integer, finite, fingerprint, identifier, text,
)
from .health import HealthSignal, HealthAssessment, assess_health


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    observed_at_ns: int
    platform_name: str
    architecture: str
    logical_cpu_count: int | None
    physical_ram_bytes: int | None
    available_ram_bytes: int | None
    available_disk_bytes: int | None
    gpu_memory_bytes: int | None
    gpu_utilization_pct: float | None
    cpu_load_pct: float | None
    temperature_c: float | None
    power_state: str
    host_device_attested: bool = False

    def __post_init__(self):
        exact_integer(self.observed_at_ns, maximum=10**30)
        text(self.platform_name, maximum_bytes=128)
        text(self.architecture, maximum_bytes=128)
        for label in (
            "logical_cpu_count", "physical_ram_bytes", "available_ram_bytes",
            "available_disk_bytes", "gpu_memory_bytes",
        ):
            raw = getattr(self, label)
            if raw is not None:
                exact_integer(raw, minimum=0, maximum=10**16)
        for label in ("gpu_utilization_pct", "cpu_load_pct"):
            raw = getattr(self, label)
            if raw is not None:
                finite(raw, minimum=0, maximum=100)
        if self.temperature_c is not None:
            finite(self.temperature_c, minimum=-273.15, maximum=250)
        if self.power_state not in ("ac", "battery", "unknown"):
            raise ContractHold("unknown device power state")
        if type(self.host_device_attested) is not bool:
            raise ContractHold("device attestation must be explicit boolean")
        if (
            self.physical_ram_bytes is not None and
            self.available_ram_bytes is not None and
            self.available_ram_bytes > self.physical_ram_bytes
        ):
            raise ContractHold("impossible RAM telemetry exceeds device memory")

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.fabric.device_snapshot.v1",
            "observed_at_ns": self.observed_at_ns,
            "platform": self.platform_name,
            "architecture": self.architecture,
            "logical_cpu_count": self.logical_cpu_count,
            "physical_ram_bytes": self.physical_ram_bytes,
            "available_ram_bytes": self.available_ram_bytes,
            "available_disk_bytes": self.available_disk_bytes,
            "gpu_memory_bytes": self.gpu_memory_bytes,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "cpu_load_pct": self.cpu_load_pct,
            "temperature_c": self.temperature_c,
            "power_state": self.power_state,
            "host_device_attested": self.host_device_attested,
            "real_GGUF_forward_pass_witnessed": False,
            "device_qualified": False,
        }


@dataclass(frozen=True, slots=True)
class DevicePolicy:
    minimum_available_ram_bytes: int = 2_147_483_648
    minimum_available_disk_bytes: int = 1_073_741_824
    maximum_cpu_load_pct: float = 95.0
    maximum_gpu_utilization_pct: float = 95.0
    maximum_temperature_c: float = 90.0
    require_attestation: bool = True
    require_gpu: bool = False
    require_ac_power: bool = False
    maximum_sample_age_ns: int = 10_000_000_000

    def __post_init__(self):
        for x in (self.minimum_available_ram_bytes, self.minimum_available_disk_bytes):
            exact_integer(x, maximum=10**16)
        finite(self.maximum_cpu_load_pct, minimum=1, maximum=100)
        finite(self.maximum_gpu_utilization_pct, minimum=1, maximum=100)
        finite(self.maximum_temperature_c, minimum=0, maximum=200)
        exact_integer(self.maximum_sample_age_ns, minimum=1, maximum=86400000000000)
        for x in (self.require_attestation, self.require_gpu, self.require_ac_power):
            if type(x) is not bool:
                raise ContractHold("device policy must use typed boolean flags")


def evaluate_device(
    snapshot: DeviceSnapshot, policy: DevicePolicy, *,
    observed_at_ns: int,
) -> dict[str, object]:
    if not isinstance(snapshot, DeviceSnapshot) or not isinstance(policy, DevicePolicy):
        raise ContractHold("typed device observation and policy required")
    exact_integer(observed_at_ns, maximum=10**30)
    if snapshot.observed_at_ns > observed_at_ns:
        raise ContractHold("device reading from future is invalid")
    missing, failed, passed = [], [], []
    if observed_at_ns - snapshot.observed_at_ns > policy.maximum_sample_age_ns:
        failed.append("stale_device_sample")
    else:
        passed.append("fresh_device_sample")
    if policy.require_attestation and not snapshot.host_device_attested:
        failed.append("unattested_host")
    elif snapshot.host_device_attested:
        passed.append("attested_host")
    fields = (
        ("ram", snapshot.available_ram_bytes,
         policy.minimum_available_ram_bytes, "min"),
        ("disk", snapshot.available_disk_bytes,
         policy.minimum_available_disk_bytes, "min"),
        ("cpu_load", snapshot.cpu_load_pct,
         policy.maximum_cpu_load_pct, "max"),
        ("temperature", snapshot.temperature_c,
         policy.maximum_temperature_c, "max"),
    )
    if policy.require_gpu:
        fields = (*fields, ("gpu_utilization", snapshot.gpu_utilization_pct,
                           policy.maximum_gpu_utilization_pct, "max"))
    for name, value, threshold, direction in fields:
        if value is None:
            missing.append(name)
        elif (direction == "min" and value < threshold or
              direction == "max" and value > threshold):
            failed.append(name + "_out_of_bounds")
        else:
            passed.append(name + "_within_bounds")
    if policy.require_ac_power:
        if snapshot.power_state == "unknown":
            missing.append("power_state")
        elif snapshot.power_state != "ac":
            failed.append("battery_power")
        else:
            passed.append("ac_power")
    return {
        "schema": "jeeves.fabric.device_policy_result.v1",
        "snapshot_sha256": fingerprint(snapshot.to_record()),
        "passed": tuple(sorted(passed)),
        "missing": tuple(sorted(missing)),
        "failed": tuple(sorted(failed)),
        "preliminary_resource_admission": not (missing or failed),
        "native_device_qualified": False,
        "release_certified": False,
    }


def safe_observation() -> DeviceSnapshot:
    """Collect only locally available, user-visible standard-library signals.

    Memory/GPU/disk sensors absent from portable Python are explicitly None.
    No network lookups, shell processes, subprocess queries, files under the
    user's home, or external monitoring services are read.
    """
    now = time.time_ns()
    cpu = os.cpu_count()
    return DeviceSnapshot(
        observed_at_ns=now, platform_name=platform.system() or "unknown",
        architecture=platform.machine() or "unknown",
        logical_cpu_count=cpu,
        physical_ram_bytes=None,
        available_ram_bytes=None,
        available_disk_bytes=None,
        gpu_memory_bytes=None,
        gpu_utilization_pct=None,
        cpu_load_pct=None,
        temperature_c=None,
        power_state="unknown",
        host_device_attested=False,
    )


__all__ = ["DeviceSnapshot", "DevicePolicy",
           "evaluate_device", "safe_observation"]

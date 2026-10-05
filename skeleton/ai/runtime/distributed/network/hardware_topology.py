"""VOL-031 hardware topology observations and freshness-bound fleet snapshots.

This module is a non-executing inventory plane. It never probes privileged
interfaces, reserves capacity, or schedules work. Platform-specific collectors
may produce :class:`WorkerHardwareObservation` values; this module validates
those observations against exact registered worker generations and produces a
content-addressed topology snapshot suitable for placement/admission evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.shells.worker_identity import WorkerRegistration


HARDWARE_TOPOLOGY_SCHEMA_VERSION = 1
HARDWARE_TOPOLOGY_TASK_ID = "VOL-031"
HARDWARE_TOPOLOGY_ACCOUNTABILITY_ID = "ACC-VOL-031"
_MAX_DEVICES = 256
_MAX_DOMAINS = 64
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HardwareTopologyError(ValueError):
    """Hardware observation or topology snapshot is malformed."""


class DeviceKind(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    ACCELERATOR = "accelerator"
    STORAGE = "storage"
    NETWORK = "network"


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or not _TOKEN.fullmatch(value)
    ):
        raise HardwareTopologyError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise HardwareTopologyError(f"{field} must be lowercase sha256")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HardwareTopologyError(f"{field} must be non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise HardwareTopologyError(f"{field} must be positive integer")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HardwareTopologyError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise HardwareTopologyError(f"{field} must be finite numeric")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0:
        raise HardwareTopologyError(f"{field} must be non-negative")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0:
        raise HardwareTopologyError(f"{field} must be positive")
    return result


def _domains(
    values: Mapping[str, str] | Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, str] = {}
    for key, value in items:
        normalized[_token(key, "topology.key", maximum=64)] = _token(
            value,
            "topology.value",
            maximum=128,
        )
    if len(normalized) > _MAX_DOMAINS:
        raise HardwareTopologyError("topology domain limit exceeded")
    return tuple(sorted(normalized.items()))


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    device_id: str
    kind: DeviceKind | str
    model: str
    memory_bytes: int = 0
    compute_units: int = 0
    numa_node: int | None = None
    healthy: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "device_id",
            _token(self.device_id, "device_id"),
        )
        try:
            object.__setattr__(self, "kind", DeviceKind(self.kind))
        except ValueError as exc:
            raise HardwareTopologyError("invalid device kind") from exc
        object.__setattr__(self, "model", _token(self.model, "model"))
        object.__setattr__(
            self,
            "memory_bytes",
            _nonnegative_int(self.memory_bytes, "memory_bytes"),
        )
        object.__setattr__(
            self,
            "compute_units",
            _nonnegative_int(self.compute_units, "compute_units"),
        )
        if self.numa_node is not None:
            object.__setattr__(
                self,
                "numa_node",
                _nonnegative_int(self.numa_node, "numa_node"),
            )
        if not isinstance(self.healthy, bool):
            raise HardwareTopologyError("healthy must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "kind": self.kind.value,
            "model": self.model,
            "memory_bytes": self.memory_bytes,
            "compute_units": self.compute_units,
            "numa_node": self.numa_node,
            "healthy": self.healthy,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkerHardwareObservation:
    worker_id: str
    generation: int
    cpu_logical_cores: int
    cpu_physical_cores: int
    ram_bytes: int
    storage_free_bytes: int
    network_mbps: float
    numa_nodes: int
    devices: tuple[DeviceDescriptor, ...]
    topology: tuple[tuple[str, str], ...]
    observed_at: float
    source_digest: str
    independent: bool = True
    schema_version: int = HARDWARE_TOPOLOGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "worker_id",
            _token(self.worker_id, "worker_id", maximum=128),
        )
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, "generation"),
        )
        for field in ("cpu_logical_cores", "cpu_physical_cores", "numa_nodes"):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field),
            )
        if self.cpu_physical_cores > self.cpu_logical_cores:
            raise HardwareTopologyError(
                "physical cores cannot exceed logical cores"
            )
        for field in ("ram_bytes", "storage_free_bytes"):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "network_mbps",
            _positive(self.network_mbps, "network_mbps"),
        )
        if (
            not isinstance(self.devices, tuple)
            or len(self.devices) > _MAX_DEVICES
            or any(not isinstance(item, DeviceDescriptor) for item in self.devices)
        ):
            raise HardwareTopologyError(
                "devices must be a bounded tuple of DeviceDescriptor"
            )
        ids = [item.device_id for item in self.devices]
        if len(ids) != len(set(ids)):
            raise HardwareTopologyError("device IDs must be unique")
        object.__setattr__(
            self,
            "devices",
            tuple(sorted(self.devices, key=lambda item: item.device_id)),
        )
        object.__setattr__(self, "topology", _domains(self.topology))
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "source_digest",
            _sha(self.source_digest, "source_digest"),
        )
        if self.independent is not True:
            raise HardwareTopologyError(
                "hardware observation must be independently produced"
            )
        if self.schema_version != HARDWARE_TOPOLOGY_SCHEMA_VERSION:
            raise HardwareTopologyError(
                "unsupported hardware observation schema"
            )

    @property
    def healthy_accelerator_memory_bytes(self) -> int:
        return sum(
            item.memory_bytes
            for item in self.devices
            if item.healthy
            and item.kind in {DeviceKind.GPU, DeviceKind.ACCELERATOR}
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "cpu_logical_cores": self.cpu_logical_cores,
            "cpu_physical_cores": self.cpu_physical_cores,
            "ram_bytes": self.ram_bytes,
            "storage_free_bytes": self.storage_free_bytes,
            "network_mbps": self.network_mbps,
            "numa_nodes": self.numa_nodes,
            "devices": [item.payload() for item in self.devices],
            "topology": [list(item) for item in self.topology],
            "observed_at": self.observed_at,
            "source_digest": self.source_digest,
            "independent": self.independent,
        }

    @property
    def observation_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class HardwareTopologySnapshot:
    observed_at: float
    max_age_s: float
    observations: tuple[WorkerHardwareObservation, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    registration_digest: str
    schema_version: int = HARDWARE_TOPOLOGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "max_age_s",
            _positive(self.max_age_s, "max_age_s"),
        )
        if (
            not isinstance(self.observations, tuple)
            or any(
                not isinstance(item, WorkerHardwareObservation)
                for item in self.observations
            )
        ):
            raise HardwareTopologyError(
                "observations must contain WorkerHardwareObservation"
            )
        ids = [item.worker_id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise HardwareTopologyError(
                "snapshot observations must be worker-unique"
            )
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(self.observations, key=lambda item: item.worker_id)),
        )
        normalized_rejected = tuple(
            sorted(
                (
                    _token(worker_id, "rejected.worker_id", maximum=128),
                    tuple(sorted(set(reasons))),
                )
                for worker_id, reasons in self.rejected
            )
        )
        object.__setattr__(self, "rejected", normalized_rejected)
        object.__setattr__(
            self,
            "registration_digest",
            _sha(self.registration_digest, "registration_digest"),
        )
        if self.schema_version != HARDWARE_TOPOLOGY_SCHEMA_VERSION:
            raise HardwareTopologyError(
                "unsupported topology snapshot schema"
            )

    def by_worker(self) -> dict[str, WorkerHardwareObservation]:
        return {item.worker_id: item for item in self.observations}

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": HARDWARE_TOPOLOGY_TASK_ID,
            "accountability_id": HARDWARE_TOPOLOGY_ACCOUNTABILITY_ID,
            "observed_at": self.observed_at,
            "max_age_s": self.max_age_s,
            "observations": [item.payload() for item in self.observations],
            "rejected": [
                [worker_id, list(reasons)]
                for worker_id, reasons in self.rejected
            ],
            "registration_digest": self.registration_digest,
            "production_authority": False,
        }

    @property
    def snapshot_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


def _registration_digest(
    registrations: Sequence[WorkerRegistration],
) -> str:
    payload = [
        registration.to_dict()
        for registration in sorted(
            registrations,
            key=lambda item: item.identity.key,
        )
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def collect_hardware_topology(
    *,
    registrations: Sequence[WorkerRegistration],
    observations: Mapping[str, WorkerHardwareObservation],
    observed_at: float,
    max_age_s: float,
) -> HardwareTopologySnapshot:
    now = _nonnegative(observed_at, "observed_at")
    age_limit = _positive(max_age_s, "max_age_s")
    if not isinstance(observations, Mapping):
        raise TypeError("observations must be a mapping")

    accepted: list[WorkerHardwareObservation] = []
    rejected: list[tuple[str, tuple[str, ...]]] = []
    seen_workers: set[str] = set()
    registration_list = tuple(registrations)
    for registration in registration_list:
        if not isinstance(registration, WorkerRegistration):
            raise TypeError(
                "registrations must contain WorkerRegistration"
            )
        identity = registration.identity
        if identity.worker_id in seen_workers:
            raise HardwareTopologyError(
                "duplicate worker registration in topology collection"
            )
        seen_workers.add(identity.worker_id)
        reasons: list[str] = []
        observation = observations.get(identity.worker_id)
        if not registration.enabled:
            reasons.append("registration-disabled")
        if observation is None:
            reasons.append("hardware-observation-missing")
        else:
            if observation.worker_id != identity.worker_id:
                reasons.append("hardware-worker-id-mismatch")
            if observation.generation != identity.generation:
                reasons.append("hardware-generation-mismatch")
            if now < observation.observed_at:
                reasons.append("hardware-observation-not-yet-valid")
            elif now - observation.observed_at > age_limit:
                reasons.append("hardware-observation-stale")
            label_map = dict(observation.topology)
            for key in ("zone", "data_boundary"):
                declared = identity.labels.get(key)
                observed = label_map.get(key)
                if declared is not None and observed != declared:
                    reasons.append(f"hardware-topology-{key}-mismatch")
        if reasons:
            rejected.append((identity.worker_id, tuple(reasons)))
        elif observation is not None:
            accepted.append(observation)

    unknown = sorted(set(observations) - seen_workers)
    for worker_id in unknown:
        rejected.append(
            (
                _token(worker_id, "observation.worker_id", maximum=128),
                ("unregistered-hardware-observation",),
            )
        )

    return HardwareTopologySnapshot(
        observed_at=now,
        max_age_s=age_limit,
        observations=tuple(accepted),
        rejected=tuple(rejected),
        registration_digest=_registration_digest(registration_list),
    )


__all__ = [
    "HARDWARE_TOPOLOGY_ACCOUNTABILITY_ID",
    "HARDWARE_TOPOLOGY_SCHEMA_VERSION",
    "HARDWARE_TOPOLOGY_TASK_ID",
    "DeviceDescriptor",
    "DeviceKind",
    "HardwareTopologyError",
    "HardwareTopologySnapshot",
    "WorkerHardwareObservation",
    "collect_hardware_topology",
]

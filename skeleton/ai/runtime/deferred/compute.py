"""Runtime/compute governance for deferred AI capabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class GPUReservation:
    reservation_id: str
    model_id: str
    bytes_reserved: int
    pinned: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "reservation_id", _text(self.reservation_id, "reservation_id"))
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        if isinstance(self.bytes_reserved, bool) or not isinstance(self.bytes_reserved, int) or self.bytes_reserved < 1:
            raise ValueError("bytes_reserved must be positive integer")
        if not isinstance(self.pinned, bool):
            raise TypeError("pinned must be boolean")


class GPUMemoryManager:
    def __init__(self, capacity_bytes: int) -> None:
        if isinstance(capacity_bytes, bool) or not isinstance(capacity_bytes, int) or capacity_bytes < 1:
            raise ValueError("capacity_bytes must be positive integer")
        self.capacity_bytes = capacity_bytes
        self._reservations: dict[str, GPUReservation] = {}

    @property
    def used_bytes(self) -> int:
        return sum(item.bytes_reserved for item in self._reservations.values())

    def reserve(self, reservation: GPUReservation) -> None:
        prior = self._reservations.get(reservation.reservation_id)
        if prior is not None:
            if prior != reservation:
                raise ValueError("GPU reservation identity collision")
            return
        if self.used_bytes + reservation.bytes_reserved > self.capacity_bytes:
            raise RuntimeError("GPU memory capacity exceeded")
        self._reservations[reservation.reservation_id] = reservation

    def release(self, reservation_id: str) -> None:
        try:
            reservation = self._reservations[reservation_id]
        except KeyError as exc:
            raise KeyError("unknown GPU reservation") from exc
        if reservation.pinned:
            raise RuntimeError("pinned reservation cannot be released")
        del self._reservations[reservation_id]


@dataclass(slots=True)
class ModelResidency:
    model_id: str
    reservation_id: str
    in_flight: int = 0
    last_used_clock: int = 0
    pinned: bool = False

    def __post_init__(self) -> None:
        self.model_id = _text(self.model_id, "model_id")
        self.reservation_id = _text(self.reservation_id, "reservation_id")
        if self.in_flight < 0 or self.last_used_clock < 0:
            raise ValueError("model residency counters must be non-negative")


class ModelEvictionController:
    def choose(self, models: Sequence[ModelResidency]) -> ModelResidency:
        candidates = [item for item in models if not item.pinned and item.in_flight == 0]
        if not candidates:
            raise RuntimeError("no safely evictable model")
        return min(candidates, key=lambda item: (item.last_used_clock, item.model_id))


@dataclass(frozen=True, slots=True)
class KVCacheKey:
    model_digest: str
    tokenizer_digest: str
    context_digest: str
    tenant_id: str

    def __post_init__(self) -> None:
        for name in ("model_digest", "tokenizer_digest", "context_digest"):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))

    @property
    def digest(self) -> str:
        return sha256_json({
            "model": self.model_digest,
            "tokenizer": self.tokenizer_digest,
            "context": self.context_digest,
            "tenant": self.tenant_id,
        })


@dataclass(frozen=True, slots=True)
class PrefixCacheKey:
    model_digest: str
    instruction_digest: str
    prefix_digest: str
    data_class: str
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("model_digest", "instruction_digest", "prefix_digest"):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        object.__setattr__(self, "data_class", _text(self.data_class, "data_class"))
        if self.data_class in {"confidential", "restricted"} and not self.tenant_id:
            raise ValueError("sensitive prefix cache requires tenant_id")
        if self.tenant_id is not None:
            object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))

    @property
    def digest(self) -> str:
        return sha256_json({
            "model": self.model_digest,
            "instruction": self.instruction_digest,
            "prefix": self.prefix_digest,
            "data_class": self.data_class,
            "tenant": self.tenant_id,
        })


@dataclass(frozen=True, slots=True)
class SpeculativePair:
    draft_model_digest: str
    target_model_digest: str
    tokenizer_digest: str
    acceptance_threshold: float
    measured_speedup: float

    def __post_init__(self) -> None:
        for name in ("draft_model_digest", "target_model_digest", "tokenizer_digest"):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        if self.draft_model_digest == self.target_model_digest:
            raise ValueError("draft and target models must differ")
        for name in ("acceptance_threshold", "measured_speedup"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if not 0.0 <= self.acceptance_threshold <= 1.0:
            raise ValueError("acceptance_threshold must be in [0,1]")
        if self.measured_speedup <= 1.0:
            raise ValueError("speculative pair must demonstrate speedup")


@dataclass(frozen=True, slots=True)
class NUMANode:
    node_id: int
    cpu_ids: tuple[int, ...]
    memory_bytes: int

    def __post_init__(self) -> None:
        if isinstance(self.node_id, bool) or not isinstance(self.node_id, int) or self.node_id < 0:
            raise ValueError("node_id must be non-negative integer")
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in self.cpu_ids):
            raise ValueError("cpu_ids must be non-negative integers")
        if len(self.cpu_ids) != len(set(self.cpu_ids)):
            raise ValueError("cpu_ids must be unique")
        if isinstance(self.memory_bytes, bool) or not isinstance(self.memory_bytes, int) or self.memory_bytes < 1:
            raise ValueError("memory_bytes must be positive integer")


class NUMAPlanner:
    @staticmethod
    def choose(nodes: Sequence[NUMANode], *, required_memory: int) -> NUMANode:
        if required_memory < 1:
            raise ValueError("required_memory must be positive")
        candidates = [node for node in nodes if node.memory_bytes >= required_memory and node.cpu_ids]
        if not candidates:
            raise RuntimeError("no NUMA node satisfies placement")
        return min(candidates, key=lambda node: (node.memory_bytes, node.node_id))


@dataclass(frozen=True, slots=True)
class InterconnectEdge:
    left_gpu: str
    right_gpu: str
    bandwidth_gbps: float
    latency_us: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "left_gpu", _text(self.left_gpu, "left_gpu"))
        object.__setattr__(self, "right_gpu", _text(self.right_gpu, "right_gpu"))
        if self.left_gpu == self.right_gpu:
            raise ValueError("interconnect self-edge forbidden")
        if self.bandwidth_gbps <= 0 or self.latency_us < 0:
            raise ValueError("invalid interconnect metrics")


class InterconnectGraph:
    def __init__(self, edges: Sequence[InterconnectEdge]) -> None:
        self.edges = tuple(edges)

    def fastest_pair(self) -> tuple[str, str]:
        if not self.edges:
            raise RuntimeError("interconnect graph is empty")
        edge = max(
            self.edges,
            key=lambda item: (item.bandwidth_gbps, -item.latency_us, item.left_gpu, item.right_gpu),
        )
        return tuple(sorted((edge.left_gpu, edge.right_gpu)))


@dataclass(frozen=True, slots=True)
class StorageTier:
    tier_id: str
    priority: int
    writable: bool
    max_object_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "tier_id", _text(self.tier_id, "tier_id"))
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be integer")
        if not isinstance(self.writable, bool):
            raise TypeError("writable must be boolean")
        if isinstance(self.max_object_bytes, bool) or not isinstance(self.max_object_bytes, int) or self.max_object_bytes < 1:
            raise ValueError("max_object_bytes must be positive integer")


class StorageTierPlanner:
    @staticmethod
    def choose(tiers: Sequence[StorageTier], *, object_bytes: int, write: bool) -> StorageTier:
        candidates = [
            tier for tier in tiers
            if object_bytes <= tier.max_object_bytes and (not write or tier.writable)
        ]
        if not candidates:
            raise RuntimeError("no storage tier can satisfy request")
        return min(candidates, key=lambda tier: (tier.priority, tier.tier_id))


@dataclass(frozen=True, slots=True)
class DataPlacement:
    data_id: str
    region: str
    tier_id: str
    replica_digest: str
    stale: bool = False

    def __post_init__(self) -> None:
        for name in ("data_id", "region", "tier_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "replica_digest", _sha(self.replica_digest, "replica_digest"))
        if not isinstance(self.stale, bool):
            raise TypeError("stale must be boolean")


class LocalityPlanner:
    @staticmethod
    def choose(placements: Sequence[DataPlacement], *, allowed_regions: Iterable[str]) -> DataPlacement:
        allowed = set(allowed_regions)
        candidates = [item for item in placements if item.region in allowed and not item.stale]
        if not candidates:
            raise RuntimeError("no fresh data placement in allowed region")
        return min(candidates, key=lambda item: (item.region, item.tier_id, item.data_id))


@dataclass(frozen=True, slots=True)
class WorkerAttestation:
    worker_id: str
    environment_digest: str
    toolchain_digest: str
    trusted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "worker_id", _text(self.worker_id, "worker_id"))
        object.__setattr__(self, "environment_digest", _sha(self.environment_digest, "environment_digest"))
        object.__setattr__(self, "toolchain_digest", _sha(self.toolchain_digest, "toolchain_digest"))
        if not isinstance(self.trusted, bool):
            raise TypeError("trusted must be boolean")


@dataclass(frozen=True, slots=True)
class FarmTask:
    task_id: str
    task_class: str
    environment_digest: str
    priority: int
    tenant_id: str

    def __post_init__(self) -> None:
        for name in ("task_id", "task_class", "tenant_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "environment_digest", _sha(self.environment_digest, "environment_digest"))
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be integer")


class WorkFarm:
    def __init__(self, workers: Sequence[WorkerAttestation]) -> None:
        self.workers = {item.worker_id: item for item in workers}
        if len(self.workers) != len(workers):
            raise ValueError("worker ids must be unique")
        self._assignments: dict[str, str] = {}
        self._load: dict[str, int] = {worker_id: 0 for worker_id in self.workers}

    def assign(self, task: FarmTask) -> str:
        compatible = [
            worker for worker in self.workers.values()
            if worker.trusted and worker.environment_digest == task.environment_digest
        ]
        if not compatible:
            raise RuntimeError("no attested compatible worker")
        worker = min(compatible, key=lambda item: (self._load[item.worker_id], item.worker_id))
        if task.task_id in self._assignments:
            return self._assignments[task.task_id]
        self._assignments[task.task_id] = worker.worker_id
        self._load[worker.worker_id] += 1
        return worker.worker_id


@dataclass(frozen=True, slots=True)
class ResearchProposal:
    proposal_id: str
    purpose: str
    data_classes: tuple[str, ...]
    human_subjects: bool
    autonomous_actions: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "purpose", _text(self.purpose, "purpose"))
        if not isinstance(self.human_subjects, bool) or not isinstance(self.autonomous_actions, bool):
            raise TypeError("proposal flags must be boolean")


class EthicsReview:
    SENSITIVE = {"restricted", "health", "biometric", "financial", "children"}

    @classmethod
    def required(cls, proposal: ResearchProposal) -> bool:
        return (
            proposal.human_subjects
            or proposal.autonomous_actions
            or bool(set(proposal.data_classes) & cls.SENSITIVE)
        )


@dataclass(frozen=True, slots=True)
class SandboxManifest:
    sandbox_id: str
    feature_id: str
    expires_at: int
    network_enabled: bool
    write_authority: bool
    promotion_authority: bool = False

    def __post_init__(self) -> None:
        for name in ("sandbox_id", "feature_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, int) or self.expires_at < 1:
            raise ValueError("expires_at must be positive integer")
        for name in ("network_enabled", "write_authority", "promotion_authority"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be boolean")
        if self.promotion_authority:
            raise ValueError("experimental sandbox cannot hold promotion authority")


@dataclass(frozen=True, slots=True)
class ResearchBranch:
    branch_name: str
    proposal_id: str
    expires_at: int
    evidence_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "branch_name", _text(self.branch_name, "branch_name"))
        object.__setattr__(self, "proposal_id", _text(self.proposal_id, "proposal_id"))
        if not self.branch_name.startswith(("exp/", "research/")):
            raise ValueError("research branch must use exp/ or research/ prefix")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, int) or self.expires_at < 1:
            raise ValueError("expires_at must be positive integer")
        if self.evidence_digest is not None:
            object.__setattr__(self, "evidence_digest", _sha(self.evidence_digest, "evidence_digest"))


@dataclass(frozen=True, slots=True)
class TechniqueRecord:
    technique_id: str
    status: str
    replacement: str | None
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "technique_id", _text(self.technique_id, "technique_id"))
        if self.status not in {"active", "deprecated", "retired"}:
            raise ValueError("unsupported technique status")
        if self.replacement is not None:
            object.__setattr__(self, "replacement", _text(self.replacement, "replacement"))
        if self.status == "retired" and not self.replacement:
            raise ValueError("retired technique needs replacement/archive successor")
        object.__setattr__(self, "evidence_digest", _sha(self.evidence_digest, "evidence_digest"))

"""Pressure-aware, deterministic idle-learning assignment planner for Jeeves.

The Dragon/absorber and candidate training systems may acquire knowledge only
when host telemetry proves spare resources. This planner emits proposals, not
background workers: the host must independently authorize every selected
operation and enforce the same budgets at actual execution time.

No model may assert that the machine is idle. Telemetry, timestamps, and
resource budgets must originate from the owning application runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable


class IdleSchedulerError(ValueError):
    """Invalid trusted telemetry or unsafe idle-work admission."""


MAX_QUEUE = 8192
MAX_SELECTED = 32
MAX_WORK_ID = 192


def _id(value: str, label: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= MAX_WORK_ID
            or value.strip() != value or any(ord(x) < 33 for x in value)):
        raise IdleSchedulerError(f"{label} must be a canonical identifier")
    return value


def _ppm(value: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise IdleSchedulerError(f"{label} must be 0..1000000")
    return value


def _ns(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise IdleSchedulerError(f"{label} must be non-negative nanoseconds")
    return value


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


class IdleWorkKind(str, Enum):
    SOURCE_RESEARCH = "source_research"
    EVIDENCE_CORROBORATION = "evidence_corroboration"
    SHADOW_REVIEW = "shadow_review"
    CANDIDATE_PREPARATION = "candidate_preparation"
    MIRROR_PROPOSAL = "mirror_proposal"
    KNOWLEDGE_REFRESH = "knowledge_refresh"


@dataclass(frozen=True, slots=True)
class HostIdleTelemetry:
    observed_at_ns: int
    last_user_activity_ns: int
    serving_pressure_ppm: int
    cpu_free_ppm: int
    memory_free_ppm: int
    gpu_free_ppm: int
    active_background_workers: int
    pending_interactive_requests: int
    power_saving: bool
    online: bool
    host_observation_digest: str

    def __post_init__(self) -> None:
        _ns(self.observed_at_ns, "observed_at_ns")
        _ns(self.last_user_activity_ns, "last_user_activity_ns")
        if self.last_user_activity_ns > self.observed_at_ns:
            raise IdleSchedulerError("telemetry observes activity from the future")
        for key in ("serving_pressure_ppm", "cpu_free_ppm",
                    "memory_free_ppm", "gpu_free_ppm"):
            _ppm(getattr(self, key), key)
        for key in ("active_background_workers", "pending_interactive_requests"):
            val = getattr(self, key)
            if type(val) is not int or not 0 <= val <= 10_000:
                raise IdleSchedulerError("host worker/request count is invalid")
        if type(self.power_saving) is not bool or type(self.online) is not bool:
            raise IdleSchedulerError("power and connectivity must be booleans")
        value = self.host_observation_digest
        if not isinstance(value, str) or len(value) != 64 or any(
            x not in "0123456789abcdef" for x in value
        ):
            raise IdleSchedulerError("host telemetry digest required")

    @property
    def quiet_ns(self) -> int:
        return self.observed_at_ns - self.last_user_activity_ns


@dataclass(frozen=True, slots=True)
class IdleLearningPolicy:
    minimum_idle_ns: int = 30_000_000_000
    maximum_serving_pressure_ppm: int = 250_000
    minimum_cpu_free_ppm: int = 300_000
    minimum_memory_free_ppm: int = 350_000
    minimum_gpu_free_ppm: int = 450_000
    maximum_concurrent_jobs: int = 3
    maximum_batch_cost_units: int = 64
    maximum_telemetry_age_ns: int = 5_000_000_000

    def __post_init__(self) -> None:
        _ns(self.minimum_idle_ns, "minimum_idle_ns")
        _ns(self.maximum_telemetry_age_ns, "maximum_telemetry_age_ns")
        if not self.maximum_telemetry_age_ns:
            raise IdleSchedulerError("telemetry must have a freshness deadline")
        for key in ("maximum_serving_pressure_ppm", "minimum_cpu_free_ppm",
                    "minimum_memory_free_ppm", "minimum_gpu_free_ppm"):
            _ppm(getattr(self, key), key)
        for key in ("maximum_concurrent_jobs", "maximum_batch_cost_units"):
            v = getattr(self, key)
            if type(v) is not int or not 1 <= v <= 128:
                raise IdleSchedulerError(f"{key} must be within 1..128")


@dataclass(frozen=True, slots=True)
class IdleWorkCandidate:
    work_id: str
    scope_id: str
    source_digest: str
    kind: IdleWorkKind
    relevance_ppm: int
    novelty_ppm: int
    evidence_confidence_ppm: int
    created_at_ns: int
    cost_units: int
    requires_network: bool = False
    requires_accelerator: bool = False

    def __post_init__(self) -> None:
        _id(self.work_id, "work_id")
        _id(self.scope_id, "scope_id")
        if (not isinstance(self.source_digest, str) or len(self.source_digest) != 64
                or any(x not in "0123456789abcdef" for x in self.source_digest)):
            raise IdleSchedulerError("source_digest must be SHA-256")
        if not isinstance(self.kind, IdleWorkKind):
            raise IdleSchedulerError("invalid idle work kind")
        for name in ("relevance_ppm", "novelty_ppm", "evidence_confidence_ppm"):
            _ppm(getattr(self, name), name)
        _ns(self.created_at_ns, "created_at_ns")
        if type(self.cost_units) is not int or not 1 <= self.cost_units <= 128:
            raise IdleSchedulerError("work cost must be within 1..128")
        if type(self.requires_network) is not bool or type(self.requires_accelerator) is not bool:
            raise IdleSchedulerError("work resource flags must be boolean")

    @property
    def score(self) -> int:
        return (
            5 * self.relevance_ppm
            + 3 * self.novelty_ppm
            + 2 * self.evidence_confidence_ppm
        ) // 10


@dataclass(frozen=True, slots=True)
class IdleWorkAssignment:
    work_id: str
    scope_id: str
    kind: IdleWorkKind
    source_digest: str
    score: int
    cost_units: int

    def to_dict(self) -> dict[str, object]:
        return {
            "work_id": self.work_id, "scope_id": self.scope_id,
            "kind": self.kind.value,
            "source_digest": self.source_digest, "score": self.score,
            "cost_units": self.cost_units,
        }


@dataclass(frozen=True, slots=True)
class IdleWorkPlan:
    assignments: tuple[IdleWorkAssignment, ...]
    observed_at_ns: int
    telemetry_digest: str
    plan_reason: str
    required_host_reauthorization: bool
    available_cost_units: int
    allocated_cost_units: int
    deferred_count: int

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "jeeves.idle_work_plan.v1",
            "assignments": [item.to_dict() for item in self.assignments],
            "observed_at_ns": self.observed_at_ns,
            "telemetry_digest": self.telemetry_digest,
            "plan_reason": self.plan_reason,
            "required_host_reauthorization": self.required_host_reauthorization,
            "available_cost_units": self.available_cost_units,
            "allocated_cost_units": self.allocated_cost_units,
            "deferred_count": self.deferred_count,
            "execution_authority": "none",
        }


class JeevesIdleLearningScheduler:
    """Choose useful work only under trustworthy spare capacity."""

    def __init__(self, *, policy: IdleLearningPolicy | None = None) -> None:
        self.policy = policy or IdleLearningPolicy()

    def propose(
        self, candidates: Iterable[IdleWorkCandidate],
        telemetry: HostIdleTelemetry, *,
        host_now_ns: int,
        active_work_ids: tuple[str, ...] = (),
    ) -> IdleWorkPlan:
        if not isinstance(telemetry, HostIdleTelemetry):
            raise IdleSchedulerError("trusted host telemetry required")
        _ns(host_now_ns, "host_now_ns")
        if (host_now_ns < telemetry.observed_at_ns
                or host_now_ns - telemetry.observed_at_ns > self.policy.maximum_telemetry_age_ns):
            raise IdleSchedulerError("host telemetry is stale or from the future")
        queue = tuple(candidates)
        if len(queue) > MAX_QUEUE or any(
            not isinstance(item, IdleWorkCandidate) for item in queue
        ):
            raise IdleSchedulerError("idle workload queue is invalid or unbounded")
        ids = [item.work_id for item in queue]
        if len(set(ids)) != len(ids):
            raise IdleSchedulerError("idle workload has duplicate identities")
        if (not isinstance(active_work_ids, tuple)
                or len(active_work_ids) > MAX_QUEUE
                or len(active_work_ids) != len(set(active_work_ids))):
            raise IdleSchedulerError("invalid active-work exclusions")
        exclude = set(active_work_ids)
        capacity = max(
            0, self.policy.maximum_concurrent_jobs - telemetry.active_background_workers,
        )
        reason = "admitted_idle"
        if telemetry.pending_interactive_requests:
            reason = "interactive_requests_pending"
        elif telemetry.quiet_ns < self.policy.minimum_idle_ns:
            reason = "machine_not_idle"
        elif telemetry.serving_pressure_ppm >= self.policy.maximum_serving_pressure_ppm:
            reason = "serving_pressure"
        elif telemetry.cpu_free_ppm < self.policy.minimum_cpu_free_ppm:
            reason = "cpu_pressure"
        elif telemetry.memory_free_ppm < self.policy.minimum_memory_free_ppm:
            reason = "memory_pressure"
        elif telemetry.power_saving:
            reason = "power_saving"
        elif capacity <= 0:
            reason = "background_worker_cap"
        if reason != "admitted_idle":
            capacity = 0
        available_cost = self.policy.maximum_batch_cost_units if capacity else 0
        ready = []
        for item in queue:
            if item.work_id in exclude or item.created_at_ns > host_now_ns:
                continue
            if item.requires_network and not telemetry.online:
                continue
            if (item.requires_accelerator
                    and telemetry.gpu_free_ppm < self.policy.minimum_gpu_free_ppm):
                continue
            ready.append(item)
        ready.sort(key=lambda item: (
            -item.score, item.created_at_ns, item.work_id,
        ))
        selected: list[IdleWorkAssignment] = []
        spent = 0
        for item in ready:
            if len(selected) >= min(capacity, MAX_SELECTED):
                break
            if spent + item.cost_units > available_cost:
                continue
            selected.append(IdleWorkAssignment(
                work_id=item.work_id, scope_id=item.scope_id,
                kind=item.kind, source_digest=item.source_digest,
                score=item.score, cost_units=item.cost_units,
            ))
            spent += item.cost_units
        return IdleWorkPlan(
            assignments=tuple(selected),
            observed_at_ns=telemetry.observed_at_ns,
            telemetry_digest=telemetry.host_observation_digest,
            plan_reason=reason if not selected else "admitted_idle",
            required_host_reauthorization=True,
            available_cost_units=available_cost,
            allocated_cost_units=spent,
            deferred_count=len(queue) - len(selected),
        )


__all__ = [
    "IdleSchedulerError", "IdleWorkKind", "HostIdleTelemetry",
    "IdleLearningPolicy", "IdleWorkCandidate", "IdleWorkAssignment",
    "IdleWorkPlan", "JeevesIdleLearningScheduler",
]

"""P1 load and capacity qualification.

This module is a non-executing decision plane. It does not scale workers,
admit traffic, or mutate runtime state. It binds declared load profiles to an
accepted DIST-03 autoscaling decision and independently measured load,
partition, shedding, stale-worker, and cost-reconciliation evidence.

A saturated service may qualify only when degradation is explicit and
controlled. A partition may never permit stale-worker commits. Accounting
must reconcile exactly within the declared tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.distributed.mesh.batching_autoscaling import AutoscalingDecision
from skeleton.shells.worker_scaling import ScalingAction


CAPACITY_QUALIFICATION_SCHEMA_VERSION = 1
CAPACITY_QUALIFICATION_TASK_ID = "P1-DIST-04"
CAPACITY_QUALIFICATION_ACCOUNTABILITY_ID = "ACC-P1-DIST-04"
_MAX_EVIDENCE = 256
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CapacityQualificationError(ValueError):
    """Capacity qualification evidence is malformed or unsafe."""


class CapacityDisposition(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SATURATED = "saturated"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CapacityQualificationError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise CapacityQualificationError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise CapacityQualificationError(
            f"{field} must be a canonical token"
        )
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CapacityQualificationError(
            f"{field} must be lowercase sha256"
        )
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CapacityQualificationError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise CapacityQualificationError(f"{field} must be finite numeric")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0:
        raise CapacityQualificationError(f"{field} must be non-negative")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0.0:
        raise CapacityQualificationError(f"{field} must be positive")
    return result


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CapacityQualificationError(
            f"{field} must be a non-negative integer"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise CapacityQualificationError(f"{field} must be positive")
    return value


def _unit_interval(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0 or result > 1.0:
        raise CapacityQualificationError(
            f"{field} must be between 0 and 1"
        )
    return result


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapacityQualificationError(
            "capacity payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise CapacityQualificationError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise CapacityQualificationError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence source")
        _sha256(item.digest, "evidence digest")
        _token(item.category, "evidence category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise CapacityQualificationError("evidence_refs must be non-empty")
    if len(by_key) > _MAX_EVIDENCE:
        raise CapacityQualificationError("evidence_refs exceeds item limit")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class LoadCapacityProfile:
    profile_id: str
    max_workers: int
    max_queue_depth: int
    target_p99_latency_ms: float
    max_error_rate: float
    max_cancellation_rate: float
    max_measured_cost_usd: float
    max_cost_reconciliation_error_usd: float
    observation_max_age_s: float
    schema_version: int = CAPACITY_QUALIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _token(self.profile_id, "profile_id"),
        )
        object.__setattr__(
            self,
            "max_workers",
            _positive_int(self.max_workers, "max_workers"),
        )
        object.__setattr__(
            self,
            "max_queue_depth",
            _positive_int(self.max_queue_depth, "max_queue_depth"),
        )
        object.__setattr__(
            self,
            "target_p99_latency_ms",
            _positive(
                self.target_p99_latency_ms,
                "target_p99_latency_ms",
            ),
        )
        for field in ("max_error_rate", "max_cancellation_rate"):
            object.__setattr__(
                self,
                field,
                _unit_interval(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "max_measured_cost_usd",
            _nonnegative(
                self.max_measured_cost_usd,
                "max_measured_cost_usd",
            ),
        )
        object.__setattr__(
            self,
            "max_cost_reconciliation_error_usd",
            _nonnegative(
                self.max_cost_reconciliation_error_usd,
                "max_cost_reconciliation_error_usd",
            ),
        )
        object.__setattr__(
            self,
            "observation_max_age_s",
            _positive(
                self.observation_max_age_s,
                "observation_max_age_s",
            ),
        )
        if self.schema_version != CAPACITY_QUALIFICATION_SCHEMA_VERSION:
            raise CapacityQualificationError(
                "unsupported load profile schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "max_workers": self.max_workers,
            "max_queue_depth": self.max_queue_depth,
            "target_p99_latency_ms": self.target_p99_latency_ms,
            "max_error_rate": self.max_error_rate,
            "max_cancellation_rate": self.max_cancellation_rate,
            "max_measured_cost_usd": self.max_measured_cost_usd,
            "max_cost_reconciliation_error_usd": (
                self.max_cost_reconciliation_error_usd
            ),
            "observation_max_age_s": self.observation_max_age_s,
        }

    @property
    def profile_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class CapacityObservation:
    profile_digest: str
    autoscaling_decision_digest: str
    observed_at: float
    healthy_workers: int
    queue_depth: int
    p99_latency_ms: float
    error_rate: float
    cancellation_rate: float
    offered_requests: int
    completed_requests: int
    rejected_requests: int
    shed_requests: int
    partition_events: int
    stale_worker_commits: int
    measured_cost_usd: float
    accounted_cost_usd: float
    evidence_refs: tuple[EvidenceRef, ...]
    independent: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_digest",
            _sha256(self.profile_digest, "profile_digest"),
        )
        object.__setattr__(
            self,
            "autoscaling_decision_digest",
            _sha256(
                self.autoscaling_decision_digest,
                "autoscaling_decision_digest",
            ),
        )
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "healthy_workers",
            _positive_int(self.healthy_workers, "healthy_workers"),
        )
        for field in (
            "queue_depth",
            "offered_requests",
            "completed_requests",
            "rejected_requests",
            "shed_requests",
            "partition_events",
            "stale_worker_commits",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "p99_latency_ms",
            _nonnegative(self.p99_latency_ms, "p99_latency_ms"),
        )
        for field in ("error_rate", "cancellation_rate"):
            object.__setattr__(
                self,
                field,
                _unit_interval(getattr(self, field), field),
            )
        for field in ("measured_cost_usd", "accounted_cost_usd"):
            object.__setattr__(
                self,
                field,
                _nonnegative(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        if self.independent is not True:
            raise CapacityQualificationError(
                "capacity observation must be independently verified"
            )
        if self.offered_requests < 1:
            raise CapacityQualificationError(
                "offered_requests must be positive"
            )

    @property
    def accounted_requests(self) -> int:
        return (
            self.completed_requests
            + self.rejected_requests
            + self.shed_requests
        )

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())

    def payload(self) -> dict[str, Any]:
        return {
            "profile_digest": self.profile_digest,
            "autoscaling_decision_digest": self.autoscaling_decision_digest,
            "observed_at": self.observed_at,
            "healthy_workers": self.healthy_workers,
            "queue_depth": self.queue_depth,
            "p99_latency_ms": self.p99_latency_ms,
            "error_rate": self.error_rate,
            "cancellation_rate": self.cancellation_rate,
            "offered_requests": self.offered_requests,
            "completed_requests": self.completed_requests,
            "rejected_requests": self.rejected_requests,
            "shed_requests": self.shed_requests,
            "accounted_requests": self.accounted_requests,
            "partition_events": self.partition_events,
            "stale_worker_commits": self.stale_worker_commits,
            "measured_cost_usd": self.measured_cost_usd,
            "accounted_cost_usd": self.accounted_cost_usd,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "independent": self.independent,
        }


@dataclass(frozen=True, slots=True)
class CapacityQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    disposition: CapacityDisposition
    profile_digest: str
    autoscaling_decision_digest: str
    observation_digest: str
    queue_utilization: float
    cost_reconciliation_error_usd: float
    task_id: str = CAPACITY_QUALIFICATION_TASK_ID
    accountability_id: str = CAPACITY_QUALIFICATION_ACCOUNTABILITY_ID
    schema_version: int = CAPACITY_QUALIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise CapacityQualificationError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise CapacityQualificationError(
                "reasons must contain non-empty strings"
            )
        try:
            object.__setattr__(
                self,
                "disposition",
                CapacityDisposition(self.disposition),
            )
        except ValueError as exc:
            raise CapacityQualificationError(
                "invalid capacity disposition"
            ) from exc
        for field in (
            "profile_digest",
            "autoscaling_decision_digest",
            "observation_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "queue_utilization",
            _nonnegative(self.queue_utilization, "queue_utilization"),
        )
        object.__setattr__(
            self,
            "cost_reconciliation_error_usd",
            _nonnegative(
                self.cost_reconciliation_error_usd,
                "cost_reconciliation_error_usd",
            ),
        )
        if self.task_id != CAPACITY_QUALIFICATION_TASK_ID:
            raise CapacityQualificationError("task_id drift")
        if self.accountability_id != CAPACITY_QUALIFICATION_ACCOUNTABILITY_ID:
            raise CapacityQualificationError("accountability_id drift")
        if self.schema_version != CAPACITY_QUALIFICATION_SCHEMA_VERSION:
            raise CapacityQualificationError(
                "unsupported capacity decision schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "disposition": self.disposition.value,
            "profile_digest": self.profile_digest,
            "autoscaling_decision_digest": self.autoscaling_decision_digest,
            "observation_digest": self.observation_digest,
            "queue_utilization": self.queue_utilization,
            "cost_reconciliation_error_usd": (
                self.cost_reconciliation_error_usd
            ),
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-04:capacity-qualification",
    ) -> EvidenceRef:
        if not self.accepted:
            raise CapacityQualificationError(
                "rejected capacity qualification cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="capacity_qualification",
        )


def qualify_capacity(
    *,
    profile: LoadCapacityProfile,
    autoscaling_decision: AutoscalingDecision,
    observation: CapacityObservation,
    observed_at: float,
) -> CapacityQualificationDecision:
    if not isinstance(profile, LoadCapacityProfile):
        raise TypeError("profile must be LoadCapacityProfile")
    if not isinstance(autoscaling_decision, AutoscalingDecision):
        raise TypeError(
            "autoscaling_decision must be AutoscalingDecision"
        )
    if not isinstance(observation, CapacityObservation):
        raise TypeError("observation must be CapacityObservation")

    now = _nonnegative(observed_at, "observed_at")
    reasons: list[str] = []

    if observation.profile_digest != profile.profile_digest:
        reasons.append("load-profile-digest-mismatch")
    if (
        observation.autoscaling_decision_digest
        != autoscaling_decision.decision_digest
    ):
        reasons.append("autoscaling-decision-digest-mismatch")
    if not autoscaling_decision.accepted:
        reasons.append("autoscaling-decision-rejected")
    if observation.healthy_workers != autoscaling_decision.current_workers:
        reasons.append("healthy-worker-count-mismatch")
    if autoscaling_decision.desired_workers > profile.max_workers:
        reasons.append("desired-workers-exceed-profile")
    if observation.healthy_workers > profile.max_workers:
        reasons.append("healthy-workers-exceed-profile")
    if now < observation.observed_at:
        reasons.append("observation-not-yet-valid")
    if now - observation.observed_at > profile.observation_max_age_s:
        reasons.append("observation-stale")

    if observation.accounted_requests != observation.offered_requests:
        reasons.append("request-accounting-divergence")
    if observation.stale_worker_commits != 0:
        reasons.append("stale-worker-commit-detected")

    cost_error = abs(
        observation.measured_cost_usd - observation.accounted_cost_usd
    )
    if observation.measured_cost_usd > profile.max_measured_cost_usd:
        reasons.append("measured-cost-budget-exceeded")
    if cost_error > profile.max_cost_reconciliation_error_usd:
        reasons.append("cost-reconciliation-divergence")

    queue_pressure = observation.queue_depth >= profile.max_queue_depth
    latency_pressure = (
        observation.p99_latency_ms > profile.target_p99_latency_ms
    )
    error_pressure = observation.error_rate > profile.max_error_rate
    cancellation_pressure = (
        observation.cancellation_rate > profile.max_cancellation_rate
    )
    pressured = (
        queue_pressure
        or latency_pressure
        or error_pressure
        or cancellation_pressure
    )
    saturated = pressured and observation.healthy_workers >= profile.max_workers

    if pressured:
        if autoscaling_decision.action is ScalingAction.SCALE_IN:
            reasons.append("scale-in-under-capacity-pressure")
        if observation.healthy_workers < profile.max_workers:
            if autoscaling_decision.action is not ScalingAction.SCALE_OUT:
                reasons.append("capacity-pressure-without-scale-out")
        elif observation.shed_requests < 1:
            reasons.append("saturation-without-load-shedding")

    if observation.partition_events > 0 and pressured:
        if observation.shed_requests < 1 and saturated:
            reasons.append("partition-saturation-without-shedding")
    if observation.partition_events > 0 and observation.stale_worker_commits:
        reasons.append("partition-stale-worker-commit")

    if saturated:
        disposition = CapacityDisposition.SATURATED
    elif pressured:
        disposition = CapacityDisposition.DEGRADED
    else:
        disposition = CapacityDisposition.HEALTHY

    normalized = tuple(sorted(set(reasons)))
    return CapacityQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        disposition=disposition,
        profile_digest=profile.profile_digest,
        autoscaling_decision_digest=autoscaling_decision.decision_digest,
        observation_digest=observation.observation_digest,
        queue_utilization=(
            observation.queue_depth / profile.max_queue_depth
        ),
        cost_reconciliation_error_usd=cost_error,
    )


__all__ = [
    "CAPACITY_QUALIFICATION_ACCOUNTABILITY_ID",
    "CAPACITY_QUALIFICATION_SCHEMA_VERSION",
    "CAPACITY_QUALIFICATION_TASK_ID",
    "CapacityDisposition",
    "CapacityObservation",
    "CapacityQualificationDecision",
    "CapacityQualificationError",
    "LoadCapacityProfile",
    "qualify_capacity",
]

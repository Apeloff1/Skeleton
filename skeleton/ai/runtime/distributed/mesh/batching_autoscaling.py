"""P1 deadline-aware continuous batching and autoscaling qualification.

This module is a pure decision plane. It does not execute inference, mutate a
worker fleet, or create infrastructure. It binds batching and scaling decisions
to an accepted DIST-02 placement and to independently measured service
objectives.

Safety properties:
- cancelled or expired work is never admitted to a batch;
- batching is deterministic and earliest-deadline-first;
- adding an item may not make any selected item's deadline infeasible;
- every item binds the exact placement/model/tenant/quality policy;
- autoscaling may not treat poor model quality as a capacity problem;
- scale-in is forbidden while latency/cancellation/error budgets are stressed;
- tail-latency/cancellation pressure must scale out or fail closed at max size;
- telemetry must be fresh, independently verified, and bound to placement.
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
from skeleton.network.model_placement import (
    ModelPlacementDecision,
    ModelPlacementRequest,
)
from skeleton.shells.worker_scaling import (
    ScalingAction,
    ScalingPolicy,
    WorkerScaler,
)


BATCH_AUTOSCALE_SCHEMA_VERSION = 1
BATCH_AUTOSCALE_TASK_ID = "P1-DIST-03"
BATCH_AUTOSCALE_ACCOUNTABILITY_ID = "ACC-P1-DIST-03"
_MAX_ITEMS = 512
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BatchingAutoscalingError(ValueError):
    """Batching/autoscaling evidence is malformed or unsafe."""


class DispatchDisposition(str, Enum):
    READY = "ready"
    WAIT = "wait"
    EMPTY = "empty"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchingAutoscalingError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise BatchingAutoscalingError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise BatchingAutoscalingError(
            f"{field} must be a canonical token"
        )
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BatchingAutoscalingError(
            f"{field} must be lowercase sha256"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BatchingAutoscalingError(
            f"{field} must be a positive integer"
        )
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BatchingAutoscalingError(
            f"{field} must be a non-negative integer"
        )
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BatchingAutoscalingError(
            f"{field} must be finite numeric"
        )
    result = float(value)
    if not math.isfinite(result):
        raise BatchingAutoscalingError(
            f"{field} must be finite numeric"
        )
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0:
        raise BatchingAutoscalingError(f"{field} must be positive")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0:
        raise BatchingAutoscalingError(
            f"{field} must be non-negative"
        )
    return result


def _unit_interval(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0 or result > 1.0:
        raise BatchingAutoscalingError(
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
        raise BatchingAutoscalingError(
            "batching/autoscaling payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise BatchingAutoscalingError(
            "evidence_refs must contain EvidenceRef"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise BatchingAutoscalingError(
                "evidence_refs must contain EvidenceRef"
            )
        _text(item.source, "evidence source")
        _sha256(item.digest, "evidence digest")
        _token(item.category, "evidence category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise BatchingAutoscalingError(
            "evidence_refs must be non-empty"
        )
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class ContinuousBatchItem:
    item_id: str
    tenant_id: str
    placement_request_digest: str
    placement_decision_digest: str
    model_digest: str
    input_digest: str
    quality_policy_digest: str
    enqueued_at: float
    deadline_at: float
    estimated_runtime_s: float
    cancelled: bool = False

    def __post_init__(self) -> None:
        for field in ("item_id", "tenant_id"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        for field in (
            "placement_request_digest",
            "placement_decision_digest",
            "model_digest",
            "input_digest",
            "quality_policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        enqueued = _nonnegative(self.enqueued_at, "enqueued_at")
        deadline = _positive(self.deadline_at, "deadline_at")
        if deadline <= enqueued:
            raise BatchingAutoscalingError(
                "deadline_at must exceed enqueued_at"
            )
        object.__setattr__(self, "enqueued_at", enqueued)
        object.__setattr__(self, "deadline_at", deadline)
        object.__setattr__(
            self,
            "estimated_runtime_s",
            _positive(
                self.estimated_runtime_s,
                "estimated_runtime_s",
            ),
        )
        if not isinstance(self.cancelled, bool):
            raise BatchingAutoscalingError(
                "cancelled must be boolean"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "tenant_id": self.tenant_id,
            "placement_request_digest": self.placement_request_digest,
            "placement_decision_digest": self.placement_decision_digest,
            "model_digest": self.model_digest,
            "input_digest": self.input_digest,
            "quality_policy_digest": self.quality_policy_digest,
            "enqueued_at": self.enqueued_at,
            "deadline_at": self.deadline_at,
            "estimated_runtime_s": self.estimated_runtime_s,
            "cancelled": self.cancelled,
        }

    @property
    def item_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ContinuousBatchPolicy:
    policy_id: str
    max_batch_size: int
    max_wait_s: float
    max_batch_runtime_s: float
    per_extra_item_overhead_s: float
    schema_version: int = BATCH_AUTOSCALE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "max_batch_size",
            _positive_int(self.max_batch_size, "max_batch_size"),
        )
        if self.max_batch_size > _MAX_ITEMS:
            raise BatchingAutoscalingError(
                "max_batch_size exceeds item limit"
            )
        object.__setattr__(
            self,
            "max_wait_s",
            _positive(self.max_wait_s, "max_wait_s"),
        )
        object.__setattr__(
            self,
            "max_batch_runtime_s",
            _positive(
                self.max_batch_runtime_s,
                "max_batch_runtime_s",
            ),
        )
        object.__setattr__(
            self,
            "per_extra_item_overhead_s",
            _nonnegative(
                self.per_extra_item_overhead_s,
                "per_extra_item_overhead_s",
            ),
        )
        if self.schema_version != BATCH_AUTOSCALE_SCHEMA_VERSION:
            raise BatchingAutoscalingError(
                "unsupported batch policy schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "max_batch_size": self.max_batch_size,
            "max_wait_s": self.max_wait_s,
            "max_batch_runtime_s": self.max_batch_runtime_s,
            "per_extra_item_overhead_s": self.per_extra_item_overhead_s,
        }

    @property
    def policy_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ContinuousBatchDecision:
    accepted: bool
    reasons: tuple[str, ...]
    disposition: DispatchDisposition
    placement_request_digest: str
    placement_decision_digest: str
    policy_digest: str
    selected_item_ids: tuple[str, ...]
    selected_item_digests: tuple[str, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    predicted_runtime_s: float
    earliest_deadline_at: float | None
    observed_at: float
    task_id: str = BATCH_AUTOSCALE_TASK_ID
    accountability_id: str = BATCH_AUTOSCALE_ACCOUNTABILITY_ID
    schema_version: int = BATCH_AUTOSCALE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BatchingAutoscalingError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise BatchingAutoscalingError(
                "reasons must contain non-empty strings"
            )
        try:
            object.__setattr__(
                self,
                "disposition",
                DispatchDisposition(self.disposition),
            )
        except ValueError as exc:
            raise BatchingAutoscalingError(
                "invalid dispatch disposition"
            ) from exc
        for field in (
            "placement_request_digest",
            "placement_decision_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if len(self.selected_item_ids) != len(
            self.selected_item_digests
        ):
            raise BatchingAutoscalingError(
                "selected item id/digest coverage mismatch"
            )
        if len(set(self.selected_item_ids)) != len(
            self.selected_item_ids
        ):
            raise BatchingAutoscalingError(
                "selected item IDs must be unique"
            )
        for item_id in self.selected_item_ids:
            _token(item_id, "selected_item_id")
        for digest in self.selected_item_digests:
            _sha256(digest, "selected_item_digest")
        object.__setattr__(
            self,
            "predicted_runtime_s",
            _nonnegative(
                self.predicted_runtime_s,
                "predicted_runtime_s",
            ),
        )
        if self.earliest_deadline_at is not None:
            object.__setattr__(
                self,
                "earliest_deadline_at",
                _positive(
                    self.earliest_deadline_at,
                    "earliest_deadline_at",
                ),
            )
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        if self.disposition is DispatchDisposition.READY and (
            not self.accepted or not self.selected_item_ids
        ):
            raise BatchingAutoscalingError(
                "ready batch must be accepted and non-empty"
            )
        if self.task_id != BATCH_AUTOSCALE_TASK_ID:
            raise BatchingAutoscalingError("task_id drift")
        if self.accountability_id != BATCH_AUTOSCALE_ACCOUNTABILITY_ID:
            raise BatchingAutoscalingError("accountability_id drift")
        if self.schema_version != BATCH_AUTOSCALE_SCHEMA_VERSION:
            raise BatchingAutoscalingError(
                "unsupported batch decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "disposition": self.disposition.value,
            "placement_request_digest": self.placement_request_digest,
            "placement_decision_digest": self.placement_decision_digest,
            "policy_digest": self.policy_digest,
            "selected_item_ids": list(self.selected_item_ids),
            "selected_item_digests": list(self.selected_item_digests),
            "rejected": [
                [item_id, list(reasons)]
                for item_id, reasons in self.rejected
            ],
            "predicted_runtime_s": self.predicted_runtime_s,
            "earliest_deadline_at": self.earliest_deadline_at,
            "observed_at": self.observed_at,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-03:continuous-batch",
    ) -> EvidenceRef:
        if not self.accepted or self.disposition is not DispatchDisposition.READY:
            raise BatchingAutoscalingError(
                "non-ready batch cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="continuous_batch",
        )


def _predicted_runtime(
    items: tuple[ContinuousBatchItem, ...],
    policy: ContinuousBatchPolicy,
) -> float:
    if not items:
        return 0.0
    return max(item.estimated_runtime_s for item in items) + (
        policy.per_extra_item_overhead_s * (len(items) - 1)
    )


def plan_continuous_batch(
    *,
    items: Iterable[ContinuousBatchItem],
    placement_request: ModelPlacementRequest,
    placement_decision: ModelPlacementDecision,
    policy: ContinuousBatchPolicy,
    observed_at: float,
) -> ContinuousBatchDecision:
    if not isinstance(placement_request, ModelPlacementRequest):
        raise TypeError(
            "placement_request must be ModelPlacementRequest"
        )
    if not isinstance(placement_decision, ModelPlacementDecision):
        raise TypeError(
            "placement_decision must be ModelPlacementDecision"
        )
    if not isinstance(policy, ContinuousBatchPolicy):
        raise TypeError("policy must be ContinuousBatchPolicy")
    now = _nonnegative(observed_at, "observed_at")
    raw_items = tuple(items)
    if len(raw_items) > _MAX_ITEMS:
        raise BatchingAutoscalingError(
            "batch input exceeds item limit"
        )
    if any(not isinstance(item, ContinuousBatchItem) for item in raw_items):
        raise TypeError(
            "items must contain ContinuousBatchItem"
        )
    if len({item.item_id for item in raw_items}) != len(raw_items):
        raise BatchingAutoscalingError(
            "batch item IDs must be unique"
        )

    global_reasons: list[str] = []
    if not placement_decision.accepted:
        global_reasons.append("placement-decision-rejected")
    if (
        placement_decision.request_digest
        != placement_request.request_digest
    ):
        global_reasons.append("placement-request-digest-mismatch")

    rejected: dict[str, list[str]] = {}
    eligible: list[ContinuousBatchItem] = []
    for item in sorted(
        raw_items,
        key=lambda row: (row.deadline_at, row.item_id),
    ):
        reasons: list[str] = []
        if item.cancelled:
            reasons.append("cancelled")
        if item.deadline_at <= now:
            reasons.append("deadline-expired")
        if item.tenant_id != placement_request.tenant_id:
            reasons.append("tenant-mismatch")
        if (
            item.placement_request_digest
            != placement_request.request_digest
        ):
            reasons.append("placement-request-mismatch")
        if (
            item.placement_decision_digest
            != placement_decision.decision_digest
        ):
            reasons.append("placement-decision-mismatch")
        if item.model_digest != placement_request.model_digest:
            reasons.append("model-digest-mismatch")
        if reasons:
            rejected[item.item_id] = reasons
            continue
        eligible.append(item)

    selected: list[ContinuousBatchItem] = []
    quality_policy: str | None = None
    for item in eligible:
        if len(selected) >= policy.max_batch_size:
            rejected.setdefault(item.item_id, []).append(
                "batch-capacity"
            )
            continue
        if quality_policy is None:
            quality_policy = item.quality_policy_digest
        elif item.quality_policy_digest != quality_policy:
            rejected.setdefault(item.item_id, []).append(
                "quality-policy-mismatch"
            )
            continue

        candidate = tuple((*selected, item))
        runtime = _predicted_runtime(candidate, policy)
        if runtime > policy.max_batch_runtime_s:
            rejected.setdefault(item.item_id, []).append(
                "batch-runtime-budget"
            )
            continue
        if any(
            now + runtime > selected_item.deadline_at
            for selected_item in candidate
        ):
            rejected.setdefault(item.item_id, []).append(
                "deadline-infeasible"
            )
            continue
        selected.append(item)

    selected_tuple = tuple(selected)
    runtime = _predicted_runtime(selected_tuple, policy)
    earliest = (
        None
        if not selected_tuple
        else min(item.deadline_at for item in selected_tuple)
    )
    disposition = DispatchDisposition.EMPTY
    if selected_tuple:
        oldest_wait = max(
            0.0,
            now - min(item.enqueued_at for item in selected_tuple),
        )
        deadline_pressure = (
            earliest is not None
            and earliest - now <= runtime + policy.max_wait_s
        )
        if (
            len(selected_tuple) >= policy.max_batch_size
            or oldest_wait >= policy.max_wait_s
            or deadline_pressure
        ):
            disposition = DispatchDisposition.READY
        else:
            disposition = DispatchDisposition.WAIT

    accepted = not global_reasons
    normalized_rejected = tuple(
        (item_id, tuple(sorted(set(item_reasons))))
        for item_id, item_reasons in sorted(rejected.items())
    )
    return ContinuousBatchDecision(
        accepted=accepted,
        reasons=tuple(sorted(set(global_reasons))),
        disposition=disposition,
        placement_request_digest=placement_request.request_digest,
        placement_decision_digest=placement_decision.decision_digest,
        policy_digest=policy.policy_digest,
        selected_item_ids=tuple(
            item.item_id for item in selected_tuple
        ),
        selected_item_digests=tuple(
            item.item_digest for item in selected_tuple
        ),
        rejected=normalized_rejected,
        predicted_runtime_s=runtime,
        earliest_deadline_at=earliest,
        observed_at=now,
    )


@dataclass(frozen=True, slots=True)
class ServiceObjectivePolicy:
    policy_id: str
    target_p99_latency_ms: float
    max_cancellation_rate: float
    max_error_rate: float
    min_quality_score: float
    observation_max_age_s: float
    target_queue_per_worker: float
    scale_out_queue_per_worker: float
    scale_in_queue_per_worker: float
    min_workers: int
    max_workers: int
    max_scale_step: int
    schema_version: int = BATCH_AUTOSCALE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "target_p99_latency_ms",
            _positive(
                self.target_p99_latency_ms,
                "target_p99_latency_ms",
            ),
        )
        for field in (
            "max_cancellation_rate",
            "max_error_rate",
            "min_quality_score",
        ):
            object.__setattr__(
                self,
                field,
                _unit_interval(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "observation_max_age_s",
            _positive(
                self.observation_max_age_s,
                "observation_max_age_s",
            ),
        )
        target = _positive(
            self.target_queue_per_worker,
            "target_queue_per_worker",
        )
        out = _positive(
            self.scale_out_queue_per_worker,
            "scale_out_queue_per_worker",
        )
        scale_in = _nonnegative(
            self.scale_in_queue_per_worker,
            "scale_in_queue_per_worker",
        )
        if not scale_in < target < out:
            raise BatchingAutoscalingError(
                "invalid queue scaling thresholds"
            )
        object.__setattr__(
            self,
            "target_queue_per_worker",
            target,
        )
        object.__setattr__(
            self,
            "scale_out_queue_per_worker",
            out,
        )
        object.__setattr__(
            self,
            "scale_in_queue_per_worker",
            scale_in,
        )
        min_workers = _positive_int(self.min_workers, "min_workers")
        max_workers = _positive_int(self.max_workers, "max_workers")
        if max_workers < min_workers:
            raise BatchingAutoscalingError(
                "max_workers must be >= min_workers"
            )
        object.__setattr__(self, "min_workers", min_workers)
        object.__setattr__(self, "max_workers", max_workers)
        object.__setattr__(
            self,
            "max_scale_step",
            _positive_int(self.max_scale_step, "max_scale_step"),
        )
        if self.schema_version != BATCH_AUTOSCALE_SCHEMA_VERSION:
            raise BatchingAutoscalingError(
                "unsupported SLO policy schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "target_p99_latency_ms": self.target_p99_latency_ms,
            "max_cancellation_rate": self.max_cancellation_rate,
            "max_error_rate": self.max_error_rate,
            "min_quality_score": self.min_quality_score,
            "observation_max_age_s": self.observation_max_age_s,
            "target_queue_per_worker": self.target_queue_per_worker,
            "scale_out_queue_per_worker": (
                self.scale_out_queue_per_worker
            ),
            "scale_in_queue_per_worker": (
                self.scale_in_queue_per_worker
            ),
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "max_scale_step": self.max_scale_step,
        }

    @property
    def policy_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ServiceObjectiveObservation:
    window_id: str
    placement_decision_digest: str
    sample_count: int
    healthy_workers: int
    queued: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    cancellation_rate: float
    error_rate: float
    quality_score: float
    observed_at: float
    evidence_refs: tuple[EvidenceRef, ...]
    verifier_id: str
    verifier_digest: str
    independent: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _token(self.window_id, "window_id"),
        )
        object.__setattr__(
            self,
            "placement_decision_digest",
            _sha256(
                self.placement_decision_digest,
                "placement_decision_digest",
            ),
        )
        object.__setattr__(
            self,
            "sample_count",
            _positive_int(self.sample_count, "sample_count"),
        )
        object.__setattr__(
            self,
            "healthy_workers",
            _nonnegative_int(
                self.healthy_workers,
                "healthy_workers",
            ),
        )
        object.__setattr__(
            self,
            "queued",
            _nonnegative_int(self.queued, "queued"),
        )
        p50 = _nonnegative(self.p50_latency_ms, "p50_latency_ms")
        p95 = _nonnegative(self.p95_latency_ms, "p95_latency_ms")
        p99 = _nonnegative(self.p99_latency_ms, "p99_latency_ms")
        if not p50 <= p95 <= p99:
            raise BatchingAutoscalingError(
                "latency percentiles must be monotonic"
            )
        object.__setattr__(self, "p50_latency_ms", p50)
        object.__setattr__(self, "p95_latency_ms", p95)
        object.__setattr__(self, "p99_latency_ms", p99)
        for field in (
            "cancellation_rate",
            "error_rate",
            "quality_score",
        ):
            object.__setattr__(
                self,
                field,
                _unit_interval(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _token(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "verifier_digest",
            _sha256(self.verifier_digest, "verifier_digest"),
        )
        if self.independent is not True:
            raise BatchingAutoscalingError(
                "service-objective observation must be independent"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "placement_decision_digest": self.placement_decision_digest,
            "sample_count": self.sample_count,
            "healthy_workers": self.healthy_workers,
            "queued": self.queued,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "cancellation_rate": self.cancellation_rate,
            "error_rate": self.error_rate,
            "quality_score": self.quality_score,
            "observed_at": self.observed_at,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "independent": self.independent,
        }

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AutoscalingDecision:
    accepted: bool
    reasons: tuple[str, ...]
    action: ScalingAction
    current_workers: int
    desired_workers: int
    placement_decision_digest: str
    observation_digest: str
    policy_digest: str
    task_id: str = BATCH_AUTOSCALE_TASK_ID
    accountability_id: str = BATCH_AUTOSCALE_ACCOUNTABILITY_ID
    schema_version: int = BATCH_AUTOSCALE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BatchingAutoscalingError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise BatchingAutoscalingError(
                "reasons must contain non-empty strings"
            )
        try:
            object.__setattr__(
                self,
                "action",
                ScalingAction(self.action),
            )
        except ValueError as exc:
            raise BatchingAutoscalingError(
                "invalid scaling action"
            ) from exc
        object.__setattr__(
            self,
            "current_workers",
            _nonnegative_int(
                self.current_workers,
                "current_workers",
            ),
        )
        object.__setattr__(
            self,
            "desired_workers",
            _positive_int(
                self.desired_workers,
                "desired_workers",
            ),
        )
        for field in (
            "placement_decision_digest",
            "observation_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.task_id != BATCH_AUTOSCALE_TASK_ID:
            raise BatchingAutoscalingError("task_id drift")
        if self.accountability_id != BATCH_AUTOSCALE_ACCOUNTABILITY_ID:
            raise BatchingAutoscalingError("accountability_id drift")
        if self.schema_version != BATCH_AUTOSCALE_SCHEMA_VERSION:
            raise BatchingAutoscalingError(
                "unsupported autoscaling decision schema"
            )

    @property
    def delta(self) -> int:
        return self.desired_workers - self.current_workers

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "action": self.action.value,
            "current_workers": self.current_workers,
            "desired_workers": self.desired_workers,
            "delta": self.delta,
            "placement_decision_digest": self.placement_decision_digest,
            "observation_digest": self.observation_digest,
            "policy_digest": self.policy_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-03:autoscaling",
    ) -> EvidenceRef:
        if not self.accepted:
            raise BatchingAutoscalingError(
                "rejected autoscaling decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="inference_autoscaling",
        )


def qualify_autoscaling(
    *,
    placement_decision: ModelPlacementDecision,
    observation: ServiceObjectiveObservation,
    policy: ServiceObjectivePolicy,
    observed_at: float,
) -> AutoscalingDecision:
    if not isinstance(placement_decision, ModelPlacementDecision):
        raise TypeError(
            "placement_decision must be ModelPlacementDecision"
        )
    if not isinstance(observation, ServiceObjectiveObservation):
        raise TypeError(
            "observation must be ServiceObjectiveObservation"
        )
    if not isinstance(policy, ServiceObjectivePolicy):
        raise TypeError("policy must be ServiceObjectivePolicy")
    now = _nonnegative(observed_at, "observed_at")
    reasons: list[str] = []
    if not placement_decision.accepted:
        reasons.append("placement-decision-rejected")
    if (
        observation.placement_decision_digest
        != placement_decision.decision_digest
    ):
        reasons.append("observation-placement-mismatch")
    if now < observation.observed_at:
        reasons.append("observation-not-yet-valid")
    if now - observation.observed_at > policy.observation_max_age_s:
        reasons.append("observation-stale")
    if observation.quality_score < policy.min_quality_score:
        reasons.append("quality-budget-breached")

    scaler = WorkerScaler(
        ScalingPolicy(
            target_queue_per_worker=policy.target_queue_per_worker,
            scale_out_queue_per_worker=(
                policy.scale_out_queue_per_worker
            ),
            scale_in_queue_per_worker=(
                policy.scale_in_queue_per_worker
            ),
            min_workers=policy.min_workers,
            max_workers=policy.max_workers,
            max_step=policy.max_scale_step,
        )
    )
    recommendation = scaler.recommend(
        healthy_workers=observation.healthy_workers,
        queued=observation.queued,
    )
    current = observation.healthy_workers
    desired = recommendation.desired_workers
    action = recommendation.action

    stressed = (
        observation.p99_latency_ms > policy.target_p99_latency_ms
        or observation.cancellation_rate > policy.max_cancellation_rate
        or observation.error_rate > policy.max_error_rate
    )
    if stressed:
        if current >= policy.max_workers:
            reasons.append("service-objective-breach-at-max-workers")
            desired = max(1, current)
            action = ScalingAction.HOLD
        else:
            desired = min(
                policy.max_workers,
                max(current + 1, current + policy.max_scale_step),
            )
            action = ScalingAction.SCALE_OUT
    elif action is ScalingAction.SCALE_IN:
        # Scale-in is only permitted on fully healthy service objectives.
        if (
            observation.p99_latency_ms
            > policy.target_p99_latency_ms
            or observation.cancellation_rate
            > policy.max_cancellation_rate
            or observation.error_rate > policy.max_error_rate
            or observation.quality_score < policy.min_quality_score
        ):
            reasons.append("scale-in-service-objective-unsafe")
            desired = max(1, current)
            action = ScalingAction.HOLD

    normalized = tuple(sorted(set(reasons)))
    return AutoscalingDecision(
        accepted=not normalized,
        reasons=normalized,
        action=action,
        current_workers=current,
        desired_workers=max(1, desired),
        placement_decision_digest=placement_decision.decision_digest,
        observation_digest=observation.observation_digest,
        policy_digest=policy.policy_digest,
    )


__all__ = [
    "BATCH_AUTOSCALE_ACCOUNTABILITY_ID",
    "BATCH_AUTOSCALE_SCHEMA_VERSION",
    "BATCH_AUTOSCALE_TASK_ID",
    "AutoscalingDecision",
    "BatchingAutoscalingError",
    "ContinuousBatchDecision",
    "ContinuousBatchItem",
    "ContinuousBatchPolicy",
    "DispatchDisposition",
    "ServiceObjectiveObservation",
    "ServiceObjectivePolicy",
    "plan_continuous_batch",
    "qualify_autoscaling",
]

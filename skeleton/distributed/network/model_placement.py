"""P1 topology-aware model placement and warming authority.

This module is a pure qualification plane. It composes existing worker
placement/capacity/topology primitives with DIST-01 remote-worker trust.

Warming is authorized only by an accepted remote-execution grant whose payload
is the exact model/runtime/tenant warming payload. Final placement is accepted
only when a deterministic candidate selection satisfies data-boundary,
liveness, capacity, topology, fresh warm-readiness, and live reservation
requirements. No model is loaded or scheduled by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.contracts.canonical import EvidenceRef
from skeleton.distributed.network.remote_execution import (
    RemoteExecutionGrantDecision,
    RemoteExecutionRequest,
    worker_identity_digest,
)
from skeleton.shells.worker_affinity import (
    AffinityMode,
    AffinityTerm,
    JobRequirements,
    WorkerPlacement,
)
from skeleton.shells.worker_capacity import (
    CapacityDemand,
    WorkerCapacityCatalog,
)
from skeleton.shells.worker_heartbeat import LivenessView, WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity, WorkerRegistration, WorkerRole
from skeleton.shells.worker_reservations import CapacityReservation
from skeleton.shells.worker_topology import SpreadConstraint, WorkerTopology


MODEL_PLACEMENT_SCHEMA_VERSION = 1
MODEL_PLACEMENT_TASK_ID = "P1-DIST-02"
MODEL_PLACEMENT_ACCOUNTABILITY_ID = "ACC-P1-DIST-02"
_MAX_ITEMS = 128
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ModelPlacementError(ValueError):
    """Model placement or warm evidence is malformed."""


class WarmReadiness(str, Enum):
    READY = "ready"
    WARMING = "warming"
    COLD = "cold"
    STALE = "stale"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelPlacementError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ModelPlacementError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise ModelPlacementError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ModelPlacementError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ModelPlacementError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelPlacementError(
            f"{field} must be a non-negative integer"
        )
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelPlacementError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ModelPlacementError(f"{field} must be finite numeric")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0:
        raise ModelPlacementError(f"{field} must be positive")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0:
        raise ModelPlacementError(f"{field} must be non-negative")
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
        raise ModelPlacementError(
            "model placement payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ModelPlacementError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not allow_empty and not result:
        raise ModelPlacementError(f"{field} must be non-empty")
    if len(result) > _MAX_ITEMS:
        raise ModelPlacementError(f"{field} exceeds item limit")
    return result


def _labels(
    values: Mapping[str, str] | Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    items = values.items() if isinstance(values, Mapping) else values
    normalized: dict[str, str] = {}
    for key, value in items:
        normalized[_token(key, "required_labels.key", maximum=64)] = _token(
            value,
            "required_labels.value",
            maximum=128,
        )
    if len(normalized) > _MAX_ITEMS:
        raise ModelPlacementError("required_labels exceeds item limit")
    return tuple(sorted(normalized.items()))


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise ModelPlacementError("evidence_refs must contain EvidenceRef")
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise ModelPlacementError(
                "evidence_refs must contain EvidenceRef"
            )
        _text(item.source, "evidence source")
        _sha256(item.digest, "evidence digest")
        _token(item.category, "evidence category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise ModelPlacementError("evidence_refs must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


def _reservation_digest(reservation: CapacityReservation) -> str:
    if not isinstance(reservation, CapacityReservation):
        raise TypeError("reservation must be CapacityReservation")
    return _canonical_digest(
        {
            "reservation_id": reservation.reservation_id,
            "worker": reservation.worker.to_dict(),
            "demand": {
                "inflight": reservation.demand.inflight,
                "weight": reservation.demand.weight,
            },
            "created_at": reservation.created_at,
            "expires_at": reservation.expires_at,
        }
    )


@dataclass(frozen=True, slots=True)
class ModelPlacementRequest:
    placement_id: str
    model_id: str
    model_version: str
    model_digest: str
    runtime_digest: str
    tenant_id: str
    data_class: str
    allowed_data_boundaries: tuple[str, ...]
    required_role: WorkerRole = WorkerRole.EXECUTOR
    required_features: tuple[str, ...] = ()
    required_labels: tuple[tuple[str, str], ...] = ()
    topology_label_key: str = "zone"
    min_topology_domains: int = 1
    max_topology_skew: int = 1
    demand_inflight: int = 1
    demand_weight: int = 1
    max_worker_inflight: int | None = None
    warmup_grant_max_age_s: float = 30.0
    schema_version: int = MODEL_PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "placement_id",
            "model_id",
            "model_version",
            "tenant_id",
            "data_class",
            "topology_label_key",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        for field in ("model_digest", "runtime_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "allowed_data_boundaries",
            _tokens(
                self.allowed_data_boundaries,
                "allowed_data_boundaries",
                allow_empty=False,
            ),
        )
        try:
            object.__setattr__(
                self,
                "required_role",
                WorkerRole(self.required_role),
            )
        except ValueError as exc:
            raise ModelPlacementError("invalid required_role") from exc
        object.__setattr__(
            self,
            "required_features",
            _tokens(self.required_features, "required_features"),
        )
        object.__setattr__(
            self,
            "required_labels",
            _labels(self.required_labels),
        )
        object.__setattr__(
            self,
            "min_topology_domains",
            _positive_int(
                self.min_topology_domains,
                "min_topology_domains",
            ),
        )
        skew = _nonnegative_int(self.max_topology_skew, "max_topology_skew")
        object.__setattr__(self, "max_topology_skew", skew)
        object.__setattr__(
            self,
            "demand_inflight",
            _positive_int(self.demand_inflight, "demand_inflight"),
        )
        object.__setattr__(
            self,
            "demand_weight",
            _positive_int(self.demand_weight, "demand_weight"),
        )
        if self.max_worker_inflight is not None:
            object.__setattr__(
                self,
                "max_worker_inflight",
                _nonnegative_int(
                    self.max_worker_inflight,
                    "max_worker_inflight",
                ),
            )
        object.__setattr__(
            self,
            "warmup_grant_max_age_s",
            _positive(
                self.warmup_grant_max_age_s,
                "warmup_grant_max_age_s",
            ),
        )
        if self.schema_version != MODEL_PLACEMENT_SCHEMA_VERSION:
            raise ModelPlacementError("unsupported request schema version")

    @property
    def demand(self) -> CapacityDemand:
        return CapacityDemand(
            inflight=self.demand_inflight,
            weight=self.demand_weight,
        )

    @property
    def warmup_payload_digest(self) -> str:
        return _canonical_digest(
            {
                "placement_id": self.placement_id,
                "model_id": self.model_id,
                "model_version": self.model_version,
                "model_digest": self.model_digest,
                "runtime_digest": self.runtime_digest,
                "tenant_id": self.tenant_id,
                "data_class": self.data_class,
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": MODEL_PLACEMENT_TASK_ID,
            "accountability_id": MODEL_PLACEMENT_ACCOUNTABILITY_ID,
            "placement_id": self.placement_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_digest": self.model_digest,
            "runtime_digest": self.runtime_digest,
            "tenant_id": self.tenant_id,
            "data_class": self.data_class,
            "allowed_data_boundaries": list(
                self.allowed_data_boundaries
            ),
            "required_role": self.required_role.value,
            "required_features": list(self.required_features),
            "required_labels": [list(item) for item in self.required_labels],
            "topology_label_key": self.topology_label_key,
            "min_topology_domains": self.min_topology_domains,
            "max_topology_skew": self.max_topology_skew,
            "demand_inflight": self.demand_inflight,
            "demand_weight": self.demand_weight,
            "max_worker_inflight": self.max_worker_inflight,
            "warmup_grant_max_age_s": self.warmup_grant_max_age_s,
            "warmup_payload_digest": self.warmup_payload_digest,
        }

    @property
    def request_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ModelWarmAuthorizationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    placement_request_digest: str
    remote_request_digest: str
    remote_grant_digest: str
    worker_identity_digest: str
    observed_at: float
    task_id: str = MODEL_PLACEMENT_TASK_ID
    accountability_id: str = MODEL_PLACEMENT_ACCOUNTABILITY_ID
    schema_version: int = MODEL_PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ModelPlacementError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ModelPlacementError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "placement_request_digest",
            "remote_request_digest",
            "remote_grant_digest",
            "worker_identity_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        if self.task_id != MODEL_PLACEMENT_TASK_ID:
            raise ModelPlacementError("task_id drift")
        if self.accountability_id != MODEL_PLACEMENT_ACCOUNTABILITY_ID:
            raise ModelPlacementError("accountability_id drift")
        if self.schema_version != MODEL_PLACEMENT_SCHEMA_VERSION:
            raise ModelPlacementError("unsupported authorization schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "placement_request_digest": self.placement_request_digest,
            "remote_request_digest": self.remote_request_digest,
            "remote_grant_digest": self.remote_grant_digest,
            "worker_identity_digest": self.worker_identity_digest,
            "observed_at": self.observed_at,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


def qualify_model_warmup(
    *,
    request: ModelPlacementRequest,
    remote_request: RemoteExecutionRequest,
    remote_grant: RemoteExecutionGrantDecision,
    worker: WorkerIdentity,
    observed_at: float,
) -> ModelWarmAuthorizationDecision:
    if not isinstance(request, ModelPlacementRequest):
        raise TypeError("request must be ModelPlacementRequest")
    if not isinstance(remote_request, RemoteExecutionRequest):
        raise TypeError("remote_request must be RemoteExecutionRequest")
    if not isinstance(remote_grant, RemoteExecutionGrantDecision):
        raise TypeError("remote_grant must be RemoteExecutionGrantDecision")
    if not isinstance(worker, WorkerIdentity):
        raise TypeError("worker must be WorkerIdentity")

    now = _nonnegative(observed_at, "observed_at")
    identity_digest = worker_identity_digest(worker)
    reasons: list[str] = []
    if not remote_grant.accepted:
        reasons.append("remote-grant-rejected")
    if remote_grant.request_digest != remote_request.request_digest:
        reasons.append("remote-grant-request-mismatch")
    if remote_grant.worker_identity_digest != identity_digest:
        reasons.append("remote-grant-worker-mismatch")
    if remote_request.payload_digest != request.warmup_payload_digest:
        reasons.append("warmup-payload-digest-mismatch")
    if remote_request.tenant_id != request.tenant_id:
        reasons.append("warmup-tenant-mismatch")
    if remote_request.required_role is not request.required_role:
        reasons.append("warmup-worker-role-mismatch")
    if not set(request.required_features) <= set(
        remote_request.required_features
    ):
        reasons.append("warmup-worker-features-mismatch")
    if not set(request.required_labels) <= set(
        remote_request.required_labels
    ):
        reasons.append("warmup-worker-labels-mismatch")
    if now < remote_grant.observed_at:
        reasons.append("remote-grant-not-yet-valid")
    if now - remote_grant.observed_at > request.warmup_grant_max_age_s:
        reasons.append("remote-grant-stale")

    boundary = worker.labels.get("data_boundary")
    if boundary not in set(request.allowed_data_boundaries):
        reasons.append("worker-data-boundary-mismatch")
    if worker.role is not request.required_role:
        reasons.append("worker-role-mismatch")
    if not set(request.required_features) <= set(worker.features):
        reasons.append("worker-feature-mismatch")
    if not worker.matches_labels(dict(request.required_labels)):
        reasons.append("worker-label-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return ModelWarmAuthorizationDecision(
        accepted=not normalized,
        reasons=normalized,
        placement_request_digest=request.request_digest,
        remote_request_digest=remote_request.request_digest,
        remote_grant_digest=remote_grant.decision_digest,
        worker_identity_digest=identity_digest,
        observed_at=now,
    )


@dataclass(frozen=True, slots=True)
class ModelWarmObservation:
    placement_request_digest: str
    authorization_digest: str
    worker_id: str
    generation: int
    worker_identity_digest: str
    model_digest: str
    runtime_digest: str
    readiness: WarmReadiness
    observed_at: float
    expires_at: float
    evidence_refs: tuple[EvidenceRef, ...]
    verifier_id: str
    verifier_digest: str
    independent: bool = True

    def __post_init__(self) -> None:
        for field in (
            "placement_request_digest",
            "authorization_digest",
            "worker_identity_digest",
            "model_digest",
            "runtime_digest",
            "verifier_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
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
        try:
            object.__setattr__(
                self,
                "readiness",
                WarmReadiness(self.readiness),
            )
        except ValueError as exc:
            raise ModelPlacementError("invalid warm readiness") from exc
        observed = _nonnegative(self.observed_at, "observed_at")
        expires = _positive(self.expires_at, "expires_at")
        if expires <= observed:
            raise ModelPlacementError(
                "warm observation expiry must exceed observed_at"
            )
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)
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
        if self.independent is not True:
            raise ModelPlacementError(
                "warm readiness verifier must be independent"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "placement_request_digest": self.placement_request_digest,
            "authorization_digest": self.authorization_digest,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "worker_identity_digest": self.worker_identity_digest,
            "model_digest": self.model_digest,
            "runtime_digest": self.runtime_digest,
            "readiness": self.readiness.value,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
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
class ModelPlacementSelection:
    request_digest: str
    selected_worker_id: str | None
    selected_worker_generation: int | None
    selected_worker_identity_digest: str | None
    warm_authorization_digest: str | None
    warm_observation_digest: str | None
    candidate_worker_ids: tuple[str, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    topology_digest: str
    capacity_digest: str
    task_id: str = MODEL_PLACEMENT_TASK_ID
    accountability_id: str = MODEL_PLACEMENT_ACCOUNTABILITY_ID
    schema_version: int = MODEL_PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_digest",
            _sha256(self.request_digest, "request_digest"),
        )
        optional_digests = (
            "selected_worker_identity_digest",
            "warm_authorization_digest",
            "warm_observation_digest",
        )
        for field in optional_digests:
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha256(value, field))
        for field in ("topology_digest", "capacity_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.selected_worker_id is not None:
            object.__setattr__(
                self,
                "selected_worker_id",
                _token(
                    self.selected_worker_id,
                    "selected_worker_id",
                    maximum=128,
                ),
            )
        if self.selected_worker_generation is not None:
            object.__setattr__(
                self,
                "selected_worker_generation",
                _positive_int(
                    self.selected_worker_generation,
                    "selected_worker_generation",
                ),
            )
        object.__setattr__(
            self,
            "candidate_worker_ids",
            _tokens(self.candidate_worker_ids, "candidate_worker_ids"),
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
        selected_evidence = (
            self.selected_worker_id,
            self.selected_worker_generation,
            self.selected_worker_identity_digest,
            self.warm_authorization_digest,
            self.warm_observation_digest,
        )
        if self.selected_worker_id is None:
            if any(value is not None for value in selected_evidence[1:]):
                raise ModelPlacementError(
                    "unselected placement cannot carry selected evidence"
                )
        elif any(value is None for value in selected_evidence):
            raise ModelPlacementError(
                "selected placement requires complete selected evidence"
            )
        if self.task_id != MODEL_PLACEMENT_TASK_ID:
            raise ModelPlacementError("task_id drift")
        if self.accountability_id != MODEL_PLACEMENT_ACCOUNTABILITY_ID:
            raise ModelPlacementError("accountability_id drift")
        if self.schema_version != MODEL_PLACEMENT_SCHEMA_VERSION:
            raise ModelPlacementError("unsupported selection schema")

    @property
    def selected(self) -> bool:
        return self.selected_worker_id is not None

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "request_digest": self.request_digest,
            "selected_worker_id": self.selected_worker_id,
            "selected_worker_generation": self.selected_worker_generation,
            "selected_worker_identity_digest": (
                self.selected_worker_identity_digest
            ),
            "warm_authorization_digest": self.warm_authorization_digest,
            "warm_observation_digest": self.warm_observation_digest,
            "candidate_worker_ids": list(self.candidate_worker_ids),
            "rejected": [
                [worker_id, list(reasons)]
                for worker_id, reasons in self.rejected
            ],
            "topology_digest": self.topology_digest,
            "capacity_digest": self.capacity_digest,
        }

    @property
    def selection_digest(self) -> str:
        return _canonical_digest(self.payload())


def select_model_placement(
    *,
    request: ModelPlacementRequest,
    registrations: Sequence[WorkerRegistration],
    liveness: Mapping[str, LivenessView],
    capacities: WorkerCapacityCatalog,
    active_weight: Mapping[str, int],
    active_assignments: Mapping[str, int],
    warm_authorizations: Mapping[str, ModelWarmAuthorizationDecision],
    warm_observations: Mapping[str, ModelWarmObservation],
    observed_at: float,
) -> ModelPlacementSelection:
    if not isinstance(request, ModelPlacementRequest):
        raise TypeError("request must be ModelPlacementRequest")
    if not isinstance(capacities, WorkerCapacityCatalog):
        raise TypeError("capacities must be WorkerCapacityCatalog")
    now = _nonnegative(observed_at, "observed_at")

    rejected: dict[str, list[str]] = {}
    prelim: list[WorkerRegistration] = []
    for registration in registrations:
        if not isinstance(registration, WorkerRegistration):
            raise TypeError(
                "registrations must contain WorkerRegistration"
            )
        worker = registration.identity
        reasons: list[str] = []
        if not registration.enabled:
            reasons.append("registration-disabled")
        view = liveness.get(worker.worker_id)
        if view is None:
            reasons.append("liveness-missing")
        else:
            if view.generation != worker.generation:
                reasons.append("liveness-generation-mismatch")
            if view.liveness is not WorkerLiveness.HEALTHY:
                reasons.append(f"liveness-{view.liveness.value}")

        boundary = worker.labels.get("data_boundary")
        if boundary not in set(request.allowed_data_boundaries):
            reasons.append("data-boundary-mismatch")
        if worker.role is not request.required_role:
            reasons.append("role-mismatch")
        if not set(request.required_features) <= set(worker.features):
            reasons.append("feature-mismatch")
        if not worker.matches_labels(dict(request.required_labels)):
            reasons.append("label-mismatch")

        authorization = warm_authorizations.get(worker.worker_id)
        observation = warm_observations.get(worker.worker_id)
        if authorization is None:
            reasons.append("warm-authorization-missing")
        else:
            if not authorization.accepted:
                reasons.append("warm-authorization-rejected")
            if authorization.placement_request_digest != request.request_digest:
                reasons.append("warm-authorization-request-mismatch")
            if (
                authorization.worker_identity_digest
                != worker_identity_digest(worker)
            ):
                reasons.append("warm-authorization-worker-mismatch")
        if observation is None:
            reasons.append("warm-observation-missing")
        else:
            if observation.placement_request_digest != request.request_digest:
                reasons.append("warm-observation-request-mismatch")
            if observation.worker_id != worker.worker_id:
                reasons.append("warm-observation-worker-id-mismatch")
            if observation.generation != worker.generation:
                reasons.append("warm-observation-generation-mismatch")
            if (
                observation.worker_identity_digest
                != worker_identity_digest(worker)
            ):
                reasons.append("warm-observation-worker-mismatch")
            if observation.model_digest != request.model_digest:
                reasons.append("warm-observation-model-mismatch")
            if observation.runtime_digest != request.runtime_digest:
                reasons.append("warm-observation-runtime-mismatch")
            if authorization is not None and (
                observation.authorization_digest
                != authorization.decision_digest
            ):
                reasons.append("warm-observation-authorization-mismatch")
            if observation.readiness is not WarmReadiness.READY:
                reasons.append(
                    f"warm-readiness-{observation.readiness.value}"
                )
            if now < observation.observed_at:
                reasons.append("warm-observation-not-yet-valid")
            if now >= observation.expires_at:
                reasons.append("warm-observation-expired")

        if reasons:
            rejected[worker.worker_id] = reasons
            continue
        prelim.append(registration)

    fleet = capacities.fleet(
        prelim,
        liveness,
        active_weight=active_weight,
    )
    capacity_views = {view.worker_id: view for view in fleet.workers}
    capacity_allowed: list[WorkerRegistration] = []
    for registration in prelim:
        view = capacity_views[registration.identity.worker_id]
        if not view.can_fit(request.demand):
            rejected.setdefault(
                registration.identity.worker_id,
                [],
            ).append("capacity-insufficient")
            continue
        capacity_allowed.append(registration)

    topology = WorkerTopology().filter(
        capacity_allowed,
        active_assignments=active_assignments,
        constraint=SpreadConstraint(
            label_key=request.topology_label_key,
            max_skew=request.max_topology_skew,
            min_domains=request.min_topology_domains,
        ),
    )
    for worker_id, reason in topology.rejected.items():
        rejected.setdefault(worker_id, []).append(
            reason.replace(" ", "-")
        )

    affinity = tuple(
        AffinityTerm(
            key=key,
            value=value,
            mode=AffinityMode.REQUIRED,
        )
        for key, value in request.required_labels
    )
    placement = WorkerPlacement().evaluate(
        topology.allowed,
        liveness,
        JobRequirements(
            required_role=request.required_role,
            required_features=frozenset(request.required_features),
            affinity=affinity,
            max_inflight=request.max_worker_inflight,
            allow_late_workers=False,
        ),
    )
    for worker_id, reasons in placement.rejected.items():
        rejected.setdefault(worker_id, []).extend(reasons)

    selected = (
        None
        if placement.selected is None
        else placement.selected.registration
    )
    selected_authorization = None
    selected_observation = None
    if selected is not None:
        worker = selected.identity
        selected_authorization = warm_authorizations[worker.worker_id]
        selected_observation = warm_observations[worker.worker_id]

    topology_digest = _canonical_digest(
        {
            "domain_counts": dict(sorted(topology.domain_counts.items())),
            "allowed": [
                registration.identity.key
                for registration in sorted(
                    topology.allowed,
                    key=lambda item: item.identity.key,
                )
            ],
            "rejected": dict(sorted(topology.rejected.items())),
        }
    )
    capacity_digest = _canonical_digest(fleet.to_dict())
    normalized_rejected = tuple(
        (
            worker_id,
            tuple(sorted(set(worker_reasons))),
        )
        for worker_id, worker_reasons in sorted(rejected.items())
    )
    return ModelPlacementSelection(
        request_digest=request.request_digest,
        selected_worker_id=(
            None if selected is None else selected.identity.worker_id
        ),
        selected_worker_generation=(
            None if selected is None else selected.identity.generation
        ),
        selected_worker_identity_digest=(
            None
            if selected is None
            else worker_identity_digest(selected.identity)
        ),
        warm_authorization_digest=(
            None
            if selected_authorization is None
            else selected_authorization.decision_digest
        ),
        warm_observation_digest=(
            None
            if selected_observation is None
            else selected_observation.observation_digest
        ),
        candidate_worker_ids=tuple(
            candidate.worker_id for candidate in placement.candidates
        ),
        rejected=normalized_rejected,
        topology_digest=topology_digest,
        capacity_digest=capacity_digest,
    )


@dataclass(frozen=True, slots=True)
class ModelPlacementDecision:
    accepted: bool
    reasons: tuple[str, ...]
    request_digest: str
    selected_worker_id: str | None
    selected_worker_generation: int | None
    selected_worker_identity_digest: str | None
    warm_authorization_digest: str | None
    warm_observation_digest: str | None
    reservation_digest: str | None
    candidate_worker_ids: tuple[str, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    topology_digest: str
    capacity_digest: str
    task_id: str = MODEL_PLACEMENT_TASK_ID
    accountability_id: str = MODEL_PLACEMENT_ACCOUNTABILITY_ID
    schema_version: int = MODEL_PLACEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ModelPlacementError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ModelPlacementError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "request_digest",
            _sha256(self.request_digest, "request_digest"),
        )
        optional_digests = (
            "selected_worker_identity_digest",
            "warm_authorization_digest",
            "warm_observation_digest",
            "reservation_digest",
        )
        for field in optional_digests:
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(
                    self,
                    field,
                    _sha256(value, field),
                )
        for field in ("topology_digest", "capacity_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.selected_worker_id is not None:
            object.__setattr__(
                self,
                "selected_worker_id",
                _token(
                    self.selected_worker_id,
                    "selected_worker_id",
                    maximum=128,
                ),
            )
        if self.selected_worker_generation is not None:
            object.__setattr__(
                self,
                "selected_worker_generation",
                _positive_int(
                    self.selected_worker_generation,
                    "selected_worker_generation",
                ),
            )
        object.__setattr__(
            self,
            "candidate_worker_ids",
            _tokens(self.candidate_worker_ids, "candidate_worker_ids"),
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
        if self.accepted:
            required = (
                self.selected_worker_id,
                self.selected_worker_generation,
                self.selected_worker_identity_digest,
                self.warm_authorization_digest,
                self.warm_observation_digest,
                self.reservation_digest,
            )
            if any(value is None for value in required):
                raise ModelPlacementError(
                    "accepted placement requires complete selected evidence"
                )
        if self.task_id != MODEL_PLACEMENT_TASK_ID:
            raise ModelPlacementError("task_id drift")
        if self.accountability_id != MODEL_PLACEMENT_ACCOUNTABILITY_ID:
            raise ModelPlacementError("accountability_id drift")
        if self.schema_version != MODEL_PLACEMENT_SCHEMA_VERSION:
            raise ModelPlacementError("unsupported decision schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "request_digest": self.request_digest,
            "selected_worker_id": self.selected_worker_id,
            "selected_worker_generation": self.selected_worker_generation,
            "selected_worker_identity_digest": (
                self.selected_worker_identity_digest
            ),
            "warm_authorization_digest": self.warm_authorization_digest,
            "warm_observation_digest": self.warm_observation_digest,
            "reservation_digest": self.reservation_digest,
            "candidate_worker_ids": list(self.candidate_worker_ids),
            "rejected": [
                [worker_id, list(reasons)]
                for worker_id, reasons in self.rejected
            ],
            "topology_digest": self.topology_digest,
            "capacity_digest": self.capacity_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-02:model-placement",
    ) -> EvidenceRef:
        if not self.accepted:
            raise ModelPlacementError(
                "rejected model placement cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="model_placement",
        )


def qualify_model_placement(
    *,
    request: ModelPlacementRequest,
    registrations: Sequence[WorkerRegistration],
    liveness: Mapping[str, LivenessView],
    capacities: WorkerCapacityCatalog,
    active_weight: Mapping[str, int],
    active_assignments: Mapping[str, int],
    warm_authorizations: Mapping[str, ModelWarmAuthorizationDecision],
    warm_observations: Mapping[str, ModelWarmObservation],
    reservation: CapacityReservation,
    observed_at: float,
) -> ModelPlacementDecision:
    if not isinstance(request, ModelPlacementRequest):
        raise TypeError("request must be ModelPlacementRequest")
    if not isinstance(capacities, WorkerCapacityCatalog):
        raise TypeError("capacities must be WorkerCapacityCatalog")
    if not isinstance(reservation, CapacityReservation):
        raise TypeError("reservation must be CapacityReservation")
    now = _nonnegative(observed_at, "observed_at")
    registration_tuple = tuple(registrations)

    selection = select_model_placement(
        request=request,
        registrations=registration_tuple,
        liveness=liveness,
        capacities=capacities,
        active_weight=active_weight,
        active_assignments=active_assignments,
        warm_authorizations=warm_authorizations,
        warm_observations=warm_observations,
        observed_at=now,
    )

    selected: WorkerRegistration | None = None
    if selection.selected:
        for registration in registration_tuple:
            if (
                registration.identity.worker_id
                == selection.selected_worker_id
                and registration.identity.generation
                == selection.selected_worker_generation
            ):
                selected = registration
                break

    reasons: list[str] = []
    if selected is None:
        reasons.append("no-qualified-placement")

    selected_authorization = None
    selected_observation = None
    reservation_digest = None
    if selected is not None:
        worker = selected.identity
        selected_authorization = warm_authorizations[worker.worker_id]
        selected_observation = warm_observations[worker.worker_id]
        if reservation.worker != worker:
            reasons.append("reservation-worker-mismatch")
        if (
            reservation.demand.inflight < request.demand_inflight
            or reservation.demand.weight < request.demand_weight
        ):
            reasons.append("reservation-demand-insufficient")
        if now < reservation.created_at:
            reasons.append("reservation-not-yet-valid")
        if now >= reservation.expires_at:
            reasons.append("reservation-expired")
        reservation_digest = _reservation_digest(reservation)

    normalized = tuple(sorted(set(reasons)))
    return ModelPlacementDecision(
        accepted=not normalized,
        reasons=normalized,
        request_digest=request.request_digest,
        selected_worker_id=(
            None if selected is None else selected.identity.worker_id
        ),
        selected_worker_generation=(
            None if selected is None else selected.identity.generation
        ),
        selected_worker_identity_digest=(
            None
            if selected is None
            else worker_identity_digest(selected.identity)
        ),
        warm_authorization_digest=(
            None
            if selected_authorization is None
            else selected_authorization.decision_digest
        ),
        warm_observation_digest=(
            None
            if selected_observation is None
            else selected_observation.observation_digest
        ),
        reservation_digest=reservation_digest,
        candidate_worker_ids=selection.candidate_worker_ids,
        rejected=selection.rejected,
        topology_digest=selection.topology_digest,
        capacity_digest=selection.capacity_digest,
    )


__all__ = [
    "MODEL_PLACEMENT_ACCOUNTABILITY_ID",
    "MODEL_PLACEMENT_SCHEMA_VERSION",
    "MODEL_PLACEMENT_TASK_ID",
    "ModelPlacementDecision",
    "ModelPlacementError",
    "ModelPlacementRequest",
    "ModelPlacementSelection",
    "ModelWarmAuthorizationDecision",
    "ModelWarmObservation",
    "WarmReadiness",
    "qualify_model_placement",
    "select_model_placement",
    "qualify_model_warmup",
]

"""P1 remote execution, worker trust, lease and fencing authority.

This module is a non-transport qualification plane. It composes the existing
worker identity, heartbeat, lease, and protocol primitives into one fail-closed
remote-execution contract. It never opens sockets or executes work itself.

Authoritative completion requires:
- the exact current worker generation and enabled registration;
- a fresh HEALTHY heartbeat;
- a fresh independent worker attestation bound to exact identity;
- a live lease owned by that worker;
- a monotonic fence chain bound to request + lease + worker;
- an accepted grant for the exact request;
- a protocol-guarded COMPLETE message;
- result budgets within the request envelope; and
- the same fence still current at commit time.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.shells.leases import Lease
from skeleton.shells.worker_heartbeat import LivenessView, WorkerLiveness
from skeleton.shells.worker_identity import (
    WorkerIdentity,
    WorkerRegistration,
    WorkerRole,
)
from skeleton.shells.worker_protocol import (
    ProtocolCursor,
    WorkerMessage,
    WorkerMessageKind,
)


REMOTE_EXECUTION_SCHEMA_VERSION = 1
REMOTE_EXECUTION_TASK_ID = "P1-DIST-01"
REMOTE_EXECUTION_ACCOUNTABILITY_ID = "ACC-P1-DIST-01"
_MAX_ITEMS = 128
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RemoteExecutionError(ValueError):
    """Remote-execution evidence is malformed or unsafe."""


class RemoteResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RemoteExecutionError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise RemoteExecutionError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise RemoteExecutionError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RemoteExecutionError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RemoteExecutionError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RemoteExecutionError(
            f"{field} must be a non-negative integer"
        )
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RemoteExecutionError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RemoteExecutionError(f"{field} must be finite numeric")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0.0:
        raise RemoteExecutionError(f"{field} must be positive")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0:
        raise RemoteExecutionError(f"{field} must be non-negative")
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
        raise RemoteExecutionError(
            "remote execution payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RemoteExecutionError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not allow_empty and not result:
        raise RemoteExecutionError(f"{field} must be non-empty")
    if len(result) > _MAX_ITEMS:
        raise RemoteExecutionError(f"{field} exceeds item limit")
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
        raise RemoteExecutionError("required_labels exceeds item limit")
    return tuple(sorted(normalized.items()))


def _evidence(
    values: Iterable[EvidenceRef],
    *,
    allow_empty: bool = False,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise RemoteExecutionError("evidence_refs must contain EvidenceRef")
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise RemoteExecutionError(
                "evidence_refs must contain EvidenceRef"
            )
        _text(item.source, "evidence source")
        _sha256(item.digest, "evidence digest")
        _token(item.category, "evidence category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key and not allow_empty:
        raise RemoteExecutionError("evidence_refs must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


def worker_identity_digest(identity: WorkerIdentity) -> str:
    if not isinstance(identity, WorkerIdentity):
        raise TypeError("identity must be WorkerIdentity")
    return _canonical_digest(identity.to_dict())


def lease_digest(lease: Lease) -> str:
    if not isinstance(lease, Lease):
        raise TypeError("lease must be Lease")
    return _canonical_digest(
        {
            "lease_id": lease.lease_id,
            "key": lease.key,
            "owner": lease.owner,
            "acquired_at": lease.acquired_at,
            "expires_at": lease.expires_at,
        }
    )


@dataclass(frozen=True, slots=True)
class RemoteExecutionRequest:
    operation_id: str
    execution_id: str
    tenant_id: str
    request_id: str
    coordinator_id: str
    action_digest: str
    authority_digest: str
    payload_digest: str
    required_role: WorkerRole
    required_features: tuple[str, ...] = ()
    required_labels: tuple[tuple[str, str], ...] = ()
    protocol_version: int = 1
    max_tokens: int = 1
    max_cost_units: float = 0.001
    max_wall_time_s: float = 0.001
    schema_version: int = REMOTE_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "operation_id",
            "execution_id",
            "tenant_id",
            "request_id",
            "coordinator_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        for field in (
            "action_digest",
            "authority_digest",
            "payload_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        try:
            object.__setattr__(
                self,
                "required_role",
                WorkerRole(self.required_role),
            )
        except ValueError as exc:
            raise RemoteExecutionError("invalid required_role") from exc
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
            "protocol_version",
            _positive_int(self.protocol_version, "protocol_version"),
        )
        object.__setattr__(
            self,
            "max_tokens",
            _positive_int(self.max_tokens, "max_tokens"),
        )
        object.__setattr__(
            self,
            "max_cost_units",
            _positive(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _positive(self.max_wall_time_s, "max_wall_time_s"),
        )
        if self.schema_version != REMOTE_EXECUTION_SCHEMA_VERSION:
            raise RemoteExecutionError("unsupported request schema version")

    @property
    def lease_key(self) -> str:
        return f"remote:{self.operation_id}:{self.execution_id}"

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": REMOTE_EXECUTION_TASK_ID,
            "accountability_id": REMOTE_EXECUTION_ACCOUNTABILITY_ID,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "request_id": self.request_id,
            "coordinator_id": self.coordinator_id,
            "action_digest": self.action_digest,
            "authority_digest": self.authority_digest,
            "payload_digest": self.payload_digest,
            "required_role": self.required_role.value,
            "required_features": list(self.required_features),
            "required_labels": [list(item) for item in self.required_labels],
            "protocol_version": self.protocol_version,
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
            "lease_key": self.lease_key,
        }

    @property
    def request_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class WorkerAttestation:
    worker_id: str
    generation: int
    identity_digest: str
    runtime_digest: str
    image_digest: str
    policy_digest: str
    verifier_id: str
    verifier_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    observed_at: float
    expires_at: float
    independent: bool = True
    schema_version: int = REMOTE_EXECUTION_SCHEMA_VERSION

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
        for field in (
            "identity_digest",
            "runtime_digest",
            "image_digest",
            "policy_digest",
            "verifier_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "verifier_id",
            _token(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        observed = _nonnegative(self.observed_at, "observed_at")
        expires = _positive(self.expires_at, "expires_at")
        if expires <= observed:
            raise RemoteExecutionError(
                "attestation expires_at must exceed observed_at"
            )
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)
        if self.independent is not True:
            raise RemoteExecutionError(
                "worker attestation must be independent"
            )
        if self.schema_version != REMOTE_EXECUTION_SCHEMA_VERSION:
            raise RemoteExecutionError(
                "unsupported attestation schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": REMOTE_EXECUTION_TASK_ID,
            "accountability_id": REMOTE_EXECUTION_ACCOUNTABILITY_ID,
            "worker_id": self.worker_id,
            "generation": self.generation,
            "identity_digest": self.identity_digest,
            "runtime_digest": self.runtime_digest,
            "image_digest": self.image_digest,
            "policy_digest": self.policy_digest,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "independent": self.independent,
        }

    @property
    def attestation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class RemoteExecutionFence:
    request_digest: str
    worker_identity_digest: str
    lease_digest: str
    epoch: int
    previous_fence_digest: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "request_digest",
            "worker_identity_digest",
            "lease_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "epoch",
            _positive_int(self.epoch, "epoch"),
        )
        if self.previous_fence_digest is not None:
            object.__setattr__(
                self,
                "previous_fence_digest",
                _sha256(
                    self.previous_fence_digest,
                    "previous_fence_digest",
                ),
            )
        if self.epoch == 1 and self.previous_fence_digest is not None:
            raise RemoteExecutionError(
                "root fence must not have predecessor"
            )
        if self.epoch > 1 and self.previous_fence_digest is None:
            raise RemoteExecutionError(
                "non-root fence must bind predecessor"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "request_digest": self.request_digest,
            "worker_identity_digest": self.worker_identity_digest,
            "lease_digest": self.lease_digest,
            "epoch": self.epoch,
            "previous_fence_digest": self.previous_fence_digest,
        }

    @property
    def fence_digest(self) -> str:
        return _canonical_digest(self.payload())


def issue_remote_execution_fence(
    *,
    request: RemoteExecutionRequest,
    worker: WorkerIdentity,
    lease: Lease,
    previous: RemoteExecutionFence | None = None,
) -> RemoteExecutionFence:
    if not isinstance(request, RemoteExecutionRequest):
        raise TypeError("request must be RemoteExecutionRequest")
    if not isinstance(worker, WorkerIdentity):
        raise TypeError("worker must be WorkerIdentity")
    if not isinstance(lease, Lease):
        raise TypeError("lease must be Lease")
    if lease.key != request.lease_key:
        raise RemoteExecutionError("lease key does not bind request")
    if lease.owner != worker.key:
        raise RemoteExecutionError("lease owner does not bind worker")

    identity_digest = worker_identity_digest(worker)
    current_lease_digest = lease_digest(lease)
    if previous is None:
        return RemoteExecutionFence(
            request_digest=request.request_digest,
            worker_identity_digest=identity_digest,
            lease_digest=current_lease_digest,
            epoch=1,
        )
    if previous.request_digest != request.request_digest:
        raise RemoteExecutionError("fence request chain mismatch")
    return RemoteExecutionFence(
        request_digest=request.request_digest,
        worker_identity_digest=identity_digest,
        lease_digest=current_lease_digest,
        epoch=previous.epoch + 1,
        previous_fence_digest=previous.fence_digest,
    )


@dataclass(frozen=True, slots=True)
class RemoteExecutionGrantDecision:
    accepted: bool
    reasons: tuple[str, ...]
    request_digest: str
    worker_identity_digest: str
    registration_id: str
    heartbeat_sequence: int
    attestation_digest: str
    lease_digest: str
    fence_digest: str
    fence_epoch: int
    observed_at: float
    task_id: str = REMOTE_EXECUTION_TASK_ID
    accountability_id: str = REMOTE_EXECUTION_ACCOUNTABILITY_ID
    schema_version: int = REMOTE_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise RemoteExecutionError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise RemoteExecutionError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "request_digest",
            "worker_identity_digest",
            "attestation_digest",
            "lease_digest",
            "fence_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "registration_id",
            _token(self.registration_id, "registration_id"),
        )
        object.__setattr__(
            self,
            "heartbeat_sequence",
            _positive_int(
                self.heartbeat_sequence,
                "heartbeat_sequence",
            ),
        )
        object.__setattr__(
            self,
            "fence_epoch",
            _positive_int(self.fence_epoch, "fence_epoch"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        if self.task_id != REMOTE_EXECUTION_TASK_ID:
            raise RemoteExecutionError("task_id drift")
        if self.accountability_id != REMOTE_EXECUTION_ACCOUNTABILITY_ID:
            raise RemoteExecutionError("accountability_id drift")
        if self.schema_version != REMOTE_EXECUTION_SCHEMA_VERSION:
            raise RemoteExecutionError("unsupported grant schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "request_digest": self.request_digest,
            "worker_identity_digest": self.worker_identity_digest,
            "registration_id": self.registration_id,
            "heartbeat_sequence": self.heartbeat_sequence,
            "attestation_digest": self.attestation_digest,
            "lease_digest": self.lease_digest,
            "fence_digest": self.fence_digest,
            "fence_epoch": self.fence_epoch,
            "observed_at": self.observed_at,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


def qualify_remote_execution(
    *,
    request: RemoteExecutionRequest,
    worker: WorkerIdentity,
    registration: WorkerRegistration,
    liveness: LivenessView,
    attestation: WorkerAttestation,
    lease: Lease,
    fence: RemoteExecutionFence,
    observed_at: float,
) -> RemoteExecutionGrantDecision:
    if not isinstance(request, RemoteExecutionRequest):
        raise TypeError("request must be RemoteExecutionRequest")
    if not isinstance(worker, WorkerIdentity):
        raise TypeError("worker must be WorkerIdentity")
    if not isinstance(registration, WorkerRegistration):
        raise TypeError("registration must be WorkerRegistration")
    if not isinstance(liveness, LivenessView):
        raise TypeError("liveness must be LivenessView")
    if not isinstance(attestation, WorkerAttestation):
        raise TypeError("attestation must be WorkerAttestation")
    if not isinstance(lease, Lease):
        raise TypeError("lease must be Lease")
    if not isinstance(fence, RemoteExecutionFence):
        raise TypeError("fence must be RemoteExecutionFence")

    now = _nonnegative(observed_at, "observed_at")
    identity_digest = worker_identity_digest(worker)
    current_lease_digest = lease_digest(lease)
    reasons: list[str] = []

    if registration.identity != worker:
        reasons.append("worker-registration-identity-mismatch")
    if not registration.enabled:
        reasons.append("worker-registration-disabled")
    if registration.identity.generation != worker.generation:
        reasons.append("worker-generation-stale")

    if worker.role is not request.required_role:
        reasons.append("worker-role-mismatch")
    if not set(request.required_features) <= set(worker.features):
        reasons.append("worker-feature-mismatch")
    required_labels = dict(request.required_labels)
    if not worker.matches_labels(required_labels):
        reasons.append("worker-label-mismatch")
    if worker.protocol_version != request.protocol_version:
        reasons.append("worker-protocol-version-mismatch")

    if liveness.worker_id != worker.worker_id:
        reasons.append("heartbeat-worker-id-mismatch")
    if liveness.generation != worker.generation:
        reasons.append("heartbeat-generation-mismatch")
    if liveness.liveness is not WorkerLiveness.HEALTHY:
        reasons.append(f"worker-liveness-{liveness.liveness.value}")
    if liveness.sequence is None:
        reasons.append("heartbeat-sequence-missing")

    if attestation.worker_id != worker.worker_id:
        reasons.append("attestation-worker-id-mismatch")
    if attestation.generation != worker.generation:
        reasons.append("attestation-generation-mismatch")
    if attestation.identity_digest != identity_digest:
        reasons.append("attestation-identity-digest-mismatch")
    if now < attestation.observed_at:
        reasons.append("attestation-not-yet-valid")
    if now >= attestation.expires_at:
        reasons.append("attestation-expired")

    if lease.key != request.lease_key:
        reasons.append("lease-key-mismatch")
    if lease.owner != worker.key:
        reasons.append("lease-owner-mismatch")
    if now < lease.acquired_at:
        reasons.append("lease-not-yet-valid")
    if now >= lease.expires_at:
        reasons.append("lease-expired")

    if fence.request_digest != request.request_digest:
        reasons.append("fence-request-mismatch")
    if fence.worker_identity_digest != identity_digest:
        reasons.append("fence-worker-mismatch")
    if fence.lease_digest != current_lease_digest:
        reasons.append("fence-lease-mismatch")

    normalized = tuple(sorted(set(reasons)))
    heartbeat_sequence = 1 if liveness.sequence is None else liveness.sequence
    return RemoteExecutionGrantDecision(
        accepted=not normalized,
        reasons=normalized,
        request_digest=request.request_digest,
        worker_identity_digest=identity_digest,
        registration_id=registration.registration_id,
        heartbeat_sequence=heartbeat_sequence,
        attestation_digest=attestation.attestation_digest,
        lease_digest=current_lease_digest,
        fence_digest=fence.fence_digest,
        fence_epoch=fence.epoch,
        observed_at=now,
    )


@dataclass(frozen=True, slots=True)
class RemoteExecutionResult:
    request_digest: str
    grant_digest: str
    worker_identity_digest: str
    fence_digest: str
    output_digest: str
    status: RemoteResultStatus
    tokens_used: int
    cost_units: float
    wall_time_s: float
    started_at: float
    completed_at: float

    def __post_init__(self) -> None:
        for field in (
            "request_digest",
            "grant_digest",
            "worker_identity_digest",
            "fence_digest",
            "output_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        try:
            object.__setattr__(
                self,
                "status",
                RemoteResultStatus(self.status),
            )
        except ValueError as exc:
            raise RemoteExecutionError("invalid result status") from exc
        object.__setattr__(
            self,
            "tokens_used",
            _nonnegative_int(self.tokens_used, "tokens_used"),
        )
        object.__setattr__(
            self,
            "cost_units",
            _nonnegative(self.cost_units, "cost_units"),
        )
        object.__setattr__(
            self,
            "wall_time_s",
            _nonnegative(self.wall_time_s, "wall_time_s"),
        )
        started = _nonnegative(self.started_at, "started_at")
        completed = _nonnegative(self.completed_at, "completed_at")
        if completed < started:
            raise RemoteExecutionError(
                "completed_at must not precede started_at"
            )
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)

    def payload(self) -> dict[str, Any]:
        return {
            "request_digest": self.request_digest,
            "grant_digest": self.grant_digest,
            "worker_identity_digest": self.worker_identity_digest,
            "fence_digest": self.fence_digest,
            "output_digest": self.output_digest,
            "status": self.status.value,
            "tokens_used": self.tokens_used,
            "cost_units": self.cost_units,
            "wall_time_s": self.wall_time_s,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @property
    def result_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class RemoteExecutionCommitDecision:
    accepted: bool
    reasons: tuple[str, ...]
    request_digest: str
    grant_digest: str
    result_digest: str
    completion_message_digest: str
    worker_identity_digest: str
    current_fence_digest: str
    task_id: str = REMOTE_EXECUTION_TASK_ID
    accountability_id: str = REMOTE_EXECUTION_ACCOUNTABILITY_ID
    schema_version: int = REMOTE_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise RemoteExecutionError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise RemoteExecutionError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "request_digest",
            "grant_digest",
            "result_digest",
            "completion_message_digest",
            "worker_identity_digest",
            "current_fence_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.task_id != REMOTE_EXECUTION_TASK_ID:
            raise RemoteExecutionError("task_id drift")
        if self.accountability_id != REMOTE_EXECUTION_ACCOUNTABILITY_ID:
            raise RemoteExecutionError("accountability_id drift")
        if self.schema_version != REMOTE_EXECUTION_SCHEMA_VERSION:
            raise RemoteExecutionError("unsupported commit schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "request_digest": self.request_digest,
            "grant_digest": self.grant_digest,
            "result_digest": self.result_digest,
            "completion_message_digest": self.completion_message_digest,
            "worker_identity_digest": self.worker_identity_digest,
            "current_fence_digest": self.current_fence_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-01:remote-execution-commit",
    ) -> EvidenceRef:
        if not self.accepted:
            raise RemoteExecutionError(
                "rejected remote execution cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="remote_execution_commit",
        )


def qualify_remote_execution_commit(
    *,
    request: RemoteExecutionRequest,
    worker: WorkerIdentity,
    registration: WorkerRegistration,
    liveness: LivenessView,
    attestation: WorkerAttestation,
    lease: Lease,
    current_fence: RemoteExecutionFence,
    grant: RemoteExecutionGrantDecision,
    result: RemoteExecutionResult,
    completion: WorkerMessage,
    protocol_cursor: ProtocolCursor,
    observed_at: float,
) -> RemoteExecutionCommitDecision:
    if not isinstance(grant, RemoteExecutionGrantDecision):
        raise TypeError("grant must be RemoteExecutionGrantDecision")
    if not isinstance(result, RemoteExecutionResult):
        raise TypeError("result must be RemoteExecutionResult")
    if not isinstance(completion, WorkerMessage):
        raise TypeError("completion must be WorkerMessage")
    if not isinstance(protocol_cursor, ProtocolCursor):
        raise TypeError("protocol_cursor must be ProtocolCursor")

    fresh = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        fence=current_fence,
        observed_at=observed_at,
    )
    reasons: list[str] = []
    if not fresh.accepted:
        reasons.extend(f"commit-{reason}" for reason in fresh.reasons)
    if not grant.accepted:
        reasons.append("grant-rejected")
    if grant.request_digest != request.request_digest:
        reasons.append("grant-request-mismatch")
    if grant.worker_identity_digest != worker_identity_digest(worker):
        reasons.append("grant-worker-mismatch")
    if grant.fence_digest != current_fence.fence_digest:
        reasons.append("stale-fence")
    if grant.fence_epoch != current_fence.epoch:
        reasons.append("stale-fence-epoch")

    if result.request_digest != request.request_digest:
        reasons.append("result-request-mismatch")
    if result.grant_digest != grant.decision_digest:
        reasons.append("result-grant-mismatch")
    if result.worker_identity_digest != worker_identity_digest(worker):
        reasons.append("result-worker-mismatch")
    if result.fence_digest != current_fence.fence_digest:
        reasons.append("result-fence-mismatch")
    if result.status is not RemoteResultStatus.SUCCEEDED:
        reasons.append("result-not-successful")
    if result.tokens_used > request.max_tokens:
        reasons.append("token-budget-exceeded")
    if result.cost_units > request.max_cost_units:
        reasons.append("cost-budget-exceeded")
    if result.wall_time_s > request.max_wall_time_s:
        reasons.append("wall-time-budget-exceeded")

    if completion.kind is not WorkerMessageKind.COMPLETE:
        reasons.append("completion-message-kind-mismatch")
    if completion.sender != worker:
        reasons.append("completion-worker-mismatch")
    if completion.recipient != request.coordinator_id:
        reasons.append("completion-recipient-mismatch")
    if completion.protocol_version != request.protocol_version:
        reasons.append("completion-protocol-version-mismatch")
    if completion.correlation_id != request.request_id:
        reasons.append("completion-correlation-mismatch")

    payload = dict(completion.payload)
    expected_payload = {
        "request_digest": request.request_digest,
        "grant_digest": grant.decision_digest,
        "fence_digest": current_fence.fence_digest,
        "result_digest": result.result_digest,
    }
    if payload != expected_payload:
        reasons.append("completion-payload-mismatch")

    if protocol_cursor.sender_id != worker.worker_id:
        reasons.append("protocol-cursor-worker-mismatch")
    if protocol_cursor.generation != worker.generation:
        reasons.append("protocol-cursor-generation-mismatch")
    if protocol_cursor.last_sequence != completion.sequence:
        reasons.append("protocol-cursor-sequence-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return RemoteExecutionCommitDecision(
        accepted=not normalized,
        reasons=normalized,
        request_digest=request.request_digest,
        grant_digest=grant.decision_digest,
        result_digest=result.result_digest,
        completion_message_digest=completion.digest,
        worker_identity_digest=worker_identity_digest(worker),
        current_fence_digest=current_fence.fence_digest,
    )


__all__ = [
    "REMOTE_EXECUTION_ACCOUNTABILITY_ID",
    "REMOTE_EXECUTION_SCHEMA_VERSION",
    "REMOTE_EXECUTION_TASK_ID",
    "RemoteExecutionCommitDecision",
    "RemoteExecutionError",
    "RemoteExecutionFence",
    "RemoteExecutionGrantDecision",
    "RemoteExecutionRequest",
    "RemoteExecutionResult",
    "RemoteResultStatus",
    "WorkerAttestation",
    "issue_remote_execution_fence",
    "lease_digest",
    "qualify_remote_execution",
    "qualify_remote_execution_commit",
    "worker_identity_digest",
]

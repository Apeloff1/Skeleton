"""VOL-031 scheduler-bound model placement and capacity reservation.

This coordinator is the bounded mutation bridge between pure placement
qualification and the real WorkerReservations registry. It performs no model
loading and no remote execution. It may only acquire/release capacity
reservations, and returns a content-addressed scheduling receipt.

The flow is deliberately two-phase:
1. deterministic placement selection;
2. exact hardware snapshot validation;
3. reserve selected worker generation/demand in WorkerReservations;
4. require the live reservation and re-run final placement qualification;
5. release the reservation on any qualification failure.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Mapping, Sequence

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.distributed.network.hardware_topology import (
    HardwareTopologySnapshot,
    WorkerHardwareObservation,
)
from skeleton.distributed.network.model_placement import (
    ModelPlacementDecision,
    ModelPlacementRequest,
    ModelPlacementSelection,
    ModelWarmAuthorizationDecision,
    ModelWarmObservation,
    qualify_model_placement,
    select_model_placement,
)
from skeleton.shells.worker_capacity import WorkerCapacityCatalog
from skeleton.shells.worker_heartbeat import LivenessView
from skeleton.shells.worker_identity import (
    WorkerIdentityError,
    WorkerRegistration,
)
from skeleton.shells.worker_reservations import (
    CapacityReservation,
    ReservationConflict,
    WorkerReservations,
)


PLACEMENT_SCHEDULER_SCHEMA_VERSION = 1
PLACEMENT_SCHEDULER_TASK_ID = "VOL-031"
PLACEMENT_SCHEDULER_ACCOUNTABILITY_ID = "ACC-VOL-031"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PlacementSchedulerError(ValueError):
    """Scheduler-bound placement request is malformed or unsafe."""


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise PlacementSchedulerError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PlacementSchedulerError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlacementSchedulerError(f"{field} must be positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlacementSchedulerError(f"{field} must be non-negative integer")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlacementSchedulerError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PlacementSchedulerError(f"{field} must be finite numeric")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0:
        raise PlacementSchedulerError(f"{field} must be positive")
    return result


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


@dataclass(frozen=True, slots=True)
class HardwareRequirement:
    min_logical_cores: int = 1
    min_ram_bytes: int = 1
    min_storage_free_bytes: int = 1
    min_network_mbps: float = 0.001
    min_accelerator_memory_bytes: int = 0
    min_numa_nodes: int = 1

    def __post_init__(self) -> None:
        for field in (
            "min_logical_cores",
            "min_ram_bytes",
            "min_storage_free_bytes",
            "min_numa_nodes",
        ):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "min_accelerator_memory_bytes",
            _nonnegative_int(
                self.min_accelerator_memory_bytes,
                "min_accelerator_memory_bytes",
            ),
        )
        object.__setattr__(
            self,
            "min_network_mbps",
            _positive(self.min_network_mbps, "min_network_mbps"),
        )

    def reasons(
        self,
        observation: WorkerHardwareObservation,
    ) -> tuple[str, ...]:
        if not isinstance(observation, WorkerHardwareObservation):
            raise TypeError(
                "observation must be WorkerHardwareObservation"
            )
        reasons: list[str] = []
        if observation.cpu_logical_cores < self.min_logical_cores:
            reasons.append("hardware-cpu-insufficient")
        if observation.ram_bytes < self.min_ram_bytes:
            reasons.append("hardware-ram-insufficient")
        if observation.storage_free_bytes < self.min_storage_free_bytes:
            reasons.append("hardware-storage-insufficient")
        if observation.network_mbps < self.min_network_mbps:
            reasons.append("hardware-network-insufficient")
        if observation.numa_nodes < self.min_numa_nodes:
            reasons.append("hardware-numa-insufficient")
        if (
            observation.healthy_accelerator_memory_bytes
            < self.min_accelerator_memory_bytes
        ):
            reasons.append("hardware-accelerator-memory-insufficient")
        return tuple(sorted(reasons))

    def payload(self) -> dict[str, Any]:
        return {
            "min_logical_cores": self.min_logical_cores,
            "min_ram_bytes": self.min_ram_bytes,
            "min_storage_free_bytes": self.min_storage_free_bytes,
            "min_network_mbps": self.min_network_mbps,
            "min_accelerator_memory_bytes": (
                self.min_accelerator_memory_bytes
            ),
            "min_numa_nodes": self.min_numa_nodes,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class ScheduledPlacementReceipt:
    accepted: bool
    reasons: tuple[str, ...]
    request_digest: str
    selection_digest: str
    hardware_requirement_digest: str
    hardware_snapshot_digest: str
    hardware_observation_digest: str | None
    reservation_id: str | None
    reservation_digest: str | None
    placement_decision_digest: str | None
    selected_worker_id: str | None
    selected_worker_generation: int | None
    reservation_expires_at: float | None
    authority_scope: str = "capacity-reservation-only"
    production_authority: bool = False
    schema_version: int = PLACEMENT_SCHEDULER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise PlacementSchedulerError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, str) or not reason
            for reason in self.reasons
        ):
            raise PlacementSchedulerError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "request_digest",
            "selection_digest",
            "hardware_requirement_digest",
            "hardware_snapshot_digest",
        ):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        for field in (
            "hardware_observation_digest",
            "reservation_digest",
            "placement_decision_digest",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha(value, field))
        if self.reservation_id is not None:
            object.__setattr__(
                self,
                "reservation_id",
                _token(self.reservation_id, "reservation_id"),
            )
        if self.selected_worker_id is not None:
            object.__setattr__(
                self,
                "selected_worker_id",
                _token(self.selected_worker_id, "selected_worker_id"),
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
        if self.reservation_expires_at is not None:
            object.__setattr__(
                self,
                "reservation_expires_at",
                _positive(
                    self.reservation_expires_at,
                    "reservation_expires_at",
                ),
            )
        if self.authority_scope != "capacity-reservation-only":
            raise PlacementSchedulerError("scheduler authority scope escalation")
        if self.production_authority is not False:
            raise PlacementSchedulerError(
                "scheduler receipt cannot claim production authority"
            )
        if self.schema_version != PLACEMENT_SCHEDULER_SCHEMA_VERSION:
            raise PlacementSchedulerError(
                "unsupported scheduler receipt schema"
            )
        if self.accepted:
            required = (
                self.hardware_observation_digest,
                self.reservation_id,
                self.reservation_digest,
                self.placement_decision_digest,
                self.selected_worker_id,
                self.selected_worker_generation,
                self.reservation_expires_at,
            )
            if any(value is None for value in required):
                raise PlacementSchedulerError(
                    "accepted scheduler receipt requires complete evidence"
                )
            if self.reasons:
                raise PlacementSchedulerError(
                    "accepted scheduler receipt cannot carry reasons"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": PLACEMENT_SCHEDULER_TASK_ID,
            "accountability_id": PLACEMENT_SCHEDULER_ACCOUNTABILITY_ID,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "request_digest": self.request_digest,
            "selection_digest": self.selection_digest,
            "hardware_requirement_digest": self.hardware_requirement_digest,
            "hardware_snapshot_digest": self.hardware_snapshot_digest,
            "hardware_observation_digest": (
                self.hardware_observation_digest
            ),
            "reservation_id": self.reservation_id,
            "reservation_digest": self.reservation_digest,
            "placement_decision_digest": self.placement_decision_digest,
            "selected_worker_id": self.selected_worker_id,
            "selected_worker_generation": self.selected_worker_generation,
            "reservation_expires_at": self.reservation_expires_at,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def receipt_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


def _reservation_digest(reservation: CapacityReservation) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
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
    ).hexdigest()


def _rejected_receipt(
    *,
    reasons: tuple[str, ...],
    request: ModelPlacementRequest,
    selection: ModelPlacementSelection,
    hardware_requirement: HardwareRequirement,
    hardware_snapshot: HardwareTopologySnapshot,
    hardware_observation: WorkerHardwareObservation | None = None,
    reservation: CapacityReservation | None = None,
    placement: ModelPlacementDecision | None = None,
) -> ScheduledPlacementReceipt:
    return ScheduledPlacementReceipt(
        accepted=False,
        reasons=tuple(sorted(set(reasons))),
        request_digest=request.request_digest,
        selection_digest=selection.selection_digest,
        hardware_requirement_digest=hardware_requirement.digest,
        hardware_snapshot_digest=hardware_snapshot.snapshot_digest,
        hardware_observation_digest=(
            None
            if hardware_observation is None
            else hardware_observation.observation_digest
        ),
        reservation_id=(
            None if reservation is None else reservation.reservation_id
        ),
        reservation_digest=(
            None if reservation is None else _reservation_digest(reservation)
        ),
        placement_decision_digest=(
            None if placement is None else placement.decision_digest
        ),
        selected_worker_id=selection.selected_worker_id,
        selected_worker_generation=selection.selected_worker_generation,
        reservation_expires_at=(
            None if reservation is None else reservation.expires_at
        ),
    )


def schedule_model_placement(
    *,
    request: ModelPlacementRequest,
    registrations: Sequence[WorkerRegistration],
    liveness: Mapping[str, LivenessView],
    capacities: WorkerCapacityCatalog,
    active_weight: Mapping[str, int],
    active_assignments: Mapping[str, int],
    warm_authorizations: Mapping[str, ModelWarmAuthorizationDecision],
    warm_observations: Mapping[str, ModelWarmObservation],
    hardware_snapshot: HardwareTopologySnapshot,
    hardware_requirement: HardwareRequirement,
    reservations: WorkerReservations,
    observed_at: float,
    reservation_ttl_s: float = 30.0,
) -> tuple[ScheduledPlacementReceipt, CapacityReservation | None]:
    if not isinstance(hardware_snapshot, HardwareTopologySnapshot):
        raise TypeError(
            "hardware_snapshot must be HardwareTopologySnapshot"
        )
    if not isinstance(hardware_requirement, HardwareRequirement):
        raise TypeError(
            "hardware_requirement must be HardwareRequirement"
        )
    if not isinstance(reservations, WorkerReservations):
        raise TypeError("reservations must be WorkerReservations")
    now = _finite(observed_at, "observed_at")
    if now < 0:
        raise PlacementSchedulerError("observed_at must be non-negative")
    ttl = _positive(reservation_ttl_s, "reservation_ttl_s")

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
    reasons: list[str] = []
    if not selection.selected:
        reasons.append("no-qualified-placement")

    expected_registration_digest = _registration_digest(
        registration_tuple
    )
    if hardware_snapshot.registration_digest != expected_registration_digest:
        reasons.append("hardware-registration-snapshot-mismatch")
    if now < hardware_snapshot.observed_at:
        reasons.append("hardware-snapshot-not-yet-valid")
    elif now - hardware_snapshot.observed_at > hardware_snapshot.max_age_s:
        reasons.append("hardware-snapshot-stale")

    observation: WorkerHardwareObservation | None = None
    selected_registration: WorkerRegistration | None = None
    if selection.selected:
        for registration in registration_tuple:
            if (
                registration.identity.worker_id
                == selection.selected_worker_id
                and registration.identity.generation
                == selection.selected_worker_generation
            ):
                selected_registration = registration
                break
        if selected_registration is None:
            reasons.append("selected-registration-missing")
        observation = hardware_snapshot.by_worker().get(
            selection.selected_worker_id or ""
        )
        if observation is None:
            reasons.append("selected-hardware-observation-missing")
        else:
            if observation.generation != selection.selected_worker_generation:
                reasons.append("selected-hardware-generation-mismatch")
            reasons.extend(hardware_requirement.reasons(observation))

    if reasons:
        return (
            _rejected_receipt(
                reasons=tuple(reasons),
                request=request,
                selection=selection,
                hardware_requirement=hardware_requirement,
                hardware_snapshot=hardware_snapshot,
                hardware_observation=observation,
            ),
            None,
        )

    assert selected_registration is not None
    assert observation is not None
    reservation: CapacityReservation | None = None
    try:
        reservation = reservations.reserve(
            selected_registration.identity,
            request.demand,
            ttl_seconds=ttl,
        )
        reservations.require(reservation)
    except (ReservationConflict, WorkerIdentityError) as exc:
        return (
            _rejected_receipt(
                reasons=(f"reservation-conflict:{type(exc).__name__}",),
                request=request,
                selection=selection,
                hardware_requirement=hardware_requirement,
                hardware_snapshot=hardware_snapshot,
                hardware_observation=observation,
            ),
            None,
        )

    placement = qualify_model_placement(
        request=request,
        registrations=registration_tuple,
        liveness=liveness,
        capacities=capacities,
        active_weight=active_weight,
        active_assignments=active_assignments,
        warm_authorizations=warm_authorizations,
        warm_observations=warm_observations,
        reservation=reservation,
        observed_at=now,
    )
    if not placement.accepted:
        reservations.release(reservation)
        return (
            _rejected_receipt(
                reasons=(
                    "final-placement-rejected",
                    *placement.reasons,
                ),
                request=request,
                selection=selection,
                hardware_requirement=hardware_requirement,
                hardware_snapshot=hardware_snapshot,
                hardware_observation=observation,
                reservation=reservation,
                placement=placement,
            ),
            None,
        )
    if placement.selected_worker_id != selection.selected_worker_id:
        reservations.release(reservation)
        return (
            _rejected_receipt(
                reasons=("selection-changed-after-reservation",),
                request=request,
                selection=selection,
                hardware_requirement=hardware_requirement,
                hardware_snapshot=hardware_snapshot,
                hardware_observation=observation,
                reservation=reservation,
                placement=placement,
            ),
            None,
        )
    try:
        reservations.require(reservation)
    except (ReservationConflict, WorkerIdentityError):
        reservations.release(reservation)
        return (
            _rejected_receipt(
                reasons=("reservation-lost-before-schedule-receipt",),
                request=request,
                selection=selection,
                hardware_requirement=hardware_requirement,
                hardware_snapshot=hardware_snapshot,
                hardware_observation=observation,
                reservation=reservation,
                placement=placement,
            ),
            None,
        )

    return (
        ScheduledPlacementReceipt(
            accepted=True,
            reasons=(),
            request_digest=request.request_digest,
            selection_digest=selection.selection_digest,
            hardware_requirement_digest=hardware_requirement.digest,
            hardware_snapshot_digest=hardware_snapshot.snapshot_digest,
            hardware_observation_digest=observation.observation_digest,
            reservation_id=reservation.reservation_id,
            reservation_digest=_reservation_digest(reservation),
            placement_decision_digest=placement.decision_digest,
            selected_worker_id=selection.selected_worker_id,
            selected_worker_generation=selection.selected_worker_generation,
            reservation_expires_at=reservation.expires_at,
        ),
        reservation,
    )


__all__ = [
    "PLACEMENT_SCHEDULER_ACCOUNTABILITY_ID",
    "PLACEMENT_SCHEDULER_SCHEMA_VERSION",
    "PLACEMENT_SCHEDULER_TASK_ID",
    "HardwareRequirement",
    "PlacementSchedulerError",
    "ScheduledPlacementReceipt",
    "schedule_model_placement",
]

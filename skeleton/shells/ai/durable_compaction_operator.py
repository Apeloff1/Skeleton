"""Durable orchestration for evidence-chain compaction and pruning.

The lower-level durable evidence stack deliberately separates authority:

* retention chooses a candidate historical prefix;
* compaction readiness proves archive coverage without deletion authority;
* a signed readiness certificate records that proof;
* a short-lived pruning authorization crosses the destructive authority line;
* the pruning executor commits a signed hot floor and deletes the exact frozen
  manifest under a fencing lease.

This module composes those primitives without weakening their boundaries.  It
adds one durable workflow record that binds every artifact digest and phase so
an operator can restart safely, inspect staleness before destructive work, and
prove exactly which authority led to which deleted interval.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_checkpoint import CheckpointableEvidenceChain
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionReadiness,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificateError,
    DurableCompactionCertificateStore,
    SignedDurableCompactionCertificate,
)
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceOperation,
    DurableMaintenanceResource,
    DurableMaintenanceStale,
    DurableMaintenanceStore,
    SignedDurableMaintenanceEpoch,
)
from skeleton.shells.ai.durable_pruning import (
    DurablePruningError,
    DurablePruningExecutor,
    DurablePruningManualReview,
    DurablePruningManifest,
    DurablePruningOperation,
    DurablePruningPhase,
    DurablePruningResult,
)
from skeleton.shells.ai.durable_compaction_reservation import (
    DurableCompactionReservationConflict,
    DurableCompactionReservationStore,
)
from skeleton.shells.ai.durable_compaction_workflow_index import (
    CompactionWorkflowIndexReport,
    DurableCompactionWorkflowIndex,
)
from skeleton.shells.ai.durable_pruning_authorization import (
    DurablePruningAuthorizationError,
    DurablePruningAuthorizationStore,
    SignedDurablePruningAuthorization,
)
from skeleton.shells.ai.durable_retention import DurableRetentionPlan
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


class DurableCompactionWorkflowPhase(str, Enum):
    PLANNED = "planned"
    CERTIFIED = "certified"
    AUTHORIZED = "authorized"
    PREPARED = "prepared"
    EXECUTING = "executing"
    COMPLETE = "complete"
    MANUAL_REVIEW = "manual_review"


_PHASE_ORDER = {
    DurableCompactionWorkflowPhase.PLANNED: 10,
    DurableCompactionWorkflowPhase.CERTIFIED: 20,
    DurableCompactionWorkflowPhase.AUTHORIZED: 30,
    DurableCompactionWorkflowPhase.PREPARED: 40,
    DurableCompactionWorkflowPhase.EXECUTING: 50,
    DurableCompactionWorkflowPhase.COMPLETE: 60,
    DurableCompactionWorkflowPhase.MANUAL_REVIEW: 90,
}


@dataclass(frozen=True)
class DurableCompactionWorkflow:
    schema_version: int
    workflow_id: str
    chain_id: str
    operator_id: str
    phase: DurableCompactionWorkflowPhase
    retention_plan_digest: str
    readiness_digest: str
    compaction_policy_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    previous_floor_sequence: int
    previous_floor_root: str
    archive_id: str
    archive_manifest_digest: str
    certificate_id: str = ""
    certificate_digest: str = ""
    authorization_id: str = ""
    authorization_digest: str = ""
    pruning_operation_id: str = ""
    pruning_manifest_digest: str = ""
    pruning_phase: str = ""
    floor_id: str = ""
    delete_count: int = 0
    deleted_items: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    error_count: int = 0
    last_error: str = ""
    last_error_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable compaction workflow schema"
            )
        for name in (
            "workflow_id",
            "retention_plan_digest",
            "readiness_digest",
            "compaction_policy_digest",
            "current_root",
            "cutoff_root",
            "previous_floor_root",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        for name in (
            "archive_manifest_digest",
            "certificate_id",
            "certificate_digest",
            "authorization_id",
            "authorization_digest",
            "pruning_operation_id",
            "pruning_manifest_digest",
            "floor_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        object.__setattr__(
            self,
            "phase",
            DurableCompactionWorkflowPhase(
                self.phase
            ),
        )
        if self.pruning_phase:
            object.__setattr__(
                self,
                "pruning_phase",
                DurablePruningPhase(
                    self.pruning_phase
                ).value,
            )
        for name in (
            "current_sequence",
            "cutoff_sequence",
            "previous_floor_sequence",
            "delete_count",
            "deleted_items",
            "error_count",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.cutoff_sequence <= 0:
            raise ValueError(
                "workflow cutoff_sequence must be positive"
            )
        if self.cutoff_sequence > self.current_sequence:
            raise ValueError(
                "workflow cutoff exceeds current sequence"
            )
        if (
            self.previous_floor_sequence
            >= self.cutoff_sequence
        ):
            raise ValueError(
                "workflow cutoff must advance previous hot floor"
            )
        if self.delete_count and self.delete_count != (
            self.cutoff_sequence
            - self.previous_floor_sequence
        ):
            raise ValueError(
                "workflow delete_count differs from floor interval"
            )
        if self.deleted_items > self.delete_count:
            raise ValueError(
                "workflow deleted_items exceeds delete_count"
            )
        if (
            self.previous_floor_sequence == 0
            and self.previous_floor_root != "0" * 64
        ):
            raise ValueError(
                "genesis previous floor must use genesis root"
            )
        for name in (
            "created_at",
            "updated_at",
            "last_error_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if self.updated_at < self.created_at:
            raise ValueError(
                "workflow updated_at precedes creation"
            )
        if self.error_count:
            if not self.last_error:
                raise ValueError(
                    "workflow error_count requires last_error"
                )
            if self.last_error_at <= 0.0:
                raise ValueError(
                    "workflow error_count requires last_error_at"
                )
        elif self.last_error or self.last_error_at:
            raise ValueError(
                "workflow error fields require error_count"
            )
        if len(self.last_error) > 2048:
            raise ValueError(
                "workflow last_error is too long"
            )
        self._validate_phase_contract()

    def _validate_phase_contract(self) -> None:
        order = _PHASE_ORDER[self.phase]
        if (
            order
            >= _PHASE_ORDER[
                DurableCompactionWorkflowPhase.CERTIFIED
            ]
            and self.phase
            is not DurableCompactionWorkflowPhase.MANUAL_REVIEW
        ):
            if (
                not self.certificate_id
                or not self.certificate_digest
            ):
                raise ValueError(
                    "certified workflow requires certificate binding"
                )
        if (
            order
            >= _PHASE_ORDER[
                DurableCompactionWorkflowPhase.AUTHORIZED
            ]
            and self.phase
            is not DurableCompactionWorkflowPhase.MANUAL_REVIEW
        ):
            if (
                not self.authorization_id
                or not self.authorization_digest
                or self.delete_count <= 0
            ):
                raise ValueError(
                    "authorized workflow requires destructive authority binding"
                )
        if (
            order
            >= _PHASE_ORDER[
                DurableCompactionWorkflowPhase.PREPARED
            ]
            and self.phase
            not in {
                DurableCompactionWorkflowPhase.MANUAL_REVIEW,
            }
        ):
            if (
                not self.pruning_operation_id
                or not self.pruning_manifest_digest
                or not self.pruning_phase
            ):
                raise ValueError(
                    "prepared workflow requires pruning manifest binding"
                )
        if self.phase is DurableCompactionWorkflowPhase.COMPLETE:
            if (
                self.pruning_phase
                != DurablePruningPhase.COMPLETE.value
                or not self.floor_id
                or self.deleted_items != self.delete_count
            ):
                raise ValueError(
                    "complete workflow requires completed pruning result"
                )

    @property
    def destructive_authority_issued(self) -> bool:
        return bool(
            self.authorization_id
            and self.authorization_digest
        )

    @property
    def delete_manifest_frozen(self) -> bool:
        return bool(
            self.pruning_operation_id
            and self.pruning_manifest_digest
        )

    @property
    def complete(self) -> bool:
        return (
            self.phase
            is DurableCompactionWorkflowPhase.COMPLETE
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.phase
            is DurableCompactionWorkflowPhase.MANUAL_REVIEW
        )

    @property
    def resumable(self) -> bool:
        return self.phase in {
            DurableCompactionWorkflowPhase.PREPARED,
            DurableCompactionWorkflowPhase.EXECUTING,
        }

    @property
    def binding_dict(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "chain_id": self.chain_id,
            "operator_id": self.operator_id,
            "retention_plan_digest": (
                self.retention_plan_digest
            ),
            "readiness_digest": self.readiness_digest,
            "compaction_policy_digest": (
                self.compaction_policy_digest
            ),
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "previous_floor_sequence": (
                self.previous_floor_sequence
            ),
            "previous_floor_root": (
                self.previous_floor_root
            ),
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
        }

    @property
    def binding_digest(self) -> str:
        raw = json.dumps(
            self.binding_dict,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            **self.binding_dict,
            "binding_digest": self.binding_digest,
            "phase": self.phase.value,
            "certificate_id": self.certificate_id,
            "certificate_digest": (
                self.certificate_digest
            ),
            "authorization_id": self.authorization_id,
            "authorization_digest": (
                self.authorization_digest
            ),
            "pruning_operation_id": (
                self.pruning_operation_id
            ),
            "pruning_manifest_digest": (
                self.pruning_manifest_digest
            ),
            "pruning_phase": self.pruning_phase,
            "floor_id": self.floor_id,
            "delete_count": self.delete_count,
            "deleted_items": self.deleted_items,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "destructive_authority_issued": (
                self.destructive_authority_issued
            ),
            "delete_manifest_frozen": (
                self.delete_manifest_frozen
            ),
            "complete": self.complete,
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "resumable": self.resumable,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class StoredDurableCompactionWorkflow:
    revision: int
    workflow: DurableCompactionWorkflow

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "workflow revision must be positive"
            )
        if not isinstance(
            self.workflow,
            DurableCompactionWorkflow,
        ):
            raise TypeError(
                "workflow must be DurableCompactionWorkflow"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "workflow": self.workflow.to_dict(),
        }


@dataclass(frozen=True)
class DurableCompactionWorkflowPlan:
    stored: StoredDurableCompactionWorkflow
    readiness: DurableCompactionReadiness

    def __post_init__(self) -> None:
        if not isinstance(
            self.stored,
            StoredDurableCompactionWorkflow,
        ):
            raise TypeError(
                "stored must be StoredDurableCompactionWorkflow"
            )
        if not isinstance(
            self.readiness,
            DurableCompactionReadiness,
        ):
            raise TypeError(
                "readiness must be DurableCompactionReadiness"
            )
        if (
            self.stored.workflow.readiness_digest
            != self.readiness.digest
        ):
            raise ValueError(
                "workflow/readiness digest mismatch"
            )

    @property
    def workflow_id(self) -> str:
        return self.stored.workflow.workflow_id

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "readiness": self.readiness.to_dict(),
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class DurableCompactionPrepared:
    stored: StoredDurableCompactionWorkflow
    certificate: SignedDurableCompactionCertificate
    authorization: SignedDurablePruningAuthorization
    manifest: DurablePruningManifest
    operation: DurablePruningOperation

    def __post_init__(self) -> None:
        if (
            self.stored.workflow.certificate_id
            != self.certificate.certificate_id
        ):
            raise ValueError(
                "prepared certificate differs from workflow"
            )
        if (
            self.stored.workflow.authorization_id
            != self.authorization.authorization_id
        ):
            raise ValueError(
                "prepared authorization differs from workflow"
            )
        if (
            self.stored.workflow.pruning_operation_id
            != self.operation.operation_id
            or self.manifest.operation_id
            != self.operation.operation_id
        ):
            raise ValueError(
                "prepared pruning operation identity mismatch"
            )
        if (
            self.stored.workflow.pruning_manifest_digest
            != self.manifest.digest
            or self.operation.manifest_digest
            != self.manifest.digest
        ):
            raise ValueError(
                "prepared pruning manifest digest mismatch"
            )

    @property
    def destructive_action_authorized(self) -> bool:
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "certificate": self.certificate.to_dict(),
            "authorization": self.authorization.to_dict(),
            "manifest": self.manifest.to_dict(),
            "operation": self.operation.to_dict(),
            "destructive_action_authorized": True,
        }


@dataclass(frozen=True)
class DurableCompactionExecution:
    stored: StoredDurableCompactionWorkflow
    result: DurablePruningResult

    def __post_init__(self) -> None:
        if (
            self.stored.workflow.pruning_operation_id
            != self.result.operation.operation_id
        ):
            raise ValueError(
                "execution result operation differs from workflow"
            )
        if (
            self.stored.workflow.pruning_manifest_digest
            != self.result.manifest.digest
        ):
            raise ValueError(
                "execution result manifest differs from workflow"
            )
        if self.result.ok and not self.stored.workflow.complete:
            raise ValueError(
                "successful pruning result requires complete workflow"
            )

    @property
    def ok(self) -> bool:
        return (
            self.stored.workflow.complete
            and self.result.ok
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "stored": self.stored.to_dict(),
            "result": self.result.to_dict(),
        }


@dataclass(frozen=True)
class DurableCompactionWorkflowInspection:
    stored: StoredDurableCompactionWorkflow
    readiness_current: bool
    certificate_current: bool
    authorization_current: bool
    pruning_state_consistent: bool
    live_head_matches: bool
    hot_floor_consistent: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "readiness_current",
            "certificate_current",
            "authorization_current",
            "pruning_state_consistent",
            "live_head_matches",
            "hot_floor_consistent",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 2048
            for item in self.reasons
        ):
            raise ValueError(
                "invalid workflow inspection reason"
            )

    @property
    def current(self) -> bool:
        workflow = self.stored.workflow
        if workflow.complete:
            return (
                self.pruning_state_consistent
                and self.hot_floor_consistent
                and not self.reasons
            )
        required = (
            self.readiness_current
            and self.live_head_matches
        )
        if workflow.certificate_id:
            required = (
                required
                and self.certificate_current
            )
        if workflow.authorization_id:
            required = (
                required
                and self.authorization_current
            )
        if workflow.pruning_operation_id:
            required = (
                required
                and self.pruning_state_consistent
            )
        return (
            required
            and self.hot_floor_consistent
            and not self.reasons
        )

    @property
    def safe_to_execute(self) -> bool:
        return (
            self.current
            and self.stored.workflow.phase
            is DurableCompactionWorkflowPhase.PREPARED
        )

    @property
    def safe_to_resume(self) -> bool:
        return (
            self.stored.workflow.resumable
            and self.pruning_state_consistent
            and self.hot_floor_consistent
            and not self.stored.workflow.requires_manual_review
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "current": self.current,
            "safe_to_execute": self.safe_to_execute,
            "safe_to_resume": self.safe_to_resume,
            "readiness_current": self.readiness_current,
            "certificate_current": (
                self.certificate_current
            ),
            "authorization_current": (
                self.authorization_current
            ),
            "pruning_state_consistent": (
                self.pruning_state_consistent
            ),
            "live_head_matches": (
                self.live_head_matches
            ),
            "hot_floor_consistent": (
                self.hot_floor_consistent
            ),
            "reasons": list(self.reasons),
        }


class DurableCompactionWorkflowError(RuntimeError):
    pass


class DurableCompactionWorkflowStale(
    DurableCompactionWorkflowError
):
    pass


class DurableCompactionWorkflowManualReview(
    DurableCompactionWorkflowError
):
    pass


class DurableCompactionOperator:
    """Persist and orchestrate the complete compaction authority chain."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        planner: DurableCompactionPlanner,
        certificates: DurableCompactionCertificateStore,
        authorizations: DurablePruningAuthorizationStore,
        pruning: DurablePruningExecutor,
        *,
        maintenance: DurableMaintenanceStore | None = None,
        reservations: DurableCompactionReservationStore | None = None,
        workflow_index: DurableCompactionWorkflowIndex | None = None,
        namespace: str = (
            "shell-ai-durable-compaction-workflows"
        ),
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if not isinstance(
            planner,
            DurableCompactionPlanner,
        ):
            raise TypeError(
                "planner must be DurableCompactionPlanner"
            )
        if not isinstance(
            certificates,
            DurableCompactionCertificateStore,
        ):
            raise TypeError(
                "certificates must be DurableCompactionCertificateStore"
            )
        if not isinstance(
            authorizations,
            DurablePruningAuthorizationStore,
        ):
            raise TypeError(
                "authorizations must be DurablePruningAuthorizationStore"
            )
        if not isinstance(
            pruning,
            DurablePruningExecutor,
        ):
            raise TypeError(
                "pruning must be DurablePruningExecutor"
            )
        if certificates.planner is not planner:
            raise ValueError(
                "certificate store is wired to a different compaction planner"
            )
        if authorizations.certificates is not certificates:
            raise ValueError(
                "pruning authorizations are wired to a different certificate store"
            )
        if pruning.authorizations is not authorizations:
            raise ValueError(
                "pruning executor is wired to a different authorization store"
            )
        pruning_maintenance = getattr(
            pruning,
            "maintenance",
            None,
        )
        if (
            maintenance is not None
            and not isinstance(
                maintenance,
                DurableMaintenanceStore,
            )
        ):
            raise TypeError(
                "maintenance must be DurableMaintenanceStore"
            )
        if maintenance is None:
            maintenance = pruning_maintenance
        elif pruning_maintenance is None:
            raise ValueError(
                "maintenance-enabled compaction requires maintenance-enabled pruning"
            )
        elif maintenance is not pruning_maintenance:
            raise ValueError(
                "compaction and pruning must share maintenance store"
            )

        if (
            reservations is not None
            and not isinstance(
                reservations,
                DurableCompactionReservationStore,
            )
        ):
            raise TypeError(
                "reservations must be DurableCompactionReservationStore"
            )
        if (
            workflow_index is not None
            and not isinstance(
                workflow_index,
                DurableCompactionWorkflowIndex,
            )
        ):
            raise TypeError(
                "workflow_index must be DurableCompactionWorkflowIndex"
            )
        if (
            workflow_index is not None
            and workflow_index.backend is not backend
        ):
            raise ValueError(
                "workflow_index must use operator backend"
            )
        if (
            not namespace
            or len(namespace) > 128
        ):
            raise ValueError(
                "invalid compaction workflow namespace"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.planner = planner
        self.certificates = certificates
        self.authorizations = authorizations
        self.pruning = pruning
        self.maintenance = maintenance
        self.reservations = reservations
        self.namespace = namespace
        self.workflow_index = (
            workflow_index
            or DurableCompactionWorkflowIndex(
                backend,
                namespace=(
                    DurableCompactionWorkflowIndex
                    .default_namespace(namespace)
                ),
                clock=clock,
            )
        )
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    def maintenance_resource(
        self,
        workflow: DurableCompactionWorkflow,
        chain: CheckpointableEvidenceChain,
    ) -> DurableMaintenanceResource:
        return DurableMaintenanceResource.from_chain(
            workflow.chain_id,
            chain,
            resource_kind="evidence-chain",
        )

    def _require_maintenance(
        self,
        workflow: DurableCompactionWorkflow,
        chain: CheckpointableEvidenceChain,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ),
    ):
        if self.maintenance is None:
            return None
        if maintenance_epoch is None:
            raise DurableCompactionWorkflowError(
                "durable maintenance epoch is required for compaction"
            )
        if not isinstance(
            maintenance_epoch,
            SignedDurableMaintenanceEpoch,
        ):
            raise TypeError(
                "maintenance_epoch must be SignedDurableMaintenanceEpoch"
            )
        resource = self.maintenance_resource(
            workflow,
            chain,
        )
        try:
            return self.maintenance.require_active(
                maintenance_epoch,
                operation=(
                    DurableMaintenanceOperation.COMPACTION
                ),
                required_resources=(
                    workflow.chain_id,
                ),
                live_resources=(resource,),
            )
        except DurableMaintenanceStale as exc:
            raise DurableCompactionWorkflowStale(
                "durable maintenance authority is stale: "
                + str(exc)
            ) from exc

    @staticmethod
    def _key(workflow_id: str) -> str:
        return (
            "workflow:"
            + _digest(
                "workflow_id",
                workflow_id,
            )
        )

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise DurableCompactionWorkflowError(
                "workflow clock returned invalid time"
            )
        return float(value)

    def _require_reservation(
        self,
        workflow: DurableCompactionWorkflow,
        *,
        reservation_holder_id: str = "",
    ) -> None:
        if self.reservations is None:
            return
        if workflow.complete:
            return
        if reservation_holder_id:
            try:
                self.reservations.require_holder(
                    workflow.chain_id,
                    holder_id=reservation_holder_id,
                    operator_id=workflow.operator_id,
                )
            except DurableCompactionReservationConflict as exc:
                raise DurableCompactionWorkflowStale(
                    "compaction reservation is missing, expired, or owned by another holder"
                ) from exc
            return
        try:
            self.reservations.assert_available(
                workflow.chain_id,
            )
        except DurableCompactionReservationConflict as exc:
            raise DurableCompactionWorkflowStale(
                "chain is reserved by another compaction workflow"
            ) from exc

    @staticmethod
    def _floor(
        chain: CheckpointableEvidenceChain,
    ) -> tuple[int, str]:
        method = getattr(
            chain,
            "hot_floor",
            None,
        )
        if not callable(method):
            return 0, "0" * 64
        floor = method()
        return (
            int(floor.sequence),
            str(floor.root_hash),
        )

    @classmethod
    def derive_workflow_id(
        cls,
        readiness: DurableCompactionReadiness,
        *,
        operator_id: str,
        previous_floor_sequence: int,
        previous_floor_root: str,
    ) -> str:
        if not isinstance(
            readiness,
            DurableCompactionReadiness,
        ):
            raise TypeError(
                "readiness must be DurableCompactionReadiness"
            )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        if (
            isinstance(previous_floor_sequence, bool)
            or not isinstance(previous_floor_sequence, int)
            or previous_floor_sequence < 0
        ):
            raise ValueError(
                "previous_floor_sequence must be non-negative"
            )
        previous_floor_root = _digest(
            "previous_floor_root",
            previous_floor_root,
        )
        raw = json.dumps(
            {
                "chain_id": readiness.chain_id,
                "operator_id": operator_id,
                "retention_plan_digest": (
                    readiness.retention_plan_digest
                ),
                "readiness_digest": readiness.digest,
                "current_sequence": (
                    readiness.current_sequence
                ),
                "current_root": readiness.current_root,
                "cutoff_sequence": (
                    readiness.cutoff_sequence
                ),
                "cutoff_root": readiness.cutoff_root,
                "previous_floor_sequence": (
                    previous_floor_sequence
                ),
                "previous_floor_root": (
                    previous_floor_root
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def current(
        self,
        workflow_id: str,
    ) -> StoredDurableCompactionWorkflow | None:
        record = self.backend.get(
            self.namespace,
            self._key(workflow_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableCompactionWorkflow,
        ):
            raise DurableCompactionWorkflowError(
                "workflow backend value type mismatch"
            )
        return StoredDurableCompactionWorkflow(
            record.revision,
            record.value,
        )

    @staticmethod
    def _same_binding(
        left: DurableCompactionWorkflow,
        right: DurableCompactionWorkflow,
    ) -> bool:
        return (
            left.binding_digest
            == right.binding_digest
        )

    def _create(
        self,
        workflow: DurableCompactionWorkflow,
    ) -> StoredDurableCompactionWorkflow:
        # Reserve discovery metadata before creating the workflow record.
        # If the process crashes between these writes, maintenance sees an
        # indexed-but-missing workflow rather than silently losing evidence
        # that compaction authority was being established.
        self.workflow_index.reserve(
            workflow.chain_id,
            workflow.workflow_id,
        )
        key = self._key(
            workflow.workflow_id
        )
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                workflow,
            )
            return StoredDurableCompactionWorkflow(
                record.revision,
                workflow,
            )
        except DistributedStateConflict:
            existing = self.current(
                workflow.workflow_id
            )
            if existing is None:
                raise
            if not self._same_binding(
                existing.workflow,
                workflow,
            ):
                raise DurableCompactionWorkflowError(
                    "workflow id already binds different compaction authority"
                )
            return existing

    def indexed_workflows(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> tuple[str, ...]:
        return self.workflow_index.workflow_ids(
            chain_id,
            max_items=max_items,
        )

    def inspect_workflow_index(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> CompactionWorkflowIndexReport:
        return self.workflow_index.inspect(
            chain_id,
            max_items=max_items,
        )

    def require_workflow_index(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> CompactionWorkflowIndexReport:
        return self.workflow_index.require(
            chain_id,
            max_items=max_items,
        )

    def index_existing(
        self,
        workflow_id: str,
    ):
        stored = self.current(
            workflow_id
        )
        if stored is None:
            raise DurableCompactionWorkflowError(
                "workflow is missing"
            )
        return self.workflow_index.reserve(
            stored.workflow.chain_id,
            stored.workflow.workflow_id,
        )

    def _replace(
        self,
        expected: DurableCompactionWorkflow,
        **changes,
    ) -> StoredDurableCompactionWorkflow:
        key = self._key(
            expected.workflow_id
        )
        for _ in range(self.max_cas_retries):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                raise DurableCompactionWorkflowError(
                    "workflow is missing"
                )
            current = record.value
            if not isinstance(
                current,
                DurableCompactionWorkflow,
            ):
                raise DurableCompactionWorkflowError(
                    "workflow backend value type mismatch"
                )
            if not self._same_binding(
                current,
                expected,
            ):
                raise DurableCompactionWorkflowError(
                    "workflow authority binding changed"
                )

            requested_phase = changes.get(
                "phase",
                current.phase,
            )
            requested_phase = (
                DurableCompactionWorkflowPhase(
                    requested_phase
                )
            )
            if (
                current.phase
                is DurableCompactionWorkflowPhase.MANUAL_REVIEW
                and requested_phase
                is not DurableCompactionWorkflowPhase.MANUAL_REVIEW
            ):
                raise DurableCompactionWorkflowManualReview(
                    "manual-review workflow cannot advance automatically"
                )
            if (
                current.phase
                is DurableCompactionWorkflowPhase.COMPLETE
                and requested_phase
                is not DurableCompactionWorkflowPhase.COMPLETE
            ):
                raise DurableCompactionWorkflowError(
                    "complete workflow cannot regress"
                )
            if (
                requested_phase
                is not DurableCompactionWorkflowPhase.MANUAL_REVIEW
                and _PHASE_ORDER[requested_phase]
                < _PHASE_ORDER[current.phase]
            ):
                return StoredDurableCompactionWorkflow(
                    record.revision,
                    current,
                )

            updated = replace(
                current,
                updated_at=self._now(),
                **changes,
            )
            if updated == current:
                return StoredDurableCompactionWorkflow(
                    record.revision,
                    current,
                )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredDurableCompactionWorkflow(
                    stored.revision,
                    updated,
                )
            except DistributedStateConflict:
                continue
        raise DurableCompactionWorkflowError(
            "workflow CAS retry budget exhausted"
        )

    def _note_error(
        self,
        workflow: DurableCompactionWorkflow,
        exc: BaseException,
        *,
        manual_review: bool = False,
    ) -> StoredDurableCompactionWorkflow:
        message = (
            f"{type(exc).__name__}: {exc}"
        )[:2048]
        return self._replace(
            workflow,
            phase=(
                DurableCompactionWorkflowPhase.MANUAL_REVIEW
                if manual_review
                else workflow.phase
            ),
            error_count=workflow.error_count + 1,
            last_error=message,
            last_error_at=self._now(),
        )

    def _require(
        self,
        workflow_id: str,
    ) -> StoredDurableCompactionWorkflow:
        stored = self.current(
            workflow_id
        )
        if stored is None:
            raise DurableCompactionWorkflowError(
                "workflow is missing"
            )
        if stored.workflow.requires_manual_review:
            raise DurableCompactionWorkflowManualReview(
                stored.workflow.last_error
                or "workflow requires manual review"
            )
        return stored

    @staticmethod
    def _require_retention_binding(
        workflow: DurableCompactionWorkflow,
        retention: DurableRetentionPlan,
    ) -> None:
        if not isinstance(
            retention,
            DurableRetentionPlan,
        ):
            raise TypeError(
                "retention must be DurableRetentionPlan"
            )
        if (
            retention.chain_id
            != workflow.chain_id
            or retention.digest
            != workflow.retention_plan_digest
            or retention.current_sequence
            != workflow.current_sequence
            or retention.current_root
            != workflow.current_root
            or retention.archive_through_sequence
            != workflow.cutoff_sequence
            or retention.archive_through_root
            != workflow.cutoff_root
        ):
            raise DurableCompactionWorkflowStale(
                "retention plan differs from workflow binding"
            )

    @staticmethod
    def _require_readiness_binding(
        workflow: DurableCompactionWorkflow,
        readiness: DurableCompactionReadiness,
    ) -> None:
        if (
            readiness.chain_id
            != workflow.chain_id
            or readiness.digest
            != workflow.readiness_digest
            or readiness.policy_digest
            != workflow.compaction_policy_digest
            or readiness.current_sequence
            != workflow.current_sequence
            or readiness.current_root
            != workflow.current_root
            or readiness.cutoff_sequence
            != workflow.cutoff_sequence
            or readiness.cutoff_root
            != workflow.cutoff_root
            or readiness.archive_id
            != workflow.archive_id
            or readiness.archive_manifest_digest
            != workflow.archive_manifest_digest
        ):
            raise DurableCompactionWorkflowStale(
                "current compaction readiness differs from workflow binding"
            )

    def _revalidate(
        self,
        workflow: DurableCompactionWorkflow,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCompactionReadiness:
        self._require_retention_binding(
            workflow,
            retention,
        )
        readiness = self.planner.require_ready(
            retention,
            chain,
        )
        self._require_readiness_binding(
            workflow,
            readiness,
        )
        floor_sequence, floor_root = (
            self._floor(chain)
        )
        if (
            floor_sequence
            != workflow.previous_floor_sequence
            or floor_root
            != workflow.previous_floor_root
        ):
            if (
                workflow.phase
                in {
                    DurableCompactionWorkflowPhase.PREPARED,
                    DurableCompactionWorkflowPhase.EXECUTING,
                    DurableCompactionWorkflowPhase.COMPLETE,
                }
                and floor_sequence
                == workflow.cutoff_sequence
                and floor_root
                == workflow.cutoff_root
            ):
                return readiness
            raise DurableCompactionWorkflowStale(
                "hot floor differs from workflow binding"
            )
        return readiness

    @staticmethod
    def _require_certificate_binding(
        workflow: DurableCompactionWorkflow,
        item: SignedDurableCompactionCertificate,
    ) -> None:
        cert = item.certificate
        if (
            cert.chain_id != workflow.chain_id
            or cert.readiness_digest
            != workflow.readiness_digest
            or cert.retention_plan_digest
            != workflow.retention_plan_digest
            or cert.compaction_policy_digest
            != workflow.compaction_policy_digest
            or cert.current_sequence
            != workflow.current_sequence
            or cert.current_root
            != workflow.current_root
            or cert.cutoff_sequence
            != workflow.cutoff_sequence
            or cert.cutoff_root
            != workflow.cutoff_root
            or cert.archive_id
            != workflow.archive_id
            or cert.archive_manifest_digest
            != workflow.archive_manifest_digest
        ):
            raise DurableCompactionWorkflowStale(
                "compaction certificate differs from workflow binding"
            )

    @staticmethod
    def _require_authorization_binding(
        workflow: DurableCompactionWorkflow,
        item: SignedDurablePruningAuthorization,
    ) -> None:
        auth = item.authorization
        if (
            auth.chain_id != workflow.chain_id
            or auth.operator_id
            != workflow.operator_id
            or auth.certificate_id
            != workflow.certificate_id
            or auth.current_sequence
            != workflow.current_sequence
            or auth.current_root
            != workflow.current_root
            or auth.cutoff_sequence
            != workflow.cutoff_sequence
            or auth.cutoff_root
            != workflow.cutoff_root
            or auth.previous_floor_sequence
            != workflow.previous_floor_sequence
            or auth.previous_floor_root
            != workflow.previous_floor_root
            or auth.archive_id
            != workflow.archive_id
            or auth.archive_manifest_digest
            != workflow.archive_manifest_digest
        ):
            raise DurableCompactionWorkflowStale(
                "pruning authorization differs from workflow binding"
            )

    def plan(
        self,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        operator_id: str,
    ) -> DurableCompactionWorkflowPlan:
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        readiness = self.planner.require_ready(
            retention,
            chain,
        )
        floor_sequence, floor_root = (
            self._floor(chain)
        )
        if (
            floor_sequence
            >= readiness.cutoff_sequence
        ):
            raise DurableCompactionWorkflowStale(
                "compaction cutoff does not advance current hot floor"
            )
        workflow_id = self.derive_workflow_id(
            readiness,
            operator_id=operator_id,
            previous_floor_sequence=(
                floor_sequence
            ),
            previous_floor_root=floor_root,
        )
        now = self._now()
        workflow = DurableCompactionWorkflow(
            1,
            workflow_id,
            readiness.chain_id,
            operator_id,
            DurableCompactionWorkflowPhase.PLANNED,
            readiness.retention_plan_digest,
            readiness.digest,
            readiness.policy_digest,
            readiness.current_sequence,
            readiness.current_root,
            readiness.cutoff_sequence,
            readiness.cutoff_root,
            floor_sequence,
            floor_root,
            readiness.archive_id,
            readiness.archive_manifest_digest,
            created_at=now,
            updated_at=now,
        )
        stored = self._create(
            workflow
        )
        return DurableCompactionWorkflowPlan(
            stored,
            readiness,
        )

    def certify(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        ttl_seconds: float | None = None,
        reservation_holder_id: str = "",
    ) -> SignedDurableCompactionCertificate:
        stored = self._require(
            workflow_id
        )
        workflow = stored.workflow
        self._require_reservation(
            workflow,
            reservation_holder_id=reservation_holder_id,
        )
        self._revalidate(
            workflow,
            retention,
            chain,
        )

        if workflow.certificate_id:
            existing = self.certificates.get(
                workflow.certificate_id
            )
            if existing is None:
                raise DurableCompactionWorkflowManualReview(
                    "workflow references missing compaction certificate"
                )
            self._require_certificate_binding(
                workflow,
                existing,
            )
            try:
                self.certificates.require_current(
                    existing,
                    retention,
                    chain,
                )
            except DurableCompactionCertificateError:
                if (
                    workflow.phase
                    is not DurableCompactionWorkflowPhase.CERTIFIED
                ):
                    raise DurableCompactionWorkflowStale(
                        "bound compaction certificate is no longer current"
                    )
            else:
                return existing

        certificate = self.certificates.issue(
            retention,
            chain,
            ttl_seconds=ttl_seconds,
        )
        self._require_certificate_binding(
            workflow,
            certificate,
        )
        self._replace(
            workflow,
            phase=DurableCompactionWorkflowPhase.CERTIFIED,
            certificate_id=(
                certificate.certificate_id
            ),
            certificate_digest=(
                certificate.certificate.digest
            ),
        )
        return certificate

    def authorize(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        ttl_seconds: float | None = None,
        max_delete_items: int | None = None,
        reservation_holder_id: str = "",
    ) -> SignedDurablePruningAuthorization:
        stored = self._require(
            workflow_id
        )
        workflow = stored.workflow
        self._require_reservation(
            workflow,
            reservation_holder_id=reservation_holder_id,
        )
        if (
            _PHASE_ORDER[workflow.phase]
            < _PHASE_ORDER[
                DurableCompactionWorkflowPhase.CERTIFIED
            ]
        ):
            raise DurableCompactionWorkflowError(
                "workflow must be certified before destructive authorization"
            )
        self._revalidate(
            workflow,
            retention,
            chain,
        )

        if workflow.authorization_id:
            existing = self.authorizations.get(
                workflow.authorization_id
            )
            if existing is None:
                raise DurableCompactionWorkflowManualReview(
                    "workflow references missing pruning authorization"
                )
            self._require_authorization_binding(
                workflow,
                existing,
            )
            try:
                self.authorizations.require_current(
                    existing,
                    retention,
                    chain,
                )
            except DurablePruningAuthorizationError:
                if (
                    workflow.phase
                    is not DurableCompactionWorkflowPhase.AUTHORIZED
                ):
                    raise DurableCompactionWorkflowStale(
                        "bound pruning authorization is no longer current"
                    )
            else:
                return existing

        certificate = self.certificates.get(
            workflow.certificate_id
        )
        if certificate is None:
            raise DurableCompactionWorkflowManualReview(
                "bound compaction certificate is missing"
            )
        self._require_certificate_binding(
            workflow,
            certificate,
        )
        authorization = (
            self.authorizations.issue(
                certificate,
                retention,
                chain,
                operator_id=(
                    workflow.operator_id
                ),
                ttl_seconds=ttl_seconds,
                max_delete_items=(
                    max_delete_items
                ),
            )
        )
        self._require_authorization_binding(
            workflow,
            authorization,
        )
        updated = self._replace(
            workflow,
            phase=DurableCompactionWorkflowPhase.AUTHORIZED,
            authorization_id=(
                authorization.authorization_id
            ),
            authorization_digest=(
                authorization.authorization.digest
            ),
            delete_count=(
                authorization.authorization.delete_count
            ),
        )
        if (
            updated.workflow.authorization_id
            != authorization.authorization_id
        ):
            raise DurableCompactionWorkflowError(
                "workflow authorization update lost race"
            )
        return authorization

    def _bound_authorization(
        self,
        workflow: DurableCompactionWorkflow,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        require_current: bool,
    ) -> SignedDurablePruningAuthorization:
        if not workflow.authorization_id:
            raise DurableCompactionWorkflowError(
                "workflow has no pruning authorization"
            )
        item = self.authorizations.get(
            workflow.authorization_id
        )
        if item is None:
            raise DurableCompactionWorkflowManualReview(
                "bound pruning authorization is missing"
            )
        self._require_authorization_binding(
            workflow,
            item,
        )
        if require_current:
            self.authorizations.require_current(
                item,
                retention,
                chain,
            )
        return item

    def _require_pruning_binding(
        self,
        workflow: DurableCompactionWorkflow,
        manifest: DurablePruningManifest,
        operation: DurablePruningOperation,
    ) -> None:
        if (
            manifest.chain_id
            != workflow.chain_id
            or manifest.authorization_id
            != workflow.authorization_id
            or manifest.current_sequence
            != workflow.current_sequence
            or manifest.current_root
            != workflow.current_root
            or manifest.previous_floor_sequence
            != workflow.previous_floor_sequence
            or manifest.previous_floor_root
            != workflow.previous_floor_root
            or manifest.cutoff_sequence
            != workflow.cutoff_sequence
            or manifest.cutoff_root
            != workflow.cutoff_root
            or manifest.archive_id
            != workflow.archive_id
            or manifest.archive_manifest_digest
            != workflow.archive_manifest_digest
            or operation.operation_id
            != manifest.operation_id
            or operation.authorization_id
            != workflow.authorization_id
            or operation.manifest_digest
            != manifest.digest
        ):
            raise DurableCompactionWorkflowManualReview(
                "stored pruning state differs from workflow authority"
            )
        if (
            workflow.pruning_operation_id
            and workflow.pruning_operation_id
            != operation.operation_id
        ):
            raise DurableCompactionWorkflowManualReview(
                "workflow pruning operation id differs from stored operation"
            )
        if (
            workflow.pruning_manifest_digest
            and workflow.pruning_manifest_digest
            != manifest.digest
        ):
            raise DurableCompactionWorkflowManualReview(
                "workflow pruning manifest digest differs from stored manifest"
            )

    def prepare(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        reservation_holder_id: str = "",
    ) -> DurableCompactionPrepared:
        stored = self._require(
            workflow_id
        )
        workflow = stored.workflow
        self._require_reservation(
            workflow,
            reservation_holder_id=reservation_holder_id,
        )
        if (
            _PHASE_ORDER[workflow.phase]
            < _PHASE_ORDER[
                DurableCompactionWorkflowPhase.AUTHORIZED
            ]
        ):
            raise DurableCompactionWorkflowError(
                "workflow must be authorized before manifest preparation"
            )
        if (
            workflow.phase
            is DurableCompactionWorkflowPhase.COMPLETE
        ):
            raise DurableCompactionWorkflowError(
                "complete workflow cannot be prepared again"
            )
        self._revalidate(
            workflow,
            retention,
            chain,
        )
        authorization = self._bound_authorization(
            workflow,
            retention,
            chain,
            require_current=True,
        )

        if workflow.pruning_operation_id:
            manifest = self.pruning.manifest(
                workflow.pruning_operation_id
            )
            operation = self.pruning.operation(
                workflow.pruning_operation_id
            )
            if (
                manifest is None
                or operation is None
            ):
                raise DurableCompactionWorkflowManualReview(
                    "workflow references missing pruning state"
                )
            self._require_pruning_binding(
                workflow,
                manifest,
                operation,
            )
            certificate = self.certificates.get(
                workflow.certificate_id
            )
            if certificate is None:
                raise DurableCompactionWorkflowManualReview(
                    "bound certificate is missing"
                )
            return DurableCompactionPrepared(
                stored,
                certificate,
                authorization,
                manifest,
                operation,
            )

        try:
            manifest, operation = (
                self.pruning.prepare(
                    authorization,
                    retention,
                    chain,
                )
            )
        except DurablePruningManualReview as exc:
            self._note_error(
                workflow,
                exc,
                manual_review=True,
            )
            raise DurableCompactionWorkflowManualReview(
                str(exc)
            ) from exc
        self._require_pruning_binding(
            workflow,
            manifest,
            operation,
        )
        updated = self._replace(
            workflow,
            phase=DurableCompactionWorkflowPhase.PREPARED,
            pruning_operation_id=(
                operation.operation_id
            ),
            pruning_manifest_digest=(
                manifest.digest
            ),
            pruning_phase=(
                operation.phase.value
            ),
            deleted_items=(
                operation.deleted_items
            ),
        )
        certificate = self.certificates.get(
            workflow.certificate_id
        )
        if certificate is None:
            raise DurableCompactionWorkflowManualReview(
                "bound certificate disappeared after pruning preparation"
            )
        return DurableCompactionPrepared(
            updated,
            certificate,
            authorization,
            manifest,
            operation,
        )

    def _finish_result(
        self,
        workflow: DurableCompactionWorkflow,
        result: DurablePruningResult,
    ) -> DurableCompactionExecution:
        self._require_pruning_binding(
            workflow,
            result.manifest,
            result.operation,
        )
        if result.operation.requires_manual_review:
            stored = self._replace(
                workflow,
                phase=(
                    DurableCompactionWorkflowPhase.MANUAL_REVIEW
                ),
                pruning_phase=(
                    result.operation.phase.value
                ),
                floor_id=(
                    result.floor.floor_id
                ),
                deleted_items=(
                    result.operation.deleted_items
                ),
                error_count=(
                    workflow.error_count + 1
                ),
                last_error=(
                    result.operation.last_error
                    or "pruning operation requires manual review"
                )[:2048],
                last_error_at=self._now(),
            )
            raise DurableCompactionWorkflowManualReview(
                stored.workflow.last_error
            )

        phase = (
            DurableCompactionWorkflowPhase.COMPLETE
            if result.ok
            else DurableCompactionWorkflowPhase.EXECUTING
        )
        stored = self._replace(
            workflow,
            phase=phase,
            pruning_phase=(
                result.operation.phase.value
            ),
            floor_id=result.floor.floor_id,
            deleted_items=(
                result.operation.deleted_items
            ),
        )
        if (
            result.ok
            and stored.workflow.deleted_items
            != stored.workflow.delete_count
        ):
            raise DurableCompactionWorkflowManualReview(
                "completed pruning result deleted count differs from workflow interval"
            )
        return DurableCompactionExecution(
            stored,
            result,
        )

    def execute(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        reservation_holder_id: str = "",
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ) = None,
    ) -> DurableCompactionExecution:
        stored = self._require(
            workflow_id
        )
        workflow = stored.workflow
        self._require_reservation(
            workflow,
            reservation_holder_id=reservation_holder_id,
        )
        self._require_maintenance(
            workflow,
            chain,
            maintenance_epoch,
        )
        if (
            workflow.phase
            is not DurableCompactionWorkflowPhase.PREPARED
        ):
            if (
                workflow.phase
                is DurableCompactionWorkflowPhase.EXECUTING
            ):
                return self.resume(
                    workflow_id,
                    retention,
                    chain,
                    reservation_holder_id=reservation_holder_id,
                    maintenance_epoch=maintenance_epoch,
                )
            raise DurableCompactionWorkflowError(
                "workflow must be prepared before destructive execution"
            )
        authorization = self._bound_authorization(
            workflow,
            retention,
            chain,
            require_current=True,
        )
        manifest = self.pruning.manifest(
            workflow.pruning_operation_id
        )
        operation = self.pruning.operation(
            workflow.pruning_operation_id
        )
        if manifest is None or operation is None:
            raise DurableCompactionWorkflowManualReview(
                "prepared pruning state is missing"
            )
        self._require_pruning_binding(
            workflow,
            manifest,
            operation,
        )

        executing = self._replace(
            workflow,
            phase=DurableCompactionWorkflowPhase.EXECUTING,
            pruning_phase=operation.phase.value,
            deleted_items=operation.deleted_items,
        )
        try:
            result = self.pruning.execute(
                authorization,
                retention,
                chain,
                maintenance_epoch=maintenance_epoch,
            )
        except DurablePruningManualReview as exc:
            self._note_error(
                executing.workflow,
                exc,
                manual_review=True,
            )
            raise DurableCompactionWorkflowManualReview(
                str(exc)
            ) from exc
        except Exception as exc:
            self._note_error(
                executing.workflow,
                exc,
                manual_review=False,
            )
            raise
        return self._finish_result(
            executing.workflow,
            result,
        )

    def resume(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        reservation_holder_id: str = "",
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ) = None,
    ) -> DurableCompactionExecution:
        stored = self._require(
            workflow_id
        )
        workflow = stored.workflow
        self._require_reservation(
            workflow,
            reservation_holder_id=reservation_holder_id,
        )
        self._require_maintenance(
            workflow,
            chain,
            maintenance_epoch,
        )
        if workflow.complete:
            authorization = self._bound_authorization(
                workflow,
                retention,
                chain,
                require_current=False,
            )
            result = self.pruning.resume(
                workflow.pruning_operation_id,
                authorization,
                retention,
                chain,
                maintenance_epoch=maintenance_epoch,
            )
            return DurableCompactionExecution(
                stored,
                result,
            )
        if not workflow.resumable:
            raise DurableCompactionWorkflowError(
                "workflow is not in a resumable pruning phase"
            )
        floor_sequence, floor_root = self._floor(
            chain
        )
        floor_committed = (
            floor_sequence == workflow.cutoff_sequence
            and floor_root == workflow.cutoff_root
        )
        authorization = self._bound_authorization(
            workflow,
            retention,
            chain,
            require_current=not floor_committed,
        )
        try:
            result = self.pruning.resume(
                workflow.pruning_operation_id,
                authorization,
                retention,
                chain,
                maintenance_epoch=maintenance_epoch,
            )
        except DurablePruningManualReview as exc:
            self._note_error(
                workflow,
                exc,
                manual_review=True,
            )
            raise DurableCompactionWorkflowManualReview(
                str(exc)
            ) from exc
        except Exception as exc:
            self._note_error(
                workflow,
                exc,
                manual_review=False,
            )
            raise
        return self._finish_result(
            workflow,
            result,
        )

    def inspect(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        reservation_holder_id: str = "",
    ) -> DurableCompactionWorkflowInspection:
        stored = self.current(
            workflow_id
        )
        if stored is None:
            raise DurableCompactionWorkflowError(
                "workflow is missing"
            )
        workflow = stored.workflow
        reasons: list[str] = []
        if self.reservations is not None and not workflow.complete:
            try:
                self._require_reservation(
                    workflow,
                    reservation_holder_id=reservation_holder_id,
                )
            except DurableCompactionWorkflowStale as exc:
                reasons.append(str(exc))

        head = chain.head()
        live_head_matches = (
            int(head.sequence)
            == workflow.current_sequence
            and str(head.root_hash)
            == workflow.current_root
        )
        if not live_head_matches:
            reasons.append(
                "live head differs from workflow"
            )

        readiness_current = False
        try:
            self._require_retention_binding(
                workflow,
                retention,
            )
            readiness = self.planner.inspect(
                retention,
                chain,
            )
            readiness_current = (
                readiness.ready
                and readiness.digest
                == workflow.readiness_digest
            )
            if not readiness_current:
                reasons.append(
                    "compaction readiness differs from workflow"
                )
        except Exception as exc:
            reasons.append(
                "readiness inspection failed: "
                f"{type(exc).__name__}"
            )

        certificate_current = (
            not workflow.certificate_id
        )
        if workflow.certificate_id:
            item = self.certificates.get(
                workflow.certificate_id
            )
            if item is None:
                reasons.append(
                    "bound compaction certificate is missing"
                )
                certificate_current = False
            else:
                try:
                    self._require_certificate_binding(
                        workflow,
                        item,
                    )
                    report = (
                        self.certificates.inspect(
                            item,
                            retention,
                            chain,
                        )
                    )
                    certificate_current = (
                        report.allowed
                    )
                    if not certificate_current:
                        reasons.append(
                            "bound compaction certificate is not current"
                        )
                except Exception as exc:
                    certificate_current = False
                    reasons.append(
                        "certificate inspection failed: "
                        f"{type(exc).__name__}"
                    )

        authorization_current = (
            not workflow.authorization_id
        )
        if workflow.authorization_id:
            item = self.authorizations.get(
                workflow.authorization_id
            )
            if item is None:
                authorization_current = False
                reasons.append(
                    "bound pruning authorization is missing"
                )
            else:
                try:
                    self._require_authorization_binding(
                        workflow,
                        item,
                    )
                    report = (
                        self.authorizations.inspect(
                            item,
                            retention,
                            chain,
                        )
                    )
                    authorization_current = (
                        report.allowed
                    )
                    if (
                        not authorization_current
                        and workflow.phase
                        not in {
                            DurableCompactionWorkflowPhase.EXECUTING,
                            DurableCompactionWorkflowPhase.COMPLETE,
                        }
                    ):
                        reasons.append(
                            "bound pruning authorization is not current"
                        )
                except Exception as exc:
                    authorization_current = False
                    reasons.append(
                        "authorization inspection failed: "
                        f"{type(exc).__name__}"
                    )

        pruning_state_consistent = (
            not workflow.pruning_operation_id
        )
        if workflow.pruning_operation_id:
            manifest = self.pruning.manifest(
                workflow.pruning_operation_id
            )
            operation = self.pruning.operation(
                workflow.pruning_operation_id
            )
            if manifest is None or operation is None:
                pruning_state_consistent = False
                reasons.append(
                    "bound pruning state is missing"
                )
            else:
                try:
                    self._require_pruning_binding(
                        workflow,
                        manifest,
                        operation,
                    )
                    pruning_state_consistent = True
                except Exception as exc:
                    pruning_state_consistent = False
                    reasons.append(
                        "pruning state inspection failed: "
                        f"{type(exc).__name__}"
                    )

        floor_sequence, floor_root = (
            self._floor(chain)
        )
        if workflow.phase in {
            DurableCompactionWorkflowPhase.EXECUTING,
            DurableCompactionWorkflowPhase.COMPLETE,
        }:
            hot_floor_consistent = (
                (
                    floor_sequence
                    == workflow.previous_floor_sequence
                    and floor_root
                    == workflow.previous_floor_root
                )
                or (
                    floor_sequence
                    == workflow.cutoff_sequence
                    and floor_root
                    == workflow.cutoff_root
                )
            )
        else:
            hot_floor_consistent = (
                floor_sequence
                == workflow.previous_floor_sequence
                and floor_root
                == workflow.previous_floor_root
            )
        if not hot_floor_consistent:
            reasons.append(
                "hot floor differs from workflow"
            )

        return DurableCompactionWorkflowInspection(
            stored,
            readiness_current,
            certificate_current,
            authorization_current,
            pruning_state_consistent,
            live_head_matches,
            hot_floor_consistent,
            tuple(dict.fromkeys(reasons)),
        )

    def require_current(
        self,
        workflow_id: str,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        reservation_holder_id: str = "",
    ) -> DurableCompactionWorkflowInspection:
        report = self.inspect(
            workflow_id,
            retention,
            chain,
            reservation_holder_id=reservation_holder_id,
        )
        if not report.current:
            detail = (
                report.reasons[0]
                if report.reasons
                else "durable compaction workflow is not current"
            )
            raise DurableCompactionWorkflowStale(
                detail
            )
        return report

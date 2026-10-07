"""P1 operator-control projection over durable product authority.

This module is presentation-only. Canonical operation state remains owned by
the durable PROD-02/PROD-03 projection chain. Human pause/resume/interrupt/
override state is projected only from an accepted AUTO-04 HumanControlDecision.
Cancellation is never inferred from AUTO-04; it derives only from canonical
OperationState.CANCELLED.

No function in this module executes a control action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.user_control_receipts import SQLiteHumanControlReceiptStore
from core.workspace_projection import (
    WorkspaceProjection,
    WorkspaceProjectionDecision,
)
from skeleton.agents.autonomy_control import AutonomyLevel
from skeleton.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import OperationState
from skeleton.frontier.contracts import stable_content_digest


OPERATOR_CONTROL_SCHEMA_VERSION = 1
OPERATOR_CONTROL_TASK_ID = "P1-PROD-04"
OPERATOR_CONTROL_ACCOUNTABILITY_ID = "ACC-P1-PROD-04"

_PROJECTABLE_HUMAN_ACTIONS = {
    HumanControlAction.INTERRUPT,
    HumanControlAction.PAUSE,
    HumanControlAction.RESUME,
    HumanControlAction.OVERRIDE,
}


class OperatorControlProjectionError(ValueError):
    """Projected operator-control state violates canonical authority."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperatorControlProjectionError(
            f"{field} must be non-empty"
        )
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise OperatorControlProjectionError(
            f"{field} must be normalized"
        )
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(
        char not in "0123456789abcdef" for char in text
    ):
        raise OperatorControlProjectionError(
            f"{field} must be lowercase sha256"
        )
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OperatorControlProjectionError(
            f"{field} must be a positive integer"
        )
    return value


def _actions(
    *,
    terminal: bool,
    paused: bool | None,
    interrupted: bool | None,
) -> tuple[str, ...]:
    if terminal:
        return ()
    if paused is None or interrupted is None:
        return ("cancel",)
    if paused or interrupted:
        return ("cancel", "resume")
    return ("cancel", "interrupt", "override", "pause")


@dataclass(frozen=True, slots=True)
class OperatorControlProjection:
    operation_id: str
    tenant_id: str
    canonical_state: OperationState
    terminal: bool
    cancelled: bool
    workspace_projection_digest: str
    workspace_decision_digest: str
    control_known: bool
    last_action: HumanControlAction | None
    human_control_receipt_digest: str | None
    control_version: int | None
    paused: bool | None
    interrupted: bool | None
    autonomy_level: AutonomyLevel | None
    previous_control_receipt_digest: str | None
    available_actions: tuple[str, ...]
    schema_version: int = OPERATOR_CONTROL_SCHEMA_VERSION
    task_id: str = OPERATOR_CONTROL_TASK_ID
    accountability_id: str = OPERATOR_CONTROL_ACCOUNTABILITY_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=64),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _text(self.tenant_id, "tenant_id"),
        )
        try:
            object.__setattr__(
                self,
                "canonical_state",
                OperationState(self.canonical_state),
            )
        except ValueError as exc:
            raise OperatorControlProjectionError(
                "invalid canonical_state"
            ) from exc
        for field in ("terminal", "cancelled", "control_known"):
            if not isinstance(getattr(self, field), bool):
                raise OperatorControlProjectionError(
                    f"{field} must be boolean"
                )
        object.__setattr__(
            self,
            "workspace_projection_digest",
            _sha256(
                self.workspace_projection_digest,
                "workspace_projection_digest",
            ),
        )
        object.__setattr__(
            self,
            "workspace_decision_digest",
            _sha256(
                self.workspace_decision_digest,
                "workspace_decision_digest",
            ),
        )

        derived_terminal = self.canonical_state in {
            OperationState.COMPLETED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
        if self.terminal != derived_terminal:
            raise OperatorControlProjectionError(
                "terminal must derive from canonical state"
            )
        if self.cancelled != (
            self.canonical_state is OperationState.CANCELLED
        ):
            raise OperatorControlProjectionError(
                "cancelled must derive from canonical state"
            )

        if self.control_known:
            if self.last_action is None:
                raise OperatorControlProjectionError(
                    "known control state requires last_action"
                )
            try:
                action = HumanControlAction(self.last_action)
            except ValueError as exc:
                raise OperatorControlProjectionError(
                    "invalid last_action"
                ) from exc
            if action not in _PROJECTABLE_HUMAN_ACTIONS:
                raise OperatorControlProjectionError(
                    "last_action is not a projectable operator control"
                )
            object.__setattr__(self, "last_action", action)
            if self.human_control_receipt_digest is None:
                raise OperatorControlProjectionError(
                    "known control state requires receipt digest"
                )
            object.__setattr__(
                self,
                "human_control_receipt_digest",
                _sha256(
                    self.human_control_receipt_digest,
                    "human_control_receipt_digest",
                ),
            )
            if self.control_version is None:
                raise OperatorControlProjectionError(
                    "known control state requires control_version"
                )
            object.__setattr__(
                self,
                "control_version",
                _positive_int(
                    self.control_version,
                    "control_version",
                ),
            )
            if not isinstance(self.paused, bool):
                raise OperatorControlProjectionError(
                    "known control state requires paused boolean"
                )
            if not isinstance(self.interrupted, bool):
                raise OperatorControlProjectionError(
                    "known control state requires interrupted boolean"
                )
            if self.autonomy_level is None:
                raise OperatorControlProjectionError(
                    "known control state requires autonomy_level"
                )
            try:
                object.__setattr__(
                    self,
                    "autonomy_level",
                    AutonomyLevel(self.autonomy_level),
                )
            except ValueError as exc:
                raise OperatorControlProjectionError(
                    "invalid autonomy_level"
                ) from exc
            if self.previous_control_receipt_digest is not None:
                object.__setattr__(
                    self,
                    "previous_control_receipt_digest",
                    _sha256(
                        self.previous_control_receipt_digest,
                        "previous_control_receipt_digest",
                    ),
                )
        else:
            if any(
                value is not None
                for value in (
                    self.last_action,
                    self.human_control_receipt_digest,
                    self.control_version,
                    self.paused,
                    self.interrupted,
                    self.autonomy_level,
                    self.previous_control_receipt_digest,
                )
            ):
                raise OperatorControlProjectionError(
                    "unknown control state cannot invent control fields"
                )

        expected_actions = _actions(
            terminal=self.terminal,
            paused=self.paused,
            interrupted=self.interrupted,
        )
        if self.available_actions != expected_actions:
            raise OperatorControlProjectionError(
                "available_actions must derive from canonical control state"
            )

        if self.schema_version != OPERATOR_CONTROL_SCHEMA_VERSION:
            raise OperatorControlProjectionError(
                "unsupported operator-control schema"
            )
        if self.task_id != OPERATOR_CONTROL_TASK_ID:
            raise OperatorControlProjectionError("task_id drift")
        if self.accountability_id != OPERATOR_CONTROL_ACCOUNTABILITY_ID:
            raise OperatorControlProjectionError(
                "accountability_id drift"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "canonical_state": self.canonical_state.value,
            "terminal": self.terminal,
            "cancelled": self.cancelled,
            "workspace_projection_digest": self.workspace_projection_digest,
            "workspace_decision_digest": self.workspace_decision_digest,
            "control_known": self.control_known,
            "last_action": (
                None
                if self.last_action is None
                else self.last_action.value
            ),
            "human_control_receipt_digest": (
                self.human_control_receipt_digest
            ),
            "control_version": self.control_version,
            "paused": self.paused,
            "interrupted": self.interrupted,
            "autonomy_level": (
                None
                if self.autonomy_level is None
                else int(self.autonomy_level)
            ),
            "previous_control_receipt_digest": (
                self.previous_control_receipt_digest
            ),
            "available_actions": list(self.available_actions),
            "canonical_operation_authority": (
                "durable-workspace-projection"
            ),
            "human_control_authority": (
                "p1-auto-04-human-control"
                if self.control_known
                else None
            ),
            "production_authority": False,
        }

    @property
    def projection_digest(self) -> str:
        return stable_content_digest(self.payload())


@dataclass(frozen=True, slots=True)
class OperatorControlProjectionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    operation_id: str
    tenant_id: str
    projection_digest: str
    workspace_projection_digest: str
    workspace_decision_digest: str
    human_control_receipt_digest: str | None
    task_id: str = OPERATOR_CONTROL_TASK_ID
    accountability_id: str = OPERATOR_CONTROL_ACCOUNTABILITY_ID
    schema_version: int = OPERATOR_CONTROL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise OperatorControlProjectionError(
                "accepted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise OperatorControlProjectionError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=64),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _text(self.tenant_id, "tenant_id"),
        )
        for field in (
            "projection_digest",
            "workspace_projection_digest",
            "workspace_decision_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.human_control_receipt_digest is not None:
            object.__setattr__(
                self,
                "human_control_receipt_digest",
                _sha256(
                    self.human_control_receipt_digest,
                    "human_control_receipt_digest",
                ),
            )
        if self.task_id != OPERATOR_CONTROL_TASK_ID:
            raise OperatorControlProjectionError("task_id drift")
        if self.accountability_id != OPERATOR_CONTROL_ACCOUNTABILITY_ID:
            raise OperatorControlProjectionError(
                "accountability_id drift"
            )
        if self.schema_version != OPERATOR_CONTROL_SCHEMA_VERSION:
            raise OperatorControlProjectionError(
                "unsupported decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "projection_digest": self.projection_digest,
            "workspace_projection_digest": self.workspace_projection_digest,
            "workspace_decision_digest": self.workspace_decision_digest,
            "human_control_receipt_digest": (
                self.human_control_receipt_digest
            ),
        }

    @property
    def decision_digest(self) -> str:
        return stable_content_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise OperatorControlProjectionError(
                "rejected operator-control projection cannot become evidence"
            )
        return EvidenceRef(
            source=(
                f"p1:prod-04:operator-control:{self.operation_id}"
            ),
            digest=self.decision_digest,
            category="operator_control_projection",
        )


def build_operator_control_projection(
    *,
    workspace: WorkspaceProjection,
    workspace_decision: WorkspaceProjectionDecision,
    human_control: HumanControlDecision | None = None,
) -> OperatorControlProjection:
    """Build a UI control view from accepted upstream authority only."""

    if not isinstance(workspace, WorkspaceProjection):
        raise TypeError("workspace must be WorkspaceProjection")
    if not isinstance(
        workspace_decision,
        WorkspaceProjectionDecision,
    ):
        raise TypeError(
            "workspace_decision must be WorkspaceProjectionDecision"
        )
    if not workspace_decision.accepted:
        raise OperatorControlProjectionError(
            "workspace projection decision must be accepted"
        )
    if (
        workspace_decision.workspace_projection_digest
        != workspace.projection_digest
    ):
        raise OperatorControlProjectionError(
            "workspace decision digest mismatch"
        )
    if workspace_decision.operation_id != workspace.operation_id:
        raise OperatorControlProjectionError(
            "workspace operation identity mismatch"
        )
    if workspace_decision.tenant_id != workspace.tenant_id:
        raise OperatorControlProjectionError(
            "workspace tenant identity mismatch"
        )

    control_known = human_control is not None
    if human_control is not None:
        if not isinstance(human_control, HumanControlDecision):
            raise TypeError(
                "human_control must be HumanControlDecision"
            )
        if not human_control.accepted:
            raise OperatorControlProjectionError(
                "human-control receipt must be accepted"
            )
        if human_control.operation_id != workspace.operation_id:
            raise OperatorControlProjectionError(
                "human-control operation identity mismatch"
            )
        if human_control.action not in _PROJECTABLE_HUMAN_ACTIONS:
            raise OperatorControlProjectionError(
                "human-control action is not projectable"
            )

    return OperatorControlProjection(
        operation_id=workspace.operation_id,
        tenant_id=workspace.tenant_id,
        canonical_state=workspace.canonical_state,
        terminal=workspace.terminal,
        cancelled=(
            workspace.canonical_state is OperationState.CANCELLED
        ),
        workspace_projection_digest=workspace.projection_digest,
        workspace_decision_digest=workspace_decision.decision_digest,
        control_known=control_known,
        last_action=(
            None if human_control is None else human_control.action
        ),
        human_control_receipt_digest=(
            None
            if human_control is None
            else human_control.receipt_digest
        ),
        control_version=(
            None if human_control is None else human_control.next_version
        ),
        paused=(
            None if human_control is None else human_control.next_paused
        ),
        interrupted=(
            None
            if human_control is None
            else human_control.next_interrupted
        ),
        autonomy_level=(
            None if human_control is None else human_control.next_level
        ),
        previous_control_receipt_digest=(
            None
            if human_control is None
            else human_control.previous_receipt_digest
        ),
        available_actions=_actions(
            terminal=workspace.terminal,
            paused=(
                None if human_control is None else human_control.next_paused
            ),
            interrupted=(
                None
                if human_control is None
                else human_control.next_interrupted
            ),
        ),
    )


def verify_operator_control_projection(
    projection: OperatorControlProjection,
    workspace: WorkspaceProjection,
    workspace_decision: WorkspaceProjectionDecision,
    human_control: HumanControlDecision | None = None,
) -> OperatorControlProjectionDecision:
    """Verify a cached UI control view against current canonical authorities."""

    if not isinstance(projection, OperatorControlProjection):
        raise TypeError(
            "projection must be OperatorControlProjection"
        )
    if not isinstance(workspace, WorkspaceProjection):
        raise TypeError("workspace must be WorkspaceProjection")
    if not isinstance(
        workspace_decision,
        WorkspaceProjectionDecision,
    ):
        raise TypeError(
            "workspace_decision must be WorkspaceProjectionDecision"
        )
    if human_control is not None and not isinstance(
        human_control,
        HumanControlDecision,
    ):
        raise TypeError(
            "human_control must be HumanControlDecision"
        )

    reasons: list[str] = []
    if not workspace_decision.accepted:
        reasons.append("workspace-decision-rejected")
    if projection.operation_id != workspace.operation_id:
        reasons.append("operation-id-mismatch")
    if projection.tenant_id != workspace.tenant_id:
        reasons.append("tenant-id-mismatch")
    if projection.canonical_state is not workspace.canonical_state:
        reasons.append("canonical-state-mismatch")
    if projection.terminal != workspace.terminal:
        reasons.append("terminal-state-mismatch")
    if projection.cancelled != (
        workspace.canonical_state is OperationState.CANCELLED
    ):
        reasons.append("cancelled-state-mismatch")
    if (
        projection.workspace_projection_digest
        != workspace.projection_digest
    ):
        reasons.append("workspace-projection-digest-mismatch")
    if (
        projection.workspace_decision_digest
        != workspace_decision.decision_digest
    ):
        reasons.append("workspace-decision-digest-mismatch")

    if human_control is None:
        if projection.control_known:
            reasons.append("control-receipt-missing")
        if projection.human_control_receipt_digest is not None:
            reasons.append("unexpected-control-receipt-digest")
    else:
        if not human_control.accepted:
            reasons.append("human-control-rejected")
        if human_control.operation_id != workspace.operation_id:
            reasons.append("human-control-operation-mismatch")
        if human_control.action not in _PROJECTABLE_HUMAN_ACTIONS:
            reasons.append("human-control-action-not-projectable")
        if not projection.control_known:
            reasons.append("control-state-not-known")
        if (
            projection.human_control_receipt_digest
            != human_control.receipt_digest
        ):
            reasons.append("human-control-receipt-digest-mismatch")
        if projection.control_version != human_control.next_version:
            reasons.append("control-version-mismatch")
        if projection.paused != human_control.next_paused:
            reasons.append("paused-state-mismatch")
        if projection.interrupted != human_control.next_interrupted:
            reasons.append("interrupted-state-mismatch")
        if projection.autonomy_level is not human_control.next_level:
            reasons.append("autonomy-level-mismatch")
        if (
            projection.previous_control_receipt_digest
            != human_control.previous_receipt_digest
        ):
            reasons.append("previous-control-receipt-mismatch")

    expected_actions = _actions(
        terminal=workspace.terminal,
        paused=projection.paused,
        interrupted=projection.interrupted,
    )
    if projection.available_actions != expected_actions:
        reasons.append("available-actions-mismatch")
    if workspace.terminal and projection.available_actions:
        reasons.append("terminal-operation-exposes-controls")

    normalized = tuple(sorted(set(reasons)))
    return OperatorControlProjectionDecision(
        accepted=not normalized,
        reasons=normalized,
        operation_id=workspace.operation_id,
        tenant_id=workspace.tenant_id,
        projection_digest=projection.projection_digest,
        workspace_projection_digest=workspace.projection_digest,
        workspace_decision_digest=workspace_decision.decision_digest,
        human_control_receipt_digest=(
            None
            if human_control is None
            else human_control.receipt_digest
        ),
    )



def build_operator_control_projection_from_store(
    *,
    store: SQLiteHumanControlReceiptStore,
    tenant_id: str,
    execution_id: str,
    workspace: WorkspaceProjection,
    workspace_decision: WorkspaceProjectionDecision,
) -> OperatorControlProjection:
    """Rebuild operator UI state from restart-safe accepted control history."""

    if not isinstance(store, SQLiteHumanControlReceiptStore):
        raise TypeError("store must be SQLiteHumanControlReceiptStore")
    chain = store.chain(
        tenant_id=tenant_id,
        operation_id=workspace.operation_id,
        execution_id=execution_id,
    )
    latest = None if not chain else chain[-1]
    return build_operator_control_projection(
        workspace=workspace,
        workspace_decision=workspace_decision,
        human_control=latest,
    )


def verify_operator_control_projection_from_store(
    projection: OperatorControlProjection,
    *,
    store: SQLiteHumanControlReceiptStore,
    tenant_id: str,
    execution_id: str,
    workspace: WorkspaceProjection,
    workspace_decision: WorkspaceProjectionDecision,
) -> OperatorControlProjectionDecision:
    """Verify cached operator UI state against durable receipt + workspace authority."""

    if not isinstance(store, SQLiteHumanControlReceiptStore):
        raise TypeError("store must be SQLiteHumanControlReceiptStore")
    chain = store.chain(
        tenant_id=tenant_id,
        operation_id=workspace.operation_id,
        execution_id=execution_id,
    )
    latest = None if not chain else chain[-1]
    return verify_operator_control_projection(
        projection,
        workspace,
        workspace_decision,
        latest,
    )


__all__ = [
    "OPERATOR_CONTROL_ACCOUNTABILITY_ID",
    "OPERATOR_CONTROL_SCHEMA_VERSION",
    "OPERATOR_CONTROL_TASK_ID",
    "OperatorControlProjection",
    "OperatorControlProjectionDecision",
    "OperatorControlProjectionError",
    "build_operator_control_projection",
    "build_operator_control_projection_from_store",
    "verify_operator_control_projection",
    "verify_operator_control_projection_from_store",
]

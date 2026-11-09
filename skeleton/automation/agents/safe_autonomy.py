"""P1 terminal safe-autonomy qualification bundle.

This module is a non-executing join contract. It does not grant authority,
execute tools, or mutate lifecycle state. It proves that the accepted AUTO-01
through AUTO-05 decisions describe one cryptographically joined action and
authority chain before they may become aggregate P1-AUTO-06 evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from skeleton.automation.agents.autonomy_control import AutonomyTransitionDecision
from skeleton.automation.agents.blast_radius import BlastRadiusDecision
from skeleton.automation.agents.delegation_qualification import AgentDelegationDecision
from skeleton.automation.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
    HumanControlError,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.skills.privileged_transaction import PrivilegedToolTransactionDecision


SAFE_AUTONOMY_SCHEMA_VERSION = 1
SAFE_AUTONOMY_TASK_ID = "P1-AUTO-06"
SAFE_AUTONOMY_ACCOUNTABILITY_ID = "ACC-P1-AUTO-06"


class SafeAutonomyError(ValueError):
    """Safe-autonomy bundle evidence is malformed."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SafeAutonomyError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise SafeAutonomyError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise SafeAutonomyError(f"{field} must be lowercase sha256")
    return text


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeAutonomyError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SafeAutonomyError(f"{field} must be finite numeric")
    return result


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SafeAutonomyError("safe-autonomy payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SafeAutonomyDecision:
    accepted: bool
    reasons: tuple[str, ...]
    operation_id: str
    execution_id: str
    agent_id: str
    action_digest: str
    authority_digest: str
    tool_transaction_digest: str
    delegation_digest: str
    autonomy_transition_digest: str
    human_control_receipt_digest: str
    blast_radius_digest: str
    authorization_digest: str
    observed_at: float
    task_id: str = SAFE_AUTONOMY_TASK_ID
    accountability_id: str = SAFE_AUTONOMY_ACCOUNTABILITY_ID
    schema_version: int = SAFE_AUTONOMY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise SafeAutonomyError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise SafeAutonomyError("reasons must contain non-empty strings")
        for field in ("operation_id", "execution_id", "agent_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in (
            "action_digest",
            "authority_digest",
            "tool_transaction_digest",
            "delegation_digest",
            "autonomy_transition_digest",
            "human_control_receipt_digest",
            "blast_radius_digest",
            "authorization_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        observed = _finite(self.observed_at, "observed_at")
        if observed <= 0:
            raise SafeAutonomyError("observed_at must be positive")
        object.__setattr__(self, "observed_at", observed)
        if self.task_id != SAFE_AUTONOMY_TASK_ID:
            raise SafeAutonomyError("task_id drift")
        if self.accountability_id != SAFE_AUTONOMY_ACCOUNTABILITY_ID:
            raise SafeAutonomyError("accountability_id drift")
        if self.schema_version != SAFE_AUTONOMY_SCHEMA_VERSION:
            raise SafeAutonomyError("unsupported schema version")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "action_digest": self.action_digest,
            "authority_digest": self.authority_digest,
            "tool_transaction_digest": self.tool_transaction_digest,
            "delegation_digest": self.delegation_digest,
            "autonomy_transition_digest": self.autonomy_transition_digest,
            "human_control_receipt_digest": self.human_control_receipt_digest,
            "blast_radius_digest": self.blast_radius_digest,
            "authorization_digest": self.authorization_digest,
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "observed_at": self.observed_at,
        }

    @property
    def chain_digest(self) -> str:
        return _canonical_digest(
            {
                "action_digest": self.action_digest,
                "authority_digest": self.authority_digest,
                "tool_transaction_digest": self.tool_transaction_digest,
                "delegation_digest": self.delegation_digest,
                "autonomy_transition_digest": self.autonomy_transition_digest,
                "human_control_receipt_digest": self.human_control_receipt_digest,
                "blast_radius_digest": self.blast_radius_digest,
                "authorization_digest": self.authorization_digest,
            }
        )

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(
            {
                **self.identity_payload(),
                "chain_digest": self.chain_digest,
            }
        )

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-06:safe-autonomy-bundle",
    ) -> EvidenceRef:
        if not self.accepted:
            raise SafeAutonomyError(
                "rejected safe-autonomy bundle cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="safe_autonomy_qualification",
        )


def qualify_safe_autonomy(
    *,
    tool_transaction: PrivilegedToolTransactionDecision,
    delegation: AgentDelegationDecision,
    autonomy_transition: AutonomyTransitionDecision,
    human_control: HumanControlDecision,
    blast_radius: BlastRadiusDecision,
    observed_at: float,
) -> SafeAutonomyDecision:
    """Join accepted AUTO-01..AUTO-05 decisions into one fail-closed bundle."""

    if not isinstance(tool_transaction, PrivilegedToolTransactionDecision):
        raise TypeError("tool_transaction must be PrivilegedToolTransactionDecision")
    if not isinstance(delegation, AgentDelegationDecision):
        raise TypeError("delegation must be AgentDelegationDecision")
    if not isinstance(autonomy_transition, AutonomyTransitionDecision):
        raise TypeError("autonomy_transition must be AutonomyTransitionDecision")
    if not isinstance(human_control, HumanControlDecision):
        raise TypeError("human_control must be HumanControlDecision")
    if not isinstance(blast_radius, BlastRadiusDecision):
        raise TypeError("blast_radius must be BlastRadiusDecision")

    now = _finite(observed_at, "observed_at")
    if now <= 0:
        raise SafeAutonomyError("observed_at must be positive")

    reasons: list[str] = []

    if not tool_transaction.accepted:
        reasons.append("tool-transaction-rejected")
    if not tool_transaction.receipt_persisted:
        reasons.append("tool-receipt-not-persisted")
    if not delegation.accepted:
        reasons.append("delegation-rejected")
    if not autonomy_transition.accepted:
        reasons.append("autonomy-transition-rejected")
    if not human_control.accepted:
        reasons.append("human-control-rejected")
    if not blast_radius.accepted:
        reasons.append("blast-radius-rejected")

    authority_digest = delegation.decision_digest
    action_digest = tool_transaction.request_digest

    if autonomy_transition.delegation_digest != authority_digest:
        reasons.append("autonomy-delegation-chain-mismatch")
    if human_control.authority_digest != authority_digest:
        reasons.append("human-authority-chain-mismatch")
    if blast_radius.authority_digest != authority_digest:
        reasons.append("blast-authority-chain-mismatch")

    if human_control.action is not HumanControlAction.APPROVE:
        reasons.append("human-control-not-approval")
    if human_control.arguments_digest != action_digest:
        reasons.append("human-action-chain-mismatch")
    if blast_radius.action_digest != action_digest:
        reasons.append("blast-action-chain-mismatch")

    if human_control.operation_id != blast_radius.operation_id:
        reasons.append("operation-chain-mismatch")
    if human_control.execution_id != blast_radius.execution_id:
        reasons.append("execution-chain-mismatch")
    if human_control.agent_id != blast_radius.agent_id:
        reasons.append("agent-chain-mismatch")

    if blast_radius.human_receipt_digest is None:
        reasons.append("blast-human-receipt-missing")
    elif blast_radius.human_receipt_digest != human_control.receipt_digest:
        reasons.append("blast-human-receipt-mismatch")

    authorization_digest = "0" * 64
    if human_control.accepted and human_control.action is HumanControlAction.APPROVE:
        try:
            authorization = human_control.accepted_autonomy_authorization()
        except HumanControlError:
            reasons.append("human-authorization-materialization-failed")
        else:
            authorization_digest = authorization.digest
            if autonomy_transition.authorization_digest is None:
                reasons.append("autonomy-authorization-missing")
            elif autonomy_transition.authorization_digest != authorization_digest:
                reasons.append("autonomy-authorization-chain-mismatch")
    else:
        reasons.append("human-authorization-unavailable")

    if now < human_control.observed_at:
        reasons.append("human-control-not-yet-valid")
    if now >= human_control.expires_at:
        reasons.append("human-control-expired")

    normalized = tuple(sorted(set(reasons)))
    return SafeAutonomyDecision(
        accepted=not normalized,
        reasons=normalized,
        operation_id=blast_radius.operation_id,
        execution_id=blast_radius.execution_id,
        agent_id=blast_radius.agent_id,
        action_digest=action_digest,
        authority_digest=authority_digest,
        tool_transaction_digest=tool_transaction.decision_digest,
        delegation_digest=delegation.decision_digest,
        autonomy_transition_digest=autonomy_transition.decision_digest,
        human_control_receipt_digest=human_control.receipt_digest,
        blast_radius_digest=blast_radius.decision_digest,
        authorization_digest=authorization_digest,
        observed_at=now,
    )


__all__ = [
    "SAFE_AUTONOMY_ACCOUNTABILITY_ID",
    "SAFE_AUTONOMY_SCHEMA_VERSION",
    "SAFE_AUTONOMY_TASK_ID",
    "SafeAutonomyDecision",
    "SafeAutonomyError",
    "qualify_safe_autonomy",
]

"""Qualification contract for canonical privileged tool transactions.

The tool runtime remains the execution authority. This module does not execute
tools, grant approval, or mutate durable state. It joins the canonical manifest,
request, execution receipt, sandbox observation, and persistence evidence into a
single fail-closed qualification decision for P1-AUTO-01.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.shells.isolation import (
    IsolationInspector,
    IsolationLevel,
    IsolationObservation,
    IsolationRequirement,
)
from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
    ToolSideEffectClass,
    approval_ref_for_request,
)


AUTO_TOOL_TRANSACTION_SCHEMA_VERSION = 1
AUTO_TOOL_TRANSACTION_TASK_ID = "P1-AUTO-01"
AUTO_TOOL_TRANSACTION_ACCOUNTABILITY_ID = "ACC-P1-AUTO-01"


class PrivilegedToolTransactionError(ValueError):
    """Privileged transaction evidence is malformed."""


def _canonical_digest(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_privileged(manifest: ToolManifest) -> bool:
    return manifest.authority_class in {
        ToolAuthorityClass.WRITE,
        ToolAuthorityClass.DESTRUCTIVE,
        ToolAuthorityClass.EXTERNAL_COMMIT,
        ToolAuthorityClass.PRIVILEGED,
    } or manifest.side_effect_class is not ToolSideEffectClass.NONE


@dataclass(frozen=True, slots=True)
class PrivilegedToolTransactionDecision:
    """Immutable qualification result over one canonical tool transaction."""

    accepted: bool
    reasons: tuple[str, ...]
    manifest_digest: str
    request_digest: str
    receipt_digest: str
    isolation_requirement_digest: str
    isolation_observation_digest: str
    receipt_persisted: bool
    task_id: str = AUTO_TOOL_TRANSACTION_TASK_ID
    accountability_id: str = AUTO_TOOL_TRANSACTION_ACCOUNTABILITY_ID
    schema_version: int = AUTO_TOOL_TRANSACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise PrivilegedToolTransactionError("accepted must be boolean")
        if not isinstance(self.receipt_persisted, bool):
            raise PrivilegedToolTransactionError(
                "receipt_persisted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise PrivilegedToolTransactionError(
                "reasons must be non-empty strings"
            )
        for field in (
            "manifest_digest",
            "request_digest",
            "receipt_digest",
            "isolation_requirement_digest",
            "isolation_observation_digest",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise PrivilegedToolTransactionError(
                    f"{field} must be lowercase sha256"
                )
        if self.task_id != AUTO_TOOL_TRANSACTION_TASK_ID:
            raise PrivilegedToolTransactionError("task_id drift")
        if self.accountability_id != AUTO_TOOL_TRANSACTION_ACCOUNTABILITY_ID:
            raise PrivilegedToolTransactionError("accountability_id drift")
        if self.schema_version != AUTO_TOOL_TRANSACTION_SCHEMA_VERSION:
            raise PrivilegedToolTransactionError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "manifest_digest": self.manifest_digest,
            "request_digest": self.request_digest,
            "receipt_digest": self.receipt_digest,
            "isolation_requirement_digest": self.isolation_requirement_digest,
            "isolation_observation_digest": self.isolation_observation_digest,
            "receipt_persisted": self.receipt_persisted,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-01:privileged-tool-transaction",
    ) -> EvidenceRef:
        if not self.accepted:
            raise PrivilegedToolTransactionError(
                "rejected transaction cannot become promotion evidence"
            )
        if not isinstance(source, str) or not source.strip():
            raise PrivilegedToolTransactionError("source must be non-empty")
        return EvidenceRef(
            source=source.strip(),
            digest=self.decision_digest,
            category="privileged_tool_transaction",
        )


def qualify_privileged_tool_transaction(
    *,
    manifest: ToolManifest,
    request: ToolExecutionRequest,
    receipt: ToolExecutionReceipt,
    isolation_requirement: IsolationRequirement,
    isolation_observation: IsolationObservation,
    receipt_persisted: bool,
) -> PrivilegedToolTransactionDecision:
    """Join canonical execution evidence into one fail-closed decision."""

    if not isinstance(manifest, ToolManifest):
        raise TypeError("manifest must be ToolManifest")
    if not isinstance(request, ToolExecutionRequest):
        raise TypeError("request must be ToolExecutionRequest")
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    if not isinstance(isolation_requirement, IsolationRequirement):
        raise TypeError("isolation_requirement must be IsolationRequirement")
    if not isinstance(isolation_observation, IsolationObservation):
        raise TypeError("isolation_observation must be IsolationObservation")
    if not isinstance(receipt_persisted, bool):
        raise TypeError("receipt_persisted must be boolean")

    reasons: list[str] = []
    privileged = _is_privileged(manifest)

    if not manifest.enabled:
        reasons.append("manifest-disabled")
    if manifest.tool_id != request.tool_id:
        reasons.append("manifest-request-tool-mismatch")

    request_fields = (
        ("request_id", request.request_id, receipt.request_id),
        ("operation_id", request.operation_id, receipt.operation_id),
        ("tenant_id", request.tenant_id, receipt.tenant_id),
        ("tool_id", request.tool_id, receipt.tool_id),
        ("idempotency_key", request.idempotency_key, receipt.idempotency_key),
        ("arguments_digest", request.arguments_digest, receipt.arguments_digest),
        ("execution_id", request.execution_id, receipt.execution_id),
        ("turn_id", request.turn_id, receipt.turn_id),
        ("call_id", request.call_id, receipt.call_id),
        ("data_class", request.data_class, receipt.data_class),
        ("transfer_purpose", request.transfer_purpose, receipt.transfer_purpose),
    )
    for field, expected, actual in request_fields:
        if expected != actual:
            reasons.append(f"request-receipt-{field}-mismatch")

    if receipt.status is not ToolExecutionStatus.SUCCEEDED:
        reasons.append("execution-not-successful")
    if receipt.error_code is not None:
        reasons.append("successful-transaction-carries-error")

    if receipt.governance_decision_ref is None:
        reasons.append("governance-decision-missing")

    approval_required = (
        manifest.approval_required
        or manifest.approval_policy
        in {ToolApprovalPolicy.ALWAYS, ToolApprovalPolicy.OPERATOR_ONLY}
    )
    if approval_required:
        expected_approval = approval_ref_for_request(request)
        if request.approval_ref is None:
            reasons.append("approval-missing")
        elif request.approval_ref != expected_approval:
            reasons.append("approval-request-binding-mismatch")
        if receipt.approval_ref != request.approval_ref:
            reasons.append("approval-receipt-binding-mismatch")

    if privileged and manifest.idempotency_mode is ToolIdempotencyMode.NOT_REQUIRED:
        reasons.append("privileged-idempotency-policy-missing")
    if privileged and not request.idempotency_key:
        reasons.append("idempotency-key-missing")

    if privileged and receipt.metered_tool_calls != 1:
        reasons.append("admission-metering-invalid")
    if not privileged and receipt.metered_tool_calls not in {0, 1}:
        reasons.append("admission-metering-invalid")

    isolation = IsolationInspector().inspect(
        isolation_requirement,
        isolation_observation,
    )
    if not isolation.allowed:
        reasons.extend(
            f"sandbox:{reason}"
            for reason in isolation.reasons
        )
    if privileged and isolation_requirement.level is not IsolationLevel.SANDBOXED:
        reasons.append("privileged-transaction-requires-sandboxed-level")

    if manifest.network_policy == "none" and isolation_observation.network_enabled:
        reasons.append("network-policy-bypass")

    if privileged and not receipt_persisted:
        reasons.append("durable-receipt-missing")

    if privileged and not receipt.postcondition_verified:
        reasons.append("postcondition-not-verified")

    manifest_digest = _canonical_digest(manifest.as_dict())
    request_digest = _canonical_digest(
        {
            "schema_version": request.schema_version,
            "request_id": request.request_id,
            "operation_id": request.operation_id,
            "execution_id": request.execution_id,
            "turn_id": request.turn_id,
            "call_id": request.call_id,
            "tenant_id": request.tenant_id,
            "tool_id": request.tool_id,
            "idempotency_key": request.idempotency_key,
            "arguments_digest": request.arguments_digest,
            "requested_at": request.requested_at.isoformat(),
            "approval_ref": request.approval_ref,
            "delegated_authority_ref": request.delegated_authority_ref,
            "data_class": request.data_class,
            "transfer_purpose": request.transfer_purpose,
        }
    )
    receipt_digest = _canonical_digest(receipt.as_dict())
    requirement_digest = _canonical_digest(isolation_requirement.to_dict())
    observation_digest = _canonical_digest(
        {
            "private_tmp": isolation_observation.private_tmp,
            "clean_environment": isolation_observation.clean_environment,
            "readonly_source": isolation_observation.readonly_source,
            "network_enabled": isolation_observation.network_enabled,
            "home_visible": isolation_observation.home_visible,
            "write_roots": list(isolation_observation.write_roots),
        }
    )

    return PrivilegedToolTransactionDecision(
        accepted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        manifest_digest=manifest_digest,
        request_digest=request_digest,
        receipt_digest=receipt_digest,
        isolation_requirement_digest=requirement_digest,
        isolation_observation_digest=observation_digest,
        receipt_persisted=receipt_persisted,
    )


__all__ = [
    "AUTO_TOOL_TRANSACTION_ACCOUNTABILITY_ID",
    "AUTO_TOOL_TRANSACTION_SCHEMA_VERSION",
    "AUTO_TOOL_TRANSACTION_TASK_ID",
    "PrivilegedToolTransactionDecision",
    "PrivilegedToolTransactionError",
    "qualify_privileged_tool_transaction",
]

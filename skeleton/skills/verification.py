"""Tool-receipt to canonical postcondition observation adapter."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.verification import (
    PostconditionObservation,
    PostconditionSpec,
)
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)


class ToolPostconditionError(ValueError):
    """A tool receipt cannot support the requested postcondition observation."""


def observe_tool_postcondition(
    spec: PostconditionSpec,
    receipt: ToolExecutionReceipt,
    *,
    passed: bool,
    observed_at: datetime,
    evidence_ids: tuple[str, ...] = (),
    result_ref: str | None = None,
) -> PostconditionObservation:
    """Bind an explicit postcondition evaluation to one canonical tool receipt.

    Tool execution success is not automatically the domain postcondition. The
    caller must provide the evaluated passed value. A failed or denied receipt
    can never be converted into a passing postcondition.
    """

    if not isinstance(spec, PostconditionSpec):
        raise TypeError("spec must be PostconditionSpec")
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    if not isinstance(passed, bool):
        raise ToolPostconditionError("passed must be boolean")
    if spec.operation_id != receipt.operation_id:
        raise ToolPostconditionError("tool receipt operation mismatch")
    if spec.tenant_id != receipt.tenant_id:
        raise ToolPostconditionError("tool receipt tenant mismatch")
    if passed and receipt.status is not ToolExecutionStatus.SUCCEEDED:
        raise ToolPostconditionError(
            "failed or denied tool execution cannot satisfy postcondition"
        )

    durable_ref = (
        result_ref
        or receipt.result_ref
        or "tool-receipt:" + receipt.receipt_id
    )
    material = "|".join(
        (
            spec.postcondition_id,
            receipt.receipt_id,
            "pass" if passed else "fail",
            ",".join(sorted(evidence_ids)),
            durable_ref,
        )
    )
    observation_id = str(
        uuid5(
            NAMESPACE_URL,
            "tool-postcondition:" + material,
        )
    )
    return PostconditionObservation(
        observation_id=observation_id,
        postcondition_id=spec.postcondition_id,
        operation_id=spec.operation_id,
        tenant_id=spec.tenant_id,
        observed_at=observed_at,
        passed=passed,
        evidence_ids=evidence_ids,
        result_ref=durable_ref,
    )


__all__ = [
    "ToolPostconditionError",
    "observe_tool_postcondition",
]

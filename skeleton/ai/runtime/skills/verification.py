"""Tool receipt and postcondition adapters for canonical verification."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from uuid import uuid4

from skeleton.contracts.verification import (
    EvidenceKind,
    EvidenceRelation,
    PostconditionState,
    ProvenanceOrigin,
    VerificationClaim,
    VerificationEvidence,
    VerificationPostcondition,
)
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)


def _receipt_digest(receipt: ToolExecutionReceipt) -> str:
    raw = json.dumps(
        receipt.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def tool_receipt_verification_evidence(
    claim: VerificationClaim,
    receipt: ToolExecutionReceipt,
    *,
    evidence_id: str | None = None,
) -> VerificationEvidence:
    """Record tool execution lineage without pretending execution proves outcome."""

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    if receipt.tenant_id != claim.tenant_id:
        raise ValueError("tool receipt tenant mismatch")
    if claim.operation_id is not None and receipt.operation_id != claim.operation_id:
        raise ValueError("tool receipt operation mismatch")
    return VerificationEvidence(
        evidence_id=evidence_id or str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.TOOL_RECEIPT,
        origin_type=ProvenanceOrigin.TOOL,
        source_id=receipt.receipt_id,
        origin_id="tool:" + receipt.tool_id,
        content_digest=_receipt_digest(receipt),
        observed_at=receipt.finished_at,
        locator="tool-receipt:" + receipt.receipt_id,
        provenance_refs=(
            "tool-request:" + receipt.request_id,
            "tool-idempotency:" + receipt.idempotency_key,
            "tool-arguments:" + receipt.arguments_digest,
        ),
        bound_claim_ids=(claim.claim_id,),
        relation=EvidenceRelation.CONTEXT,
        data_class=claim.data_class,
    )


def tool_postcondition_verification_records(
    claim: VerificationClaim,
    receipt: ToolExecutionReceipt,
    *,
    state: PostconditionState,
    observation_digest: str,
    observation_origin_id: str,
    observed_at: datetime,
    subject_ref: str | None = None,
    expected_digest: str | None = None,
    detail_code: str | None = None,
    evidence_id: str | None = None,
    postcondition_id: str | None = None,
) -> tuple[VerificationEvidence, VerificationPostcondition]:
    """Bind an independently observed tool postcondition to execution lineage.

    Receipt success is deliberately insufficient. The caller must provide an
    observed postcondition state and observation digest. A successful
    postcondition is rejected when the execution receipt itself was not
    successful.
    """

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    state = PostconditionState(state)
    if receipt.tenant_id != claim.tenant_id:
        raise ValueError("tool receipt tenant mismatch")
    if claim.operation_id is None or receipt.operation_id != claim.operation_id:
        raise ValueError("tool receipt operation mismatch")
    if state is PostconditionState.SATISFIED and receipt.status is not ToolExecutionStatus.SUCCEEDED:
        raise ValueError("failed or denied tool execution cannot have satisfied postcondition")
    if state is PostconditionState.COMPENSATED and not receipt.compensation_ref:
        raise ValueError("compensated postcondition requires compensation_ref")

    relation = EvidenceRelation.POSTCONDITION
    if state is PostconditionState.SATISFIED:
        relation = EvidenceRelation.SUPPORTS
    elif state is PostconditionState.FAILED:
        relation = EvidenceRelation.CONTRADICTS

    evidence = VerificationEvidence(
        evidence_id=evidence_id or str(uuid4()),
        tenant_id=claim.tenant_id,
        kind=EvidenceKind.POSTCONDITION,
        origin_type=ProvenanceOrigin.SYSTEM,
        source_id="postcondition:" + receipt.receipt_id,
        origin_id=observation_origin_id,
        content_digest=observation_digest,
        observed_at=observed_at,
        locator=subject_ref or ("tool:" + receipt.tool_id),
        provenance_refs=(
            "tool-receipt:" + receipt.receipt_id,
            "tool-request:" + receipt.request_id,
            "tool-arguments:" + receipt.arguments_digest,
        ),
        bound_claim_ids=(claim.claim_id,),
        relation=relation,
        data_class=claim.data_class,
    )
    postcondition = VerificationPostcondition(
        postcondition_id=postcondition_id or str(uuid4()),
        tenant_id=claim.tenant_id,
        operation_id=receipt.operation_id,
        subject_ref=subject_ref or ("tool:" + receipt.tool_id),
        state=state,
        observed_at=observed_at,
        evidence_ids=(evidence.evidence_id,),
        tool_receipt_ref=receipt.receipt_id,
        expected_digest=expected_digest,
        actual_digest=observation_digest if expected_digest is not None else None,
        detail_code=detail_code,
    )
    return evidence, postcondition


__all__ = [
    "tool_postcondition_verification_records",
    "tool_receipt_verification_evidence",
]

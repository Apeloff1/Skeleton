"""Deterministic verification runtime for claims, evidence, and actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

from skeleton.contracts.verification import (
    Claim,
    ClaimCheck,
    ClaimKind,
    ConfidenceBand,
    EvidenceReference,
    PostconditionCheck,
    VerificationLevel,
    VerificationOutcome,
    VerificationReceipt,
    VerificationRequest,
    content_digest,
)
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
)


_LEVEL_RANK = {
    VerificationLevel.NONE: 0,
    VerificationLevel.STRUCTURAL: 1,
    VerificationLevel.EVIDENCE: 2,
    VerificationLevel.ACTION: 3,
    VerificationLevel.HIGH_IMPACT: 4,
}


@dataclass(frozen=True, slots=True)
class DeterministicVerificationInput:
    candidate_text: str
    claims: tuple[Claim, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    postconditions: tuple[PostconditionCheck, ...] = ()
    evidence_content: Mapping[str, str] | None = None


def tool_receipt_postcondition(
    receipt: ToolExecutionReceipt,
) -> PostconditionCheck:
    """Convert one observable tool receipt into a verification postcondition."""

    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    passed = receipt.status is ToolExecutionStatus.SUCCEEDED
    return PostconditionCheck(
        check_id="tool:" + receipt.receipt_id,
        subject_ref="tool-receipt:" + receipt.receipt_id,
        passed=passed,
        reason_code=(
            "tool_succeeded"
            if passed
            else "tool_" + receipt.status.value
        ),
        evidence_refs=(),
    )


class VerificationRuntime:
    """Verify only observable candidate/evidence/action properties."""

    @staticmethod
    def _claim_checks(
        claims: Iterable[Claim],
        evidence: Iterable[EvidenceReference],
        *,
        evidence_content: Mapping[str, str] | None = None,
    ) -> tuple[ClaimCheck, ...]:
        evidence_by_id: dict[str, EvidenceReference] = {}
        for item in evidence:
            if not isinstance(item, EvidenceReference):
                raise TypeError("evidence must contain EvidenceReference values")
            if item.evidence_id in evidence_by_id:
                raise ValueError("evidence ids must be unique")
            evidence_by_id[item.evidence_id] = item

        content_map = dict(evidence_content or {})
        checks: list[ClaimCheck] = []
        seen_claims: set[str] = set()

        for claim in claims:
            if not isinstance(claim, Claim):
                raise TypeError("claims must contain Claim values")
            if claim.claim_id in seen_claims:
                raise ValueError("claim ids must be unique")
            seen_claims.add(claim.claim_id)

            reasons: list[str] = []
            resolved = tuple(
                ref for ref in claim.evidence_refs if ref in evidence_by_id
            )
            missing = tuple(
                ref for ref in claim.evidence_refs if ref not in evidence_by_id
            )
            if missing:
                reasons.append("missing_evidence_ref")

            requires_evidence = (
                claim.required
                and claim.kind
                in {
                    ClaimKind.FACTUAL,
                    ClaimKind.INTERPRETATION,
                    ClaimKind.ACTION,
                }
            )
            grounded = not missing and (
                bool(resolved) if requires_evidence else True
            )
            if requires_evidence and not resolved:
                reasons.append("claim_ungrounded")

            digest_failed = False
            for evidence_id in resolved:
                if evidence_id not in content_map:
                    continue
                observed = content_digest(content_map[evidence_id])
                if observed != evidence_by_id[evidence_id].content_digest:
                    digest_failed = True
                    reasons.append("evidence_digest_mismatch")
            if digest_failed:
                grounded = False

            citation_ids: set[str] = set()
            for evidence_id in resolved:
                item = evidence_by_id[evidence_id]
                citation_ids.add(item.evidence_id)
                citation_id = item.citation_metadata.get("citation_id")
                if isinstance(citation_id, str) and citation_id.strip():
                    citation_ids.add(citation_id.strip())

            citation_valid = all(
                ref in citation_ids
                for ref in claim.citation_refs
            )
            if not citation_valid:
                reasons.append("citation_not_bound_to_claim_evidence")

            checks.append(
                ClaimCheck(
                    claim_id=claim.claim_id,
                    grounded=grounded,
                    citation_valid=citation_valid,
                    evidence_refs=resolved,
                    reason_codes=tuple(dict.fromkeys(reasons)),
                )
            )
        return tuple(checks)

    @staticmethod
    def _outcome_for_failure(
        level: VerificationLevel,
        *,
        structural_failure: bool,
        evidence_failure: bool,
        action_failure: bool,
    ) -> tuple[VerificationOutcome, dict[str, object] | None]:
        if structural_failure:
            return (
                VerificationOutcome.REPAIR,
                {
                    "reason": "structural_verification_failed",
                    "retry_allowed": True,
                },
            )
        if action_failure:
            return (VerificationOutcome.BLOCK, None)
        if evidence_failure:
            if level is VerificationLevel.HIGH_IMPACT:
                return (VerificationOutcome.BLOCK, None)
            return (
                VerificationOutcome.QUALIFIED,
                {
                    "reason": "evidence_incomplete",
                    "retry_allowed": True,
                },
            )
        if level is VerificationLevel.HIGH_IMPACT:
            return (
                VerificationOutcome.BLOCK,
                {
                    "reason": "semantic_high_impact_verifier_required",
                    "retry_allowed": False,
                },
            )
        return (VerificationOutcome.VERIFIED, None)

    def verify_deterministic(
        self,
        request: VerificationRequest,
        verification_input: DeterministicVerificationInput,
        *,
        now: datetime | None = None,
    ) -> VerificationReceipt:
        if not isinstance(request, VerificationRequest):
            raise TypeError("request must be VerificationRequest")
        if not isinstance(
            verification_input,
            DeterministicVerificationInput,
        ):
            raise TypeError(
                "verification_input must be DeterministicVerificationInput"
            )
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )

        reasons: list[str] = []
        candidate = verification_input.candidate_text
        structural_failure = (
            not isinstance(candidate, str)
            or not candidate.strip()
        )
        if structural_failure:
            reasons.append("candidate_empty")

        deadline_expired = (
            request.deadline is not None
            and instant > request.deadline
        )
        if deadline_expired:
            reasons.append("verification_deadline_expired")

        claim_checks = self._claim_checks(
            verification_input.claims,
            verification_input.evidence,
            evidence_content=verification_input.evidence_content,
        )

        level = request.required_level
        evidence_required = _LEVEL_RANK[level] >= _LEVEL_RANK[
            VerificationLevel.EVIDENCE
        ]
        action_required = _LEVEL_RANK[level] >= _LEVEL_RANK[
            VerificationLevel.ACTION
        ]

        evidence_failure = False
        if evidence_required:
            failed_claims = tuple(
                item
                for item in claim_checks
                if not item.passed
            )
            evidence_failure = bool(failed_claims)
            if failed_claims:
                reasons.append("claim_grounding_or_citation_failed")

            declared = set(request.evidence_refs)
            supplied = {
                item.evidence_id
                for item in verification_input.evidence
            }
            if not declared.issubset(supplied):
                evidence_failure = True
                reasons.append("declared_evidence_missing")

        postconditions = verification_input.postconditions
        if any(
            not isinstance(item, PostconditionCheck)
            for item in postconditions
        ):
            raise TypeError(
                "postconditions must contain PostconditionCheck values"
            )

        action_failure = False
        if action_required:
            if request.tool_receipt_refs and not postconditions:
                action_failure = True
                reasons.append("action_postconditions_missing")
            failed_postconditions = tuple(
                item for item in postconditions if not item.passed
            )
            if failed_postconditions:
                action_failure = True
                reasons.append("action_postcondition_failed")

        if deadline_expired:
            structural_failure = True
            reasons.append("verification_incomplete")

        outcome, repair = self._outcome_for_failure(
            level,
            structural_failure=structural_failure,
            evidence_failure=evidence_failure,
            action_failure=action_failure,
        )

        if outcome is VerificationOutcome.VERIFIED:
            confidence = (
                ConfidenceBand.HIGH
                if level in {
                    VerificationLevel.ACTION,
                    VerificationLevel.HIGH_IMPACT,
                }
                else ConfidenceBand.MEDIUM
            )
        elif outcome is VerificationOutcome.QUALIFIED:
            confidence = ConfidenceBand.LOW
        else:
            confidence = ConfidenceBand.UNKNOWN

        evidence_refs = tuple(
            dict.fromkeys(
                ref
                for check in claim_checks
                for ref in check.evidence_refs
            )
        )

        return VerificationReceipt(
            verification_id=request.verification_id,
            operation_id=request.operation_id,
            execution_id=request.execution_id,
            turn_id=request.turn_id,
            candidate_ref=request.candidate_ref,
            level=level,
            outcome=outcome,
            reason_codes=tuple(dict.fromkeys(reasons)),
            claim_checks=claim_checks,
            postcondition_checks=tuple(postconditions),
            evidence_refs=evidence_refs,
            repair_directive=repair,
            confidence_band=confidence,
            created_at=instant,
            completed_at=instant,
        )


__all__ = [
    "DeterministicVerificationInput",
    "VerificationRuntime",
    "tool_receipt_postcondition",
]

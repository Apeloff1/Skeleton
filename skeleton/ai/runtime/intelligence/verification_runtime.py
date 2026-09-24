"""Deterministic verification runtime.

This layer performs structural/evidence/citation/postcondition verification.
It intentionally does not manufacture independent verification. When policy
requires an independent verifier, a previously produced independent canonical
VerificationCheck must be supplied or the result remains UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.verification import (
    EvidenceReference,
    PostconditionObservation,
    VerificationCheck,
    VerificationClaim,
    VerificationLevel,
    VerificationOutcome,
)
from skeleton.intelligence.verification_policy import (
    VerificationPolicyDecision,
    select_verification_policy,
)
from skeleton.retrieval.verification import (
    CitationIntegrityResult,
    GroundingAssessment,
    ground_claim,
)


@dataclass(frozen=True, slots=True)
class VerificationAssessment:
    claim_id: str
    policy: VerificationPolicyDecision
    outcome: VerificationOutcome
    policy_satisfied: bool
    grounding: GroundingAssessment
    check: VerificationCheck | None
    issues: tuple[str, ...]


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("verified_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _valid_independent_checks(
    claim: VerificationClaim,
    checks: tuple[VerificationCheck, ...],
) -> tuple[VerificationCheck, ...]:
    return tuple(
        check
        for check in checks
        if check.claim_id == claim.claim_id
        and check.tenant_id == claim.tenant_id
        and check.independent
        and check.level >= VerificationLevel.INDEPENDENT
        and check.outcome is VerificationOutcome.PASSED
    )


def _valid_postconditions(
    claim: VerificationClaim,
    observations: tuple[PostconditionObservation, ...],
) -> tuple[PostconditionObservation, ...]:
    return tuple(
        item
        for item in observations
        if item.tenant_id == claim.tenant_id
        and (
            claim.operation_id is None
            or item.operation_id == claim.operation_id
        )
    )


def _check_id(
    *,
    claim: VerificationClaim,
    policy: VerificationPolicyDecision,
    verified_at: datetime,
    verifier_id: str,
    evidence_ids: tuple[str, ...],
    observation_ids: tuple[str, ...],
    independent_check_ids: tuple[str, ...],
) -> str:
    material = "|".join(
        (
            claim.digest,
            str(int(policy.level)),
            verified_at.isoformat(),
            verifier_id,
            ",".join(sorted(evidence_ids)),
            ",".join(sorted(observation_ids)),
            ",".join(sorted(independent_check_ids)),
        )
    )
    return str(uuid5(NAMESPACE_URL, "verification-check:" + material))


class VerificationRuntime:
    """Evaluate canonical claims against deterministic evidence obligations."""

    def verify(
        self,
        claim: VerificationClaim,
        *,
        evidence: tuple[EvidenceReference, ...] = (),
        postconditions: tuple[PostconditionObservation, ...] = (),
        independent_checks: tuple[VerificationCheck, ...] = (),
        verified_at: datetime,
        verifier_id: str = "verification-runtime:deterministic",
        action_effect: str | None = None,
        externally_observable_action: bool = False,
    ) -> VerificationAssessment:
        if not isinstance(claim, VerificationClaim):
            raise TypeError("claim must be VerificationClaim")
        instant = _utc(verified_at)
        if not isinstance(verifier_id, str) or not verifier_id.strip():
            raise ValueError("verifier_id must be non-empty")

        policy = select_verification_policy(
            claim,
            action_effect=action_effect,
            externally_observable_action=externally_observable_action,
        )
        grounding = ground_claim(claim, list(evidence))
        issues: list[str] = []

        for citation in grounding.citation_results:
            if not citation.accepted:
                issues.extend(
                    f"citation:{citation.evidence_id}:{reason}"
                    for reason in citation.reasons
                )

        outcome = VerificationOutcome.PASSED
        if grounding.has_authoritative_contradiction:
            if grounding.has_authoritative_support:
                outcome = VerificationOutcome.CONTESTED
                issues.append("authoritative_evidence_contested")
            else:
                outcome = VerificationOutcome.FAILED
                issues.append("authoritative_evidence_contradicts_claim")

        if (
            outcome is VerificationOutcome.PASSED
            and policy.level >= VerificationLevel.EVIDENCE
        ):
            if not grounding.has_authoritative_support:
                outcome = VerificationOutcome.UNKNOWN
                issues.append("authoritative_support_missing")
            elif len(grounding.supporting_origin_ids) < policy.min_independent_origins:
                outcome = VerificationOutcome.UNKNOWN
                issues.append("independent_origin_requirement_unsatisfied")

        valid_independent = _valid_independent_checks(claim, independent_checks)
        if (
            outcome is VerificationOutcome.PASSED
            and policy.level >= VerificationLevel.INDEPENDENT
            and not valid_independent
        ):
            outcome = VerificationOutcome.UNKNOWN
            issues.append("independent_verification_required")

        valid_postconditions = _valid_postconditions(claim, postconditions)
        if (
            outcome is VerificationOutcome.PASSED
            and policy.require_postcondition
        ):
            if claim.operation_id is None:
                outcome = VerificationOutcome.UNKNOWN
                issues.append("postcondition_operation_identity_missing")
            elif not valid_postconditions:
                outcome = VerificationOutcome.UNKNOWN
                issues.append("postcondition_observation_required")
            elif any(not item.passed for item in valid_postconditions):
                outcome = VerificationOutcome.FAILED
                issues.append("postcondition_failed")

        policy_satisfied = outcome is VerificationOutcome.PASSED
        check: VerificationCheck | None = None
        if policy_satisfied:
            evidence_ids = (
                grounding.supporting_evidence_ids
                if policy.level >= VerificationLevel.EVIDENCE
                else ()
            )
            observation_ids = (
                tuple(item.observation_id for item in valid_postconditions)
                if policy.level >= VerificationLevel.POSTCONDITION
                else ()
            )
            independent_ids = tuple(item.check_id for item in valid_independent)
            check = VerificationCheck(
                check_id=_check_id(
                    claim=claim,
                    policy=policy,
                    verified_at=instant,
                    verifier_id=verifier_id,
                    evidence_ids=evidence_ids,
                    observation_ids=observation_ids,
                    independent_check_ids=independent_ids,
                ),
                claim_id=claim.claim_id,
                tenant_id=claim.tenant_id,
                level=policy.level,
                outcome=VerificationOutcome.PASSED,
                verifier_id=verifier_id,
                verified_at=instant,
                evidence_ids=evidence_ids,
                postcondition_observation_ids=observation_ids,
                independent=bool(valid_independent),
                issues=(),
            )

        return VerificationAssessment(
            claim_id=claim.claim_id,
            policy=policy,
            outcome=outcome,
            policy_satisfied=policy_satisfied,
            grounding=grounding,
            check=check,
            issues=tuple(dict.fromkeys(issues)),
        )


__all__ = [
    "VerificationAssessment",
    "VerificationRuntime",
]

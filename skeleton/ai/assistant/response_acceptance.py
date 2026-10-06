"""Deterministic final-response acceptance over Volume-8 evidence receipts.

This module does not extract claims from prose and does not publish responses.
It accepts only explicit canonical VerificationClaim objects plus their
ClaimEvidenceReceipt bindings.  Product routes or engine finalization can use
this decision before transcript commit once structured claim extraction is
available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable, Sequence

from skeleton.contracts.verification import (
    ClaimKind,
    VerificationClaim,
    VerificationRisk,
)

from .evidence import (
    ClaimEvidenceReceipt,
    PublicationDisposition,
)


class ResponseAcceptanceError(ValueError):
    """Response-acceptance evidence is malformed or contradictory."""


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ResponseAcceptanceError(
            f"{field} must be timezone-aware datetime"
        )
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ResponseAcceptancePolicy:
    policy_id: str
    required_claim_kinds: tuple[ClaimKind | str, ...] = (
        ClaimKind.FACT,
        ClaimKind.ACTION_OUTCOME,
    )
    allow_qualified_low_risk: bool = True
    max_receipt_age_s: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ResponseAcceptanceError("policy_id must be non-empty")
        object.__setattr__(self, "policy_id", self.policy_id.strip())
        normalized: list[ClaimKind] = []
        for raw in self.required_claim_kinds:
            try:
                kind = ClaimKind(raw)
            except ValueError as exc:
                raise ResponseAcceptanceError(
                    "invalid required claim kind"
                ) from exc
            if kind not in normalized:
                normalized.append(kind)
        if not normalized:
            raise ResponseAcceptanceError(
                "required_claim_kinds must not be empty"
            )
        object.__setattr__(
            self,
            "required_claim_kinds",
            tuple(normalized),
        )
        if not isinstance(self.allow_qualified_low_risk, bool):
            raise ResponseAcceptanceError(
                "allow_qualified_low_risk must be boolean"
            )
        if self.max_receipt_age_s is not None:
            if (
                isinstance(self.max_receipt_age_s, bool)
                or not isinstance(self.max_receipt_age_s, (int, float))
                or float(self.max_receipt_age_s) < 0
            ):
                raise ResponseAcceptanceError(
                    "max_receipt_age_s must be non-negative numeric"
                )
            object.__setattr__(
                self,
                "max_receipt_age_s",
                float(self.max_receipt_age_s),
            )


@dataclass(frozen=True, slots=True)
class ResponseAcceptanceDecision:
    accepted: bool
    reasons: tuple[str, ...]
    required_claim_ids: tuple[str, ...]
    accepted_claim_ids: tuple[str, ...]
    missing_receipt_claim_ids: tuple[str, ...]
    rejected_claim_ids: tuple[str, ...]
    qualified_claim_ids: tuple[str, ...]
    receipt_digests: tuple[str, ...]
    authority_scope: str = "response-acceptance-decision-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.accepted and (
            self.missing_receipt_claim_ids or self.rejected_claim_ids
        ):
            raise ResponseAcceptanceError(
                "accepted response cannot contain unresolved required claims"
            )
        if self.authority_scope != "response-acceptance-decision-only":
            raise ResponseAcceptanceError(
                "response acceptance authority scope escalated"
            )
        if self.production_authority is not False:
            raise ResponseAcceptanceError(
                "response acceptance cannot commit transcript state"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "required_claim_ids": list(self.required_claim_ids),
            "accepted_claim_ids": list(self.accepted_claim_ids),
            "missing_receipt_claim_ids": list(self.missing_receipt_claim_ids),
            "rejected_claim_ids": list(self.rejected_claim_ids),
            "qualified_claim_ids": list(self.qualified_claim_ids),
            "receipt_digests": list(self.receipt_digests),
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def evaluate_response_acceptance(
    *,
    claims: Sequence[VerificationClaim] | Iterable[VerificationClaim],
    receipts: Sequence[ClaimEvidenceReceipt] | Iterable[ClaimEvidenceReceipt],
    policy: ResponseAcceptancePolicy,
    finalized_at: datetime,
) -> ResponseAcceptanceDecision:
    """Evaluate explicit structured claims against Volume-8 receipts."""

    if not isinstance(policy, ResponseAcceptancePolicy):
        raise TypeError("policy must be ResponseAcceptancePolicy")
    now = _utc(finalized_at, "finalized_at")
    claim_values = tuple(claims)
    receipt_values = tuple(receipts)
    if any(not isinstance(item, VerificationClaim) for item in claim_values):
        raise TypeError("claims must contain VerificationClaim")
    if any(not isinstance(item, ClaimEvidenceReceipt) for item in receipt_values):
        raise TypeError("receipts must contain ClaimEvidenceReceipt")

    claim_by_id: dict[str, VerificationClaim] = {}
    reasons: list[str] = []
    for item in claim_values:
        if item.claim_id in claim_by_id:
            reasons.append("duplicate_claim_id")
        claim_by_id[item.claim_id] = item

    receipt_by_claim: dict[str, ClaimEvidenceReceipt] = {}
    for item in receipt_values:
        if item.claim_id in receipt_by_claim:
            reasons.append("duplicate_receipt_for_claim")
            continue
        receipt_by_claim[item.claim_id] = item

    unknown_receipts = sorted(
        set(receipt_by_claim) - set(claim_by_id)
    )
    if unknown_receipts:
        reasons.append("receipt_for_unknown_claim")

    required: list[str] = []
    accepted_claims: list[str] = []
    missing: list[str] = []
    rejected: list[str] = []
    qualified: list[str] = []
    receipt_digests: list[str] = []

    for claim in claim_values:
        if claim.kind not in policy.required_claim_kinds:
            continue
        required.append(claim.claim_id)
        receipt = receipt_by_claim.get(claim.claim_id)
        if receipt is None:
            missing.append(claim.claim_id)
            continue

        receipt_digests.append(receipt.digest)
        if receipt.claim_digest != claim.digest:
            rejected.append(claim.claim_id)
            reasons.append("claim_receipt_digest_mismatch")
            continue
        if receipt.evaluated_at > now:
            rejected.append(claim.claim_id)
            reasons.append("claim_receipt_from_future")
            continue
        if policy.max_receipt_age_s is not None:
            age = (now - receipt.evaluated_at).total_seconds()
            if age > policy.max_receipt_age_s:
                rejected.append(claim.claim_id)
                reasons.append("claim_receipt_stale")
                continue

        if receipt.disposition is PublicationDisposition.PUBLISH:
            accepted_claims.append(claim.claim_id)
            continue
        if (
            receipt.disposition
            is PublicationDisposition.PUBLISH_WITH_QUALIFICATION
            and claim.risk in {VerificationRisk.LOW, VerificationRisk.MEDIUM}
            and policy.allow_qualified_low_risk
        ):
            accepted_claims.append(claim.claim_id)
            qualified.append(claim.claim_id)
            continue

        rejected.append(claim.claim_id)
        if receipt.disposition is PublicationDisposition.CONTESTED:
            reasons.append("required_claim_contested")
        elif receipt.disposition is PublicationDisposition.ABSTAIN:
            reasons.append("required_claim_abstained")
        else:
            reasons.append("required_claim_qualification_not_admitted")

    normalized_reasons = tuple(sorted(set(reasons)))
    accepted = not (
        normalized_reasons
        or missing
        or rejected
    )
    return ResponseAcceptanceDecision(
        accepted=accepted,
        reasons=normalized_reasons,
        required_claim_ids=tuple(required),
        accepted_claim_ids=tuple(accepted_claims),
        missing_receipt_claim_ids=tuple(missing),
        rejected_claim_ids=tuple(rejected),
        qualified_claim_ids=tuple(qualified),
        receipt_digests=tuple(receipt_digests),
    )


__all__ = [
    "ResponseAcceptanceDecision",
    "ResponseAcceptanceError",
    "ResponseAcceptancePolicy",
    "evaluate_response_acceptance",
]

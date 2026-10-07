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


@dataclass(frozen=True, slots=True)
class LiveClaimEvidenceBinding:
    """Content-minimized claim/evidence decision bound to live turn lineage."""

    operation_id: str
    context_digest: str
    decision_digest: str
    accepted: bool
    reasons: tuple[str, ...]
    required_claim_count: int
    accepted_claim_count: int
    qualified_claim_count: int
    claim_digest_hashes: tuple[str, ...]
    receipt_digest_hashes: tuple[str, ...]
    authority_scope: str = "live-claim-evidence-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _canonical_live_text(self.operation_id, "operation_id", maximum=512),
        )
        object.__setattr__(
            self,
            "context_digest",
            _canonical_sha256(self.context_digest, "context_digest"),
        )
        object.__setattr__(
            self,
            "decision_digest",
            _canonical_sha256(self.decision_digest, "decision_digest"),
        )
        if not isinstance(self.accepted, bool):
            raise ResponseAcceptanceError("claim evidence accepted must be boolean")
        for field in (
            "required_claim_count",
            "accepted_claim_count",
            "qualified_claim_count",
        ):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ResponseAcceptanceError(f"{field} must be non-negative integer")
        if self.accepted_claim_count > self.required_claim_count:
            raise ResponseAcceptanceError(
                "accepted claim count cannot exceed required claim count"
            )
        if self.qualified_claim_count > self.accepted_claim_count:
            raise ResponseAcceptanceError(
                "qualified claim count cannot exceed accepted claim count"
            )
        normalized_reasons = tuple(
            sorted(
                {
                    _canonical_live_text(str(reason), "claim_reason", maximum=128)
                    for reason in self.reasons
                }
            )
        )
        object.__setattr__(self, "reasons", normalized_reasons)
        if self.accepted and self.reasons:
            raise ResponseAcceptanceError(
                "accepted claim evidence cannot retain rejection reasons"
            )
        if not self.accepted and not self.reasons:
            raise ResponseAcceptanceError(
                "rejected claim evidence must retain rejection reasons"
            )
        for field in ("claim_digest_hashes", "receipt_digest_hashes"):
            values = tuple(getattr(self, field))
            if len(set(values)) != len(values):
                raise ResponseAcceptanceError(f"{field} must be unique")
            for value in values:
                _canonical_sha256(value, field)
            object.__setattr__(self, field, tuple(sorted(values)))
        if self.authority_scope != "live-claim-evidence-binding-only":
            raise ResponseAcceptanceError("claim evidence authority scope escalated")
        if self.production_authority is not False:
            raise ResponseAcceptanceError(
                "claim evidence binding cannot commit transcript state"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "context_digest": self.context_digest,
            "decision_digest": self.decision_digest,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "required_claim_count": self.required_claim_count,
            "accepted_claim_count": self.accepted_claim_count,
            "qualified_claim_count": self.qualified_claim_count,
            "claim_digest_hashes": list(self.claim_digest_hashes),
            "receipt_digest_hashes": list(self.receipt_digest_hashes),
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


def bind_live_claim_evidence(
    *,
    operation_id: str,
    context_digest: str,
    claims: Sequence[VerificationClaim] | Iterable[VerificationClaim],
    receipts: Sequence[ClaimEvidenceReceipt] | Iterable[ClaimEvidenceReceipt],
    policy: ResponseAcceptancePolicy,
    finalized_at: datetime,
) -> LiveClaimEvidenceBinding:
    """Bind structured Volume-8 claim evidence to one live operation/context."""

    operation = _canonical_live_text(operation_id, "operation_id", maximum=512)
    context = _canonical_sha256(context_digest, "context_digest")
    claim_values = tuple(claims)
    receipt_values = tuple(receipts)
    if any(not isinstance(item, VerificationClaim) for item in claim_values):
        raise TypeError("claims must contain VerificationClaim")
    if any(not isinstance(item, ClaimEvidenceReceipt) for item in receipt_values):
        raise TypeError("receipts must contain ClaimEvidenceReceipt")

    lineage_reasons: list[str] = []
    required_kinds = frozenset(policy.required_claim_kinds)
    for claim in claim_values:
        if claim.kind not in required_kinds:
            continue
        if claim.operation_id != operation:
            lineage_reasons.append("claim_operation_identity_mismatch")
        if claim.context_digest != context:
            lineage_reasons.append("claim_context_identity_mismatch")

    decision = evaluate_response_acceptance(
        claims=claim_values,
        receipts=receipt_values,
        policy=policy,
        finalized_at=finalized_at,
    )
    combined_reasons = tuple(
        sorted(set(decision.reasons).union(lineage_reasons))
    )
    accepted = decision.accepted and not combined_reasons
    claim_hashes = tuple(
        sorted({_hash_ref(claim.digest) for claim in claim_values})
    )
    receipt_hashes = tuple(
        sorted({_hash_ref(receipt.digest) for receipt in receipt_values})
    )
    return LiveClaimEvidenceBinding(
        operation_id=operation,
        context_digest=context,
        decision_digest=decision.digest,
        accepted=accepted,
        reasons=combined_reasons,
        required_claim_count=len(decision.required_claim_ids),
        accepted_claim_count=(
            len(decision.accepted_claim_ids) if accepted else 0
        ),
        qualified_claim_count=(
            len(decision.qualified_claim_ids) if accepted else 0
        ),
        claim_digest_hashes=claim_hashes,
        receipt_digest_hashes=receipt_hashes,
    )


LIVE_RESPONSE_ACCEPTANCE_SCHEMA_VERSION = 1


def _canonical_live_text(
    value: object,
    field: str,
    *,
    maximum: int,
) -> str:
    if not isinstance(value, str):
        raise ResponseAcceptanceError(f"{field} must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized)
    ):
        raise ResponseAcceptanceError(f"{field} is not canonical")
    return normalized


def _canonical_sha256(value: object, field: str) -> str:
    text = _canonical_live_text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ResponseAcceptanceError(f"{field} must be lowercase sha256")
    return text


def _hash_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_live_refs(
    values: Sequence[str] | Iterable[str],
    field: str,
    *,
    maximum_count: int,
    required_prefix: str | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    raw_values = tuple(values)
    reasons: list[str] = []
    if len(raw_values) > maximum_count:
        reasons.append(f"{field}_count_exceeded")
        raw_values = raw_values[:maximum_count]

    normalized: list[str] = []
    for raw in raw_values:
        try:
            value = _canonical_live_text(raw, field, maximum=2048)
        except ResponseAcceptanceError:
            reasons.append(f"{field}_malformed")
            continue
        if required_prefix is not None and not value.startswith(required_prefix):
            reasons.append(f"{field}_prefix_invalid")
            continue
        normalized.append(value)

    if len(set(normalized)) != len(normalized):
        reasons.append(f"{field}_duplicate")
    return tuple(sorted(normalized)), tuple(sorted(set(reasons)))


@dataclass(frozen=True, slots=True)
class LiveResponseAcceptancePolicy:
    """Fail-closed policy for committing one engine-backed live chat result."""

    policy_id: str = "ai-chat-live-response/v1"
    require_provider_receipt: bool = True
    require_structured_claim_evidence: bool = False
    max_output_utf8_bytes: int = 2_000_000
    max_receipt_refs: int = 64

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _canonical_live_text(self.policy_id, "policy_id", maximum=256),
        )
        if not isinstance(self.require_provider_receipt, bool):
            raise ResponseAcceptanceError(
                "require_provider_receipt must be boolean"
            )
        if not isinstance(self.require_structured_claim_evidence, bool):
            raise ResponseAcceptanceError(
                "require_structured_claim_evidence must be boolean"
            )
        for field in ("max_output_utf8_bytes", "max_receipt_refs"):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ResponseAcceptanceError(f"{field} must be positive integer")
        if self.max_output_utf8_bytes > 16_000_000:
            raise ResponseAcceptanceError(
                "max_output_utf8_bytes exceeds hard safety ceiling"
            )
        if self.max_receipt_refs > 1024:
            raise ResponseAcceptanceError(
                "max_receipt_refs exceeds hard safety ceiling"
            )


@dataclass(frozen=True, slots=True)
class LiveResponseAcceptanceReceipt:
    """Content-minimized receipt binding an accepted output to execution lineage."""

    policy_id: str
    operation_id: str
    observed_operation_id: str | None
    expected_execution_id: str
    observed_execution_id: str | None
    context_digest: str
    verification_ref_hash: str | None
    output_sha256: str | None
    output_utf8_bytes: int
    provider_receipt_ref_hashes: tuple[str, ...]
    tool_receipt_ref_hashes: tuple[str, ...]
    evidence_ref_hashes: tuple[str, ...]
    claim_evidence_digest: str | None
    accepted: bool
    reasons: tuple[str, ...]
    schema_version: int = LIVE_RESPONSE_ACCEPTANCE_SCHEMA_VERSION
    authority_scope: str = "live-response-acceptance-decision-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_RESPONSE_ACCEPTANCE_SCHEMA_VERSION:
            raise ResponseAcceptanceError(
                "live response acceptance schema version drifted"
            )
        for field in ("policy_id", "operation_id", "expected_execution_id"):
            object.__setattr__(
                self,
                field,
                _canonical_live_text(
                    getattr(self, field),
                    field,
                    maximum=512,
                ),
            )
        object.__setattr__(
            self,
            "context_digest",
            _canonical_sha256(self.context_digest, "context_digest"),
        )
        if self.observed_operation_id is not None:
            object.__setattr__(
                self,
                "observed_operation_id",
                _canonical_live_text(
                    self.observed_operation_id,
                    "observed_operation_id",
                    maximum=512,
                ),
            )
        if self.observed_execution_id is not None:
            object.__setattr__(
                self,
                "observed_execution_id",
                _canonical_live_text(
                    self.observed_execution_id,
                    "observed_execution_id",
                    maximum=512,
                ),
            )
        for field in (
            "verification_ref_hash",
            "output_sha256",
            "claim_evidence_digest",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(
                    self,
                    field,
                    _canonical_sha256(value, field),
                )
        if (
            isinstance(self.output_utf8_bytes, bool)
            or not isinstance(self.output_utf8_bytes, int)
            or self.output_utf8_bytes < 0
        ):
            raise ResponseAcceptanceError(
                "output_utf8_bytes must be non-negative integer"
            )
        for field in (
            "provider_receipt_ref_hashes",
            "tool_receipt_ref_hashes",
            "evidence_ref_hashes",
        ):
            values = tuple(getattr(self, field))
            for digest in values:
                _canonical_sha256(digest, field)
            object.__setattr__(self, field, values)
        if not isinstance(self.accepted, bool):
            raise ResponseAcceptanceError("accepted must be boolean")
        normalized_reasons = tuple(
            sorted(
                {
                    _canonical_live_text(
                        str(reason),
                        "reason",
                        maximum=128,
                    )
                    for reason in self.reasons
                }
            )
        )
        object.__setattr__(self, "reasons", normalized_reasons)
        if self.accepted and self.reasons:
            raise ResponseAcceptanceError(
                "accepted live response cannot retain rejection reasons"
            )
        if not self.accepted and not self.reasons:
            raise ResponseAcceptanceError(
                "rejected live response must retain at least one reason"
            )
        if self.accepted and (
            self.observed_operation_id != self.operation_id
            or self.observed_execution_id != self.expected_execution_id
            or self.verification_ref_hash is None
            or self.output_sha256 is None
            or self.output_utf8_bytes <= 0
            or not self.provider_receipt_ref_hashes
        ):
            raise ResponseAcceptanceError(
                "accepted live response is missing mandatory lineage evidence"
            )
        if self.authority_scope != "live-response-acceptance-decision-only":
            raise ResponseAcceptanceError(
                "live response acceptance authority scope escalated"
            )
        if self.production_authority is not False:
            raise ResponseAcceptanceError(
                "live response acceptance cannot commit transcript state"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "operation_id": self.operation_id,
            "observed_operation_id": self.observed_operation_id,
            "expected_execution_id": self.expected_execution_id,
            "observed_execution_id": self.observed_execution_id,
            "context_digest": self.context_digest,
            "verification_ref_hash": self.verification_ref_hash,
            "output_sha256": self.output_sha256,
            "output_utf8_bytes": self.output_utf8_bytes,
            "provider_receipt_ref_hashes": list(
                self.provider_receipt_ref_hashes
            ),
            "tool_receipt_ref_hashes": list(self.tool_receipt_ref_hashes),
            "evidence_ref_hashes": list(self.evidence_ref_hashes),
            "claim_evidence_digest": self.claim_evidence_digest,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
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

    @property
    def artifact_ref(self) -> str:
        return "response-acceptance-sha256:" + self.digest


def evaluate_live_response_acceptance(
    *,
    operation_id: str,
    observed_operation_id: object,
    expected_execution_id: str,
    observed_execution_id: object,
    context_digest: str,
    final_output: object,
    verification: object,
    provider_receipts: Sequence[str] | Iterable[str],
    tool_receipts: Sequence[str] | Iterable[str] = (),
    evidence_refs: Sequence[str] | Iterable[str] = (),
    claim_evidence: LiveClaimEvidenceBinding | None = None,
    policy: LiveResponseAcceptancePolicy | None = None,
) -> LiveResponseAcceptanceReceipt:
    """Evaluate one engine result before it may enter canonical transcript state."""

    effective_policy = policy or LiveResponseAcceptancePolicy()
    if not isinstance(effective_policy, LiveResponseAcceptancePolicy):
        raise TypeError("policy must be LiveResponseAcceptancePolicy")

    operation = _canonical_live_text(
        operation_id,
        "operation_id",
        maximum=512,
    )
    expected_execution = _canonical_live_text(
        expected_execution_id,
        "expected_execution_id",
        maximum=512,
    )
    context = _canonical_sha256(context_digest, "context_digest")
    reasons: list[str] = []

    observed_operation: str | None = None
    if isinstance(observed_operation_id, str):
        candidate_operation = observed_operation_id.strip()
        if (
            candidate_operation
            and candidate_operation == observed_operation_id
            and len(candidate_operation) <= 512
            and not any(
                ord(ch) < 32 or ord(ch) == 127
                for ch in candidate_operation
            )
        ):
            observed_operation = candidate_operation
    if observed_operation is None:
        reasons.append("operation_identity_missing")
    elif observed_operation != operation:
        reasons.append("operation_identity_mismatch")

    observed: str | None = None
    if isinstance(observed_execution_id, str):
        candidate = observed_execution_id.strip()
        if (
            candidate
            and candidate == observed_execution_id
            and len(candidate) <= 512
            and not any(
                ord(ch) < 32 or ord(ch) == 127
                for ch in candidate
            )
        ):
            observed = candidate
    if observed is None:
        reasons.append("execution_identity_missing")
    elif observed != expected_execution:
        reasons.append("execution_identity_mismatch")

    verification_hash: str | None = None
    if isinstance(verification, str):
        verification_value = verification.strip()
        if (
            verification_value
            and verification_value == verification
            and len(verification_value) <= 2048
            and not any(
                ord(ch) < 32 or ord(ch) == 127
                for ch in verification_value
            )
            and (
                verification_value == "verified"
                or verification_value.startswith("verification:")
            )
        ):
            verification_hash = _hash_ref(verification_value)
        else:
            reasons.append("verification_not_accepted")
    else:
        reasons.append("verification_missing")

    output_digest: str | None = None
    output_size = 0
    if isinstance(final_output, str) and final_output.strip():
        encoded_output = final_output.encode("utf-8")
        output_size = len(encoded_output)
        if output_size > effective_policy.max_output_utf8_bytes:
            reasons.append("output_size_exceeded")
        else:
            output_digest = hashlib.sha256(encoded_output).hexdigest()
    else:
        reasons.append("output_missing")

    provider_values, provider_reasons = _normalize_live_refs(
        provider_receipts,
        "provider_receipt",
        maximum_count=effective_policy.max_receipt_refs,
        required_prefix="provider:",
    )
    tool_values, tool_reasons = _normalize_live_refs(
        tool_receipts,
        "tool_receipt",
        maximum_count=effective_policy.max_receipt_refs,
    )
    evidence_values, evidence_reasons = _normalize_live_refs(
        evidence_refs,
        "evidence_ref",
        maximum_count=effective_policy.max_receipt_refs,
    )
    reasons.extend(provider_reasons)
    reasons.extend(tool_reasons)
    reasons.extend(evidence_reasons)
    if effective_policy.require_provider_receipt and not provider_values:
        reasons.append("provider_receipt_missing")

    claim_evidence_digest: str | None = None
    if claim_evidence is not None:
        if not isinstance(claim_evidence, LiveClaimEvidenceBinding):
            raise TypeError("claim_evidence must be LiveClaimEvidenceBinding or None")
        claim_evidence_digest = claim_evidence.digest
        if claim_evidence.operation_id != operation:
            reasons.append("claim_evidence_operation_mismatch")
        if claim_evidence.context_digest != context:
            reasons.append("claim_evidence_context_mismatch")
        if not claim_evidence.accepted:
            reasons.append("claim_evidence_rejected")
            reasons.extend(
                "claim_evidence:" + reason for reason in claim_evidence.reasons
            )
    elif effective_policy.require_structured_claim_evidence:
        reasons.append("claim_evidence_missing")

    normalized_reasons = tuple(sorted(set(reasons)))
    return LiveResponseAcceptanceReceipt(
        policy_id=effective_policy.policy_id,
        operation_id=operation,
        observed_operation_id=observed_operation,
        expected_execution_id=expected_execution,
        observed_execution_id=observed,
        context_digest=context,
        verification_ref_hash=verification_hash,
        output_sha256=output_digest,
        output_utf8_bytes=output_size,
        provider_receipt_ref_hashes=tuple(
            _hash_ref(value) for value in provider_values
        ),
        tool_receipt_ref_hashes=tuple(
            _hash_ref(value) for value in tool_values
        ),
        evidence_ref_hashes=tuple(
            _hash_ref(value) for value in evidence_values
        ),
        claim_evidence_digest=claim_evidence_digest,
        accepted=not normalized_reasons,
        reasons=normalized_reasons,
    )


__all__ = [
    "LIVE_RESPONSE_ACCEPTANCE_SCHEMA_VERSION",
    "LiveClaimEvidenceBinding",
    "LiveResponseAcceptancePolicy",
    "LiveResponseAcceptanceReceipt",
    "ResponseAcceptanceDecision",
    "ResponseAcceptanceError",
    "ResponseAcceptancePolicy",
    "bind_live_claim_evidence",
    "evaluate_live_response_acceptance",
    "evaluate_response_acceptance",
]

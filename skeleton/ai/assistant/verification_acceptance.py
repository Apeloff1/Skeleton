"""Deterministic AI-chat acceptance profiles over canonical verification receipts.

This module is deliberately an adapter, not a verification engine.  It never
generates claims, retrieves evidence, calls models, or mutates transcript state.
Canonical verification remains owned by skeleton.contracts.verification and the
verification runtimes that produce VerificationReceipt records.

The chat layer uses these profiles only to decide whether an already-produced
set of receipts is sufficient for response promotion, must be rejected, or must
be quarantined for review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Iterable, Sequence

from skeleton.contracts.verification import (
    VerificationLevel,
    VerificationOutcome,
    VerificationReceipt,
)


CHAT_VERIFICATION_ACCEPTANCE_SCHEMA_VERSION = 1


class ChatVerificationAcceptanceError(ValueError):
    """Verification evidence is malformed or insufficient for chat promotion."""


class ChatVerificationDisposition(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    QUARANTINE = "quarantine"


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise ChatVerificationAcceptanceError(f"{field} must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized)
    ):
        raise ChatVerificationAcceptanceError(f"{field} is not canonical")
    return normalized


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ChatVerificationAcceptanceError(
            f"{field} must be timezone-aware datetime"
        )
    return value.astimezone(timezone.utc)


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ChatVerificationAcceptanceError(
            "verification acceptance data is not deterministic JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ChatVerificationProfile:
    """Minimum canonical receipt evidence required by one chat risk tier."""

    profile_id: str
    minimum_level: VerificationLevel | int = VerificationLevel.STRUCTURAL
    allowed_outcomes: tuple[VerificationOutcome | str, ...] = (
        VerificationOutcome.PASSED,
    )
    quarantine_outcomes: tuple[VerificationOutcome | str, ...] = (
        VerificationOutcome.CONTESTED,
    )
    required_modes: tuple[str, ...] = ()
    require_policy_satisfied: bool = True
    require_supporting_evidence: bool = False
    require_independent_receipt: bool = False
    require_postcondition_observation: bool = False
    max_receipt_age_s: float | None = None
    schema_version: int = CHAT_VERIFICATION_ACCEPTANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CHAT_VERIFICATION_ACCEPTANCE_SCHEMA_VERSION:
            raise ChatVerificationAcceptanceError(
                "verification profile schema version drifted"
            )
        object.__setattr__(
            self,
            "profile_id",
            _text(self.profile_id, "profile_id", maximum=256),
        )
        try:
            object.__setattr__(
                self,
                "minimum_level",
                VerificationLevel(self.minimum_level),
            )
        except ValueError as exc:
            raise ChatVerificationAcceptanceError(
                "minimum_level is invalid"
            ) from exc

        def normalize_outcomes(
            values: Sequence[VerificationOutcome | str],
            field: str,
        ) -> tuple[VerificationOutcome, ...]:
            result: list[VerificationOutcome] = []
            for raw in values:
                try:
                    item = VerificationOutcome(raw)
                except ValueError as exc:
                    raise ChatVerificationAcceptanceError(
                        f"{field} contains invalid outcome"
                    ) from exc
                if item not in result:
                    result.append(item)
            return tuple(result)

        allowed = normalize_outcomes(self.allowed_outcomes, "allowed_outcomes")
        quarantine = normalize_outcomes(
            self.quarantine_outcomes,
            "quarantine_outcomes",
        )
        if not allowed:
            raise ChatVerificationAcceptanceError(
                "allowed_outcomes must not be empty"
            )
        overlap = set(allowed).intersection(quarantine)
        if overlap:
            raise ChatVerificationAcceptanceError(
                "allowed and quarantine outcomes must not overlap"
            )
        object.__setattr__(self, "allowed_outcomes", allowed)
        object.__setattr__(self, "quarantine_outcomes", quarantine)

        modes: list[str] = []
        for raw in self.required_modes:
            mode = _text(raw, "required_mode", maximum=128)
            if mode not in modes:
                modes.append(mode)
        object.__setattr__(self, "required_modes", tuple(modes))

        for field in (
            "require_policy_satisfied",
            "require_supporting_evidence",
            "require_independent_receipt",
            "require_postcondition_observation",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ChatVerificationAcceptanceError(
                    f"{field} must be boolean"
                )
        if self.max_receipt_age_s is not None:
            if (
                isinstance(self.max_receipt_age_s, bool)
                or not isinstance(self.max_receipt_age_s, (int, float))
                or float(self.max_receipt_age_s) < 0
            ):
                raise ChatVerificationAcceptanceError(
                    "max_receipt_age_s must be non-negative numeric"
                )
            object.__setattr__(
                self,
                "max_receipt_age_s",
                float(self.max_receipt_age_s),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "minimum_level": int(self.minimum_level),
            "allowed_outcomes": [
                item.value for item in self.allowed_outcomes
            ],
            "quarantine_outcomes": [
                item.value for item in self.quarantine_outcomes
            ],
            "required_modes": list(self.required_modes),
            "require_policy_satisfied": self.require_policy_satisfied,
            "require_supporting_evidence": self.require_supporting_evidence,
            "require_independent_receipt": self.require_independent_receipt,
            "require_postcondition_observation":
                self.require_postcondition_observation,
            "max_receipt_age_s": self.max_receipt_age_s,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


CHAT_VERIFICATION_PROFILES: dict[str, ChatVerificationProfile] = {
    "structural": ChatVerificationProfile(
        profile_id="chat-verification/structural-v1",
        minimum_level=VerificationLevel.STRUCTURAL,
        require_supporting_evidence=False,
    ),
    "grounded": ChatVerificationProfile(
        profile_id="chat-verification/grounded-v1",
        minimum_level=VerificationLevel.EVIDENCE,
        required_modes=("structural", "evidence"),
        require_supporting_evidence=True,
        max_receipt_age_s=3600.0,
    ),
    "high_assurance": ChatVerificationProfile(
        profile_id="chat-verification/high-assurance-v1",
        minimum_level=VerificationLevel.INDEPENDENT,
        required_modes=("structural", "evidence", "independent"),
        require_supporting_evidence=True,
        require_independent_receipt=True,
        max_receipt_age_s=1800.0,
    ),
    "action_postcondition": ChatVerificationProfile(
        profile_id="chat-verification/action-postcondition-v1",
        minimum_level=VerificationLevel.POSTCONDITION,
        required_modes=(
            "structural",
            "evidence",
            "independent",
            "postcondition",
        ),
        require_supporting_evidence=True,
        require_independent_receipt=True,
        require_postcondition_observation=True,
        max_receipt_age_s=900.0,
    ),
}


@dataclass(frozen=True, slots=True)
class ChatVerificationAcceptanceDecision:
    """Content-minimized deterministic decision over canonical receipts."""

    profile_id: str
    profile_digest: str
    operation_id: str
    execution_id: str
    disposition: ChatVerificationDisposition
    reasons: tuple[str, ...]
    receipt_digests: tuple[str, ...]
    claim_ids: tuple[str, ...]
    independent_receipt_count: int
    postcondition_observation_count: int
    schema_version: int = CHAT_VERIFICATION_ACCEPTANCE_SCHEMA_VERSION
    authority_scope: str = "chat-verification-acceptance-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != CHAT_VERIFICATION_ACCEPTANCE_SCHEMA_VERSION:
            raise ChatVerificationAcceptanceError(
                "verification decision schema version drifted"
            )
        object.__setattr__(
            self,
            "profile_id",
            _text(self.profile_id, "profile_id", maximum=256),
        )
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=512),
        )
        object.__setattr__(
            self,
            "execution_id",
            _text(self.execution_id, "execution_id", maximum=512),
        )
        if (
            len(self.profile_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.profile_digest)
        ):
            raise ChatVerificationAcceptanceError(
                "profile_digest must be lowercase sha256"
            )
        if not isinstance(self.disposition, ChatVerificationDisposition):
            object.__setattr__(
                self,
                "disposition",
                ChatVerificationDisposition(str(self.disposition)),
            )
        normalized_reasons = tuple(
            sorted(
                {
                    _text(reason, "reason", maximum=128)
                    for reason in self.reasons
                }
            )
        )
        object.__setattr__(self, "reasons", normalized_reasons)
        if self.disposition is ChatVerificationDisposition.ACCEPT and self.reasons:
            raise ChatVerificationAcceptanceError(
                "accepted verification decision cannot retain rejection reasons"
            )
        if self.disposition is not ChatVerificationDisposition.ACCEPT and not self.reasons:
            raise ChatVerificationAcceptanceError(
                "non-accepted verification decision requires reasons"
            )
        digests = tuple(self.receipt_digests)
        if not digests:
            raise ChatVerificationAcceptanceError(
                "verification decision requires receipt digests"
            )
        if len(set(digests)) != len(digests):
            raise ChatVerificationAcceptanceError(
                "verification receipt digests must be unique"
            )
        for digest in digests:
            if (
                len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise ChatVerificationAcceptanceError(
                    "receipt digest must be lowercase sha256"
                )
        object.__setattr__(self, "receipt_digests", tuple(sorted(digests)))
        claims = tuple(self.claim_ids)
        if len(set(claims)) != len(claims):
            raise ChatVerificationAcceptanceError(
                "verification claim identities must be unique"
            )
        object.__setattr__(self, "claim_ids", tuple(sorted(claims)))
        for field in (
            "independent_receipt_count",
            "postcondition_observation_count",
        ):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ChatVerificationAcceptanceError(
                    f"{field} must be non-negative integer"
                )
        if self.authority_scope != "chat-verification-acceptance-only":
            raise ChatVerificationAcceptanceError(
                "verification acceptance authority scope escalated"
            )
        if self.production_authority is not False:
            raise ChatVerificationAcceptanceError(
                "verification acceptance cannot publish or commit content"
            )

    @property
    def accepted(self) -> bool:
        return self.disposition is ChatVerificationDisposition.ACCEPT

    @property
    def quarantined(self) -> bool:
        return self.disposition is ChatVerificationDisposition.QUARANTINE

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_digest": self.profile_digest,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "receipt_digests": list(self.receipt_digests),
            "claim_ids": list(self.claim_ids),
            "independent_receipt_count": self.independent_receipt_count,
            "postcondition_observation_count":
                self.postcondition_observation_count,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    @property
    def reference(self) -> str:
        return "chat-verification-acceptance-sha256:" + self.digest


def evaluate_chat_verification(
    *,
    profile: ChatVerificationProfile,
    receipts: Sequence[VerificationReceipt] | Iterable[VerificationReceipt],
    operation_id: str,
    execution_id: str,
    finalized_at: datetime,
) -> ChatVerificationAcceptanceDecision:
    """Evaluate canonical verification receipts against a chat acceptance tier."""

    if not isinstance(profile, ChatVerificationProfile):
        raise TypeError("profile must be ChatVerificationProfile")
    operation = _text(operation_id, "operation_id", maximum=512)
    execution = _text(execution_id, "execution_id", maximum=512)
    now = _utc(finalized_at, "finalized_at")
    values = tuple(receipts)
    if not values:
        raise ChatVerificationAcceptanceError(
            "verification receipt set must not be empty"
        )
    if any(not isinstance(item, VerificationReceipt) for item in values):
        raise TypeError("receipts must contain VerificationReceipt")

    reasons: list[str] = []
    quarantine = False
    seen_receipts: set[str] = set()
    seen_claims: set[str] = set()
    independent_count = 0
    postcondition_ids: set[str] = set()

    for receipt in values:
        if receipt.receipt_id in seen_receipts:
            reasons.append("duplicate_verification_receipt")
        seen_receipts.add(receipt.receipt_id)

        if receipt.claim_id in seen_claims:
            reasons.append("duplicate_claim_verification")
        seen_claims.add(receipt.claim_id)

        if receipt.operation_id != operation:
            reasons.append("verification_operation_identity_mismatch")
        if receipt.execution_id != execution:
            reasons.append("verification_execution_identity_mismatch")

        if receipt.verified_at > now:
            reasons.append("verification_receipt_from_future")
        elif profile.max_receipt_age_s is not None:
            age = (now - receipt.verified_at).total_seconds()
            if age > profile.max_receipt_age_s:
                reasons.append("verification_receipt_stale")

        if receipt.outcome in profile.quarantine_outcomes:
            reasons.append("verification_outcome_requires_quarantine")
            quarantine = True
        elif receipt.outcome not in profile.allowed_outcomes:
            reasons.append("verification_outcome_not_accepted")

        if (
            profile.require_policy_satisfied
            and not receipt.policy_satisfied
        ):
            reasons.append("verification_policy_not_satisfied")
        if receipt.policy_level < profile.minimum_level:
            reasons.append("verification_level_below_profile")

        missing_modes = set(profile.required_modes).difference(
            receipt.required_modes
        )
        if missing_modes:
            reasons.append("verification_required_mode_missing")

        if (
            profile.require_supporting_evidence
            and not receipt.supporting_evidence_ids
        ):
            reasons.append("verification_supporting_evidence_missing")

        if receipt.independent:
            independent_count += 1
        postcondition_ids.update(receipt.postcondition_observation_ids)

    if profile.require_independent_receipt and independent_count < 1:
        reasons.append("independent_verification_receipt_missing")
    if (
        profile.require_postcondition_observation
        and not postcondition_ids
    ):
        reasons.append("postcondition_observation_missing")

    normalized_reasons = tuple(sorted(set(reasons)))
    if quarantine:
        disposition = ChatVerificationDisposition.QUARANTINE
    elif normalized_reasons:
        disposition = ChatVerificationDisposition.REJECT
    else:
        disposition = ChatVerificationDisposition.ACCEPT

    return ChatVerificationAcceptanceDecision(
        profile_id=profile.profile_id,
        profile_digest=profile.digest,
        operation_id=operation,
        execution_id=execution,
        disposition=disposition,
        reasons=normalized_reasons,
        receipt_digests=tuple(receipt.digest for receipt in values),
        claim_ids=tuple(receipt.claim_id for receipt in values),
        independent_receipt_count=independent_count,
        postcondition_observation_count=len(postcondition_ids),
    )


__all__ = [
    "CHAT_VERIFICATION_ACCEPTANCE_SCHEMA_VERSION",
    "CHAT_VERIFICATION_PROFILES",
    "ChatVerificationAcceptanceDecision",
    "ChatVerificationAcceptanceError",
    "ChatVerificationDisposition",
    "ChatVerificationProfile",
    "evaluate_chat_verification",
]

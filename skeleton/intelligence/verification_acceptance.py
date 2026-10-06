"""Verification acceptance and quarantine authority for October 2026.

The existing verification runtimes answer what the verifier concluded.
This module answers the separate promotion question: may that verification be
trusted for finalization? It is deliberately non-executing.

Key invariants:

* canonical risk/action policy is a floor and cannot be weakened by a caller;
* a verification receipt must bind the exact claim digest and tenant;
* future or internally contradictory passed receipts are quarantined;
* stale receipts fail closed under an explicit acceptance profile;
* independent verification requires an identity-bound proof of the independent
  check, not merely a boolean independent flag;
* high/critical model-origin claims require a distinct authority domain and
  process for the independent verifier; critical profiles can require a
  distinct provider as well;
* acceptance/quarantine decisions are deterministic and digest-bound.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from uuid import UUID

from skeleton.contracts.verification import (
    VerificationCheck,
    VerificationClaim,
    VerificationLevel,
    VerificationOutcome,
    VerificationReceipt,
    VerificationRisk,
)
from skeleton.intelligence.verification_policy import (
    select_verification_policy,
)


ACCEPTANCE_SCHEMA_VERSION = 1
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#@-]{0,255}$")


class VerificationAcceptanceError(ValueError):
    """Verification acceptance evidence is malformed."""


class AcceptanceDisposition(str, Enum):
    ACCEPT = "accept"
    ABSTAIN = "abstain"
    BLOCK = "block"
    QUARANTINE = "quarantine"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise VerificationAcceptanceError(
            "acceptance evidence is not canonical-json encodable"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise VerificationAcceptanceError(
            f"{field} must be a canonical token"
        )
    return value


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise VerificationAcceptanceError(f"{field} must be UUID text")
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise VerificationAcceptanceError(
            f"{field} must be a canonical UUID"
        ) from exc
    if str(parsed) != value:
        raise VerificationAcceptanceError(
            f"{field} must be a canonical UUID"
        )
    return value


def _utc(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise VerificationAcceptanceError(
            f"{field} must be timezone-aware datetime"
        )
    return value.astimezone(timezone.utc)


def _finite_nonnegative(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise VerificationAcceptanceError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise VerificationAcceptanceError(
            f"{field} must be finite and non-negative"
        )
    return result


@dataclass(frozen=True, slots=True)
class VerificationActorIdentity:
    """Observable identity used to prove verifier separation."""

    actor_id: str
    authority_domain: str
    process_id: str
    provider_id: str | None = None
    model_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "actor_id",
            _token(self.actor_id, "actor_id"),
        )
        object.__setattr__(
            self,
            "authority_domain",
            _token(self.authority_domain, "authority_domain"),
        )
        object.__setattr__(
            self,
            "process_id",
            _token(self.process_id, "process_id"),
        )
        if self.provider_id is not None:
            object.__setattr__(
                self,
                "provider_id",
                _token(self.provider_id, "provider_id"),
            )
        if self.model_id is not None:
            object.__setattr__(
                self,
                "model_id",
                _token(self.model_id, "model_id"),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "authority_domain": self.authority_domain,
            "process_id": self.process_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class IndependentVerificationProof:
    """Digest-bound proof connecting one independent check to actor identity."""

    claim_id: str
    tenant_id: str
    receipt_digest: str
    independent_check_id: str
    independent_check_digest: str
    independent_check_verified_at: datetime
    generator: VerificationActorIdentity
    verifier: VerificationActorIdentity
    schema_version: int = ACCEPTANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "claim_id",
            _uuid(self.claim_id, "claim_id"),
        )
        if (
            not isinstance(self.receipt_digest, str)
            or len(self.receipt_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.receipt_digest)
        ):
            raise VerificationAcceptanceError(
                "receipt_digest must be lowercase sha256"
            )
        object.__setattr__(
            self,
            "independent_check_id",
            _uuid(self.independent_check_id, "independent_check_id"),
        )
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise VerificationAcceptanceError(
                "tenant_id must be non-empty"
            )
        if (
            not isinstance(self.independent_check_digest, str)
            or len(self.independent_check_digest) != 64
            or any(
                ch not in "0123456789abcdef"
                for ch in self.independent_check_digest
            )
        ):
            raise VerificationAcceptanceError(
                "independent_check_digest must be lowercase sha256"
            )
        object.__setattr__(
            self,
            "independent_check_verified_at",
            _utc(
                self.independent_check_verified_at,
                "independent_check_verified_at",
            ),
        )
        if not isinstance(self.generator, VerificationActorIdentity):
            raise VerificationAcceptanceError(
                "generator must be VerificationActorIdentity"
            )
        if not isinstance(self.verifier, VerificationActorIdentity):
            raise VerificationAcceptanceError(
                "verifier must be VerificationActorIdentity"
            )
        if self.schema_version != ACCEPTANCE_SCHEMA_VERSION:
            raise VerificationAcceptanceError(
                "unsupported independence proof schema"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "tenant_id": self.tenant_id,
            "receipt_digest": self.receipt_digest,
            "independent_check_id": self.independent_check_id,
            "independent_check_digest": self.independent_check_digest,
            "independent_check_verified_at":
                self.independent_check_verified_at.isoformat(),
            "generator": self.generator.as_dict(),
            "verifier": self.verifier.as_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


def build_independent_verification_proof(
    *,
    claim: VerificationClaim,
    receipt: VerificationReceipt,
    independent_check: VerificationCheck,
    generator: VerificationActorIdentity,
    verifier: VerificationActorIdentity,
) -> IndependentVerificationProof:
    """Bind an already-produced independent check to observable actor identity."""

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    if not isinstance(receipt, VerificationReceipt):
        raise TypeError("receipt must be VerificationReceipt")
    if not isinstance(independent_check, VerificationCheck):
        raise TypeError("independent_check must be VerificationCheck")
    if (
        receipt.claim_id != claim.claim_id
        or receipt.claim_digest != claim.digest
        or receipt.tenant_id != claim.tenant_id
    ):
        raise VerificationAcceptanceError(
            "receipt does not bind the canonical claim"
        )
    if not receipt.independent:
        raise VerificationAcceptanceError(
            "receipt does not claim independent verification"
        )
    if independent_check.claim_id != claim.claim_id:
        raise VerificationAcceptanceError(
            "independent check belongs to another claim"
        )
    if independent_check.tenant_id != claim.tenant_id:
        raise VerificationAcceptanceError(
            "independent check belongs to another tenant"
        )
    if not independent_check.independent:
        raise VerificationAcceptanceError(
            "independent check lacks independent=true"
        )
    if independent_check.level < VerificationLevel.INDEPENDENT:
        raise VerificationAcceptanceError(
            "independent check level is too weak"
        )
    if independent_check.outcome is not VerificationOutcome.PASSED:
        raise VerificationAcceptanceError(
            "independent check must have passed"
        )
    if independent_check.verifier_id != verifier.actor_id:
        raise VerificationAcceptanceError(
            "verifier identity does not bind independent check"
        )
    return IndependentVerificationProof(
        claim_id=claim.claim_id,
        tenant_id=claim.tenant_id,
        receipt_digest=receipt.digest,
        independent_check_id=independent_check.check_id,
        independent_check_digest=independent_check.digest,
        independent_check_verified_at=independent_check.verified_at,
        generator=generator,
        verifier=verifier,
    )


@dataclass(frozen=True, slots=True)
class VerificationAcceptanceProfile:
    profile_id: str
    minimum_level: VerificationLevel | int = VerificationLevel.STRUCTURAL
    max_receipt_age_s: float = 86_400.0
    max_independent_check_age_s: float = 86_400.0
    require_distinct_authority_domain: bool = True
    require_distinct_process: bool = True
    require_distinct_provider_for_critical: bool = True
    quarantine_on_binding_mismatch: bool = True
    quarantine_on_future_evidence: bool = True
    schema_version: int = ACCEPTANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _token(self.profile_id, "profile_id"),
        )
        try:
            object.__setattr__(
                self,
                "minimum_level",
                VerificationLevel(self.minimum_level),
            )
        except ValueError as exc:
            raise VerificationAcceptanceError(
                "minimum_level is invalid"
            ) from exc
        object.__setattr__(
            self,
            "max_receipt_age_s",
            _finite_nonnegative(
                self.max_receipt_age_s,
                "max_receipt_age_s",
            ),
        )
        object.__setattr__(
            self,
            "max_independent_check_age_s",
            _finite_nonnegative(
                self.max_independent_check_age_s,
                "max_independent_check_age_s",
            ),
        )
        for field in (
            "require_distinct_authority_domain",
            "require_distinct_process",
            "require_distinct_provider_for_critical",
            "quarantine_on_binding_mismatch",
            "quarantine_on_future_evidence",
        ):
            if not isinstance(getattr(self, field), bool):
                raise VerificationAcceptanceError(
                    f"{field} must be boolean"
                )
        if self.schema_version != ACCEPTANCE_SCHEMA_VERSION:
            raise VerificationAcceptanceError(
                "unsupported acceptance profile schema"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "minimum_level": int(self.minimum_level),
            "max_receipt_age_s": self.max_receipt_age_s,
            "max_independent_check_age_s":
                self.max_independent_check_age_s,
            "require_distinct_authority_domain":
                self.require_distinct_authority_domain,
            "require_distinct_process": self.require_distinct_process,
            "require_distinct_provider_for_critical":
                self.require_distinct_provider_for_critical,
            "quarantine_on_binding_mismatch":
                self.quarantine_on_binding_mismatch,
            "quarantine_on_future_evidence":
                self.quarantine_on_future_evidence,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


def default_acceptance_profile(
    claim: VerificationClaim,
) -> VerificationAcceptanceProfile:
    """Risk-scaled receipt freshness and independence profile."""

    if not isinstance(claim, VerificationClaim):
        raise TypeError("claim must be VerificationClaim")
    if claim.risk is VerificationRisk.LOW:
        level = VerificationLevel.STRUCTURAL
        max_age = 86_400.0
    elif claim.risk is VerificationRisk.MEDIUM:
        level = VerificationLevel.EVIDENCE
        max_age = 21_600.0
    elif claim.risk is VerificationRisk.HIGH:
        level = VerificationLevel.INDEPENDENT
        max_age = 3_600.0
    else:
        level = VerificationLevel.POSTCONDITION
        max_age = 900.0
    return VerificationAcceptanceProfile(
        profile_id="verification-acceptance-" + claim.risk.value + "-v1",
        minimum_level=level,
        max_receipt_age_s=max_age,
        max_independent_check_age_s=max_age,
    )


@dataclass(frozen=True, slots=True)
class VerificationAcceptanceDecision:
    disposition: AcceptanceDisposition | str
    reasons: tuple[str, ...]
    canonical_policy_level: VerificationLevel | int
    canonical_required_modes: tuple[str, ...]
    profile_digest: str
    receipt_digest: str | None
    independence_proof_digest: str | None
    checked_at: datetime
    authority_scope: str = "verification-acceptance-only"
    production_authority: bool = False
    schema_version: int = ACCEPTANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "disposition",
                AcceptanceDisposition(self.disposition),
            )
            object.__setattr__(
                self,
                "canonical_policy_level",
                VerificationLevel(self.canonical_policy_level),
            )
        except ValueError as exc:
            raise VerificationAcceptanceError(
                "acceptance decision enum is invalid"
            ) from exc
        object.__setattr__(
            self,
            "checked_at",
            _utc(self.checked_at, "checked_at"),
        )
        if self.authority_scope != "verification-acceptance-only":
            raise VerificationAcceptanceError(
                "acceptance authority scope escalated"
            )
        if self.production_authority is not False:
            raise VerificationAcceptanceError(
                "acceptance decision cannot publish or execute"
            )
        if self.schema_version != ACCEPTANCE_SCHEMA_VERSION:
            raise VerificationAcceptanceError(
                "unsupported acceptance decision schema"
            )

    @property
    def accepted(self) -> bool:
        return self.disposition is AcceptanceDisposition.ACCEPT

    @property
    def quarantined(self) -> bool:
        return self.disposition is AcceptanceDisposition.QUARANTINE

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "canonical_policy_level": int(self.canonical_policy_level),
            "canonical_required_modes": list(
                self.canonical_required_modes
            ),
            "profile_digest": self.profile_digest,
            "receipt_digest": self.receipt_digest,
            "independence_proof_digest": self.independence_proof_digest,
            "checked_at": self.checked_at.isoformat(),
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


def _failure_disposition(
    claim: VerificationClaim,
    *,
    quarantine: bool = False,
) -> AcceptanceDisposition:
    if quarantine:
        return AcceptanceDisposition.QUARANTINE
    if claim.risk in {
        VerificationRisk.HIGH,
        VerificationRisk.CRITICAL,
    }:
        return AcceptanceDisposition.BLOCK
    return AcceptanceDisposition.ABSTAIN


class VerificationAcceptanceGate:
    """Validate verification authority before a result can be finalized."""

    def evaluate(
        self,
        claim: VerificationClaim,
        *,
        receipt: VerificationReceipt | None,
        checked_at: datetime,
        profile: VerificationAcceptanceProfile | None = None,
        independence_proof: IndependentVerificationProof | None = None,
        action_effect: str | None = None,
        externally_observable_action: bool = False,
    ) -> VerificationAcceptanceDecision:
        if not isinstance(claim, VerificationClaim):
            raise TypeError("claim must be VerificationClaim")
        instant = _utc(checked_at, "checked_at")
        acceptance = profile or default_acceptance_profile(claim)
        if not isinstance(
            acceptance,
            VerificationAcceptanceProfile,
        ):
            raise TypeError(
                "profile must be VerificationAcceptanceProfile"
            )

        canonical = select_verification_policy(
            claim,
            action_effect=action_effect,
            externally_observable_action=externally_observable_action,
        )
        reasons: list[str] = []
        quarantine = False
        required_level = max(
            canonical.level,
            acceptance.minimum_level,
        )

        if receipt is None:
            reasons.append("verification_receipt_missing")
            disposition = _failure_disposition(claim)
            return VerificationAcceptanceDecision(
                disposition=disposition,
                reasons=tuple(reasons),
                canonical_policy_level=required_level,
                canonical_required_modes=canonical.required_modes,
                profile_digest=acceptance.digest,
                receipt_digest=None,
                independence_proof_digest=None,
                checked_at=instant,
            )
        if not isinstance(receipt, VerificationReceipt):
            raise TypeError("receipt must be VerificationReceipt")

        binding_mismatch = (
            receipt.claim_id != claim.claim_id
            or receipt.claim_digest != claim.digest
            or receipt.tenant_id != claim.tenant_id
        )
        if binding_mismatch:
            reasons.append("verification_receipt_binding_mismatch")
            quarantine = acceptance.quarantine_on_binding_mismatch

        if receipt.verified_at > instant:
            reasons.append("verification_receipt_from_future")
            quarantine = (
                quarantine
                or acceptance.quarantine_on_future_evidence
            )
        else:
            age = (instant - receipt.verified_at).total_seconds()
            if age > acceptance.max_receipt_age_s:
                reasons.append("verification_receipt_stale")

        if receipt.policy_level < required_level:
            reasons.append("verification_level_below_required_floor")
        if not set(canonical.required_modes).issubset(
            set(receipt.required_modes)
        ):
            reasons.append("verification_required_modes_missing")
        if not receipt.policy_satisfied:
            reasons.append("verification_policy_not_satisfied")
        if receipt.outcome is not VerificationOutcome.PASSED:
            reasons.append("verification_outcome_not_passed")
        if receipt.contradicting_evidence_ids:
            reasons.append("passed_receipt_contains_contradiction")
            quarantine = True

        independent_required = (
            required_level >= VerificationLevel.INDEPENDENT
        )
        proof_digest: str | None = None
        if independent_required:
            if not receipt.independent:
                reasons.append("independent_verification_flag_missing")
            if independence_proof is None:
                reasons.append("independent_identity_proof_missing")
            else:
                if not isinstance(
                    independence_proof,
                    IndependentVerificationProof,
                ):
                    raise TypeError(
                        "independence_proof must be IndependentVerificationProof"
                    )
                proof_digest = independence_proof.digest
                if (
                    independence_proof.claim_id != claim.claim_id
                    or independence_proof.tenant_id != claim.tenant_id
                    or independence_proof.receipt_digest != receipt.digest
                ):
                    reasons.append(
                        "independent_identity_proof_binding_mismatch"
                    )
                    quarantine = True
                if (
                    independence_proof.independent_check_verified_at
                    > receipt.verified_at
                ):
                    reasons.append(
                        "independent_check_postdates_receipt"
                    )
                    quarantine = True
                if (
                    independence_proof.independent_check_verified_at
                    > instant
                ):
                    reasons.append(
                        "independent_check_from_future"
                    )
                    quarantine = True
                else:
                    independent_age = (
                        instant
                        - independence_proof.independent_check_verified_at
                    ).total_seconds()
                    if (
                        independent_age
                        > acceptance.max_independent_check_age_s
                    ):
                        reasons.append("independent_check_stale")

                generator = independence_proof.generator
                verifier = independence_proof.verifier
                if generator.actor_id == verifier.actor_id:
                    reasons.append("independent_actor_identity_collides")
                if (
                    acceptance.require_distinct_authority_domain
                    and generator.authority_domain
                    == verifier.authority_domain
                ):
                    reasons.append(
                        "independent_authority_domain_collides"
                    )
                if (
                    acceptance.require_distinct_process
                    and generator.process_id == verifier.process_id
                ):
                    reasons.append("independent_process_collides")
                if (
                    claim.risk is VerificationRisk.CRITICAL
                    and acceptance.require_distinct_provider_for_critical
                    and generator.provider_id is not None
                    and verifier.provider_id is not None
                    and generator.provider_id == verifier.provider_id
                ):
                    reasons.append(
                        "critical_independent_provider_collides"
                    )

        disposition = (
            AcceptanceDisposition.ACCEPT
            if not reasons
            else _failure_disposition(
                claim,
                quarantine=quarantine,
            )
        )
        return VerificationAcceptanceDecision(
            disposition=disposition,
            reasons=tuple(sorted(set(reasons))),
            canonical_policy_level=required_level,
            canonical_required_modes=canonical.required_modes,
            profile_digest=acceptance.digest,
            receipt_digest=receipt.digest,
            independence_proof_digest=proof_digest,
            checked_at=instant,
        )


__all__ = [
    "ACCEPTANCE_SCHEMA_VERSION",
    "AcceptanceDisposition",
    "IndependentVerificationProof",
    "VerificationAcceptanceDecision",
    "VerificationAcceptanceError",
    "VerificationAcceptanceGate",
    "VerificationAcceptanceProfile",
    "VerificationActorIdentity",
    "build_independent_verification_proof",
    "default_acceptance_profile",
]

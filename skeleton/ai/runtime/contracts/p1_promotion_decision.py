"""Independent terminal P1 promotion decision.

P1-PROM-03 is the terminal decision contract. It never mutates masterplan
maturity. A promotion intent must bind the exact PROM-02 decision and the full
canonical deferred-volume set. A PROMOTE disposition additionally requires an
independently verified detached Ed25519 signature over the exact canonical
intent bytes. When no external signature is supplied, callers may record an
explicit REJECT disposition instead of fabricating promotion authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_failure_journeys import P1FailureJourneyDecision


P1_PROMOTION_DECISION_SCHEMA_VERSION = 1
P1_PROMOTION_DECISION_TASK_ID = "P1-PROM-03"
P1_PROMOTION_DECISION_ACCOUNTABILITY_ID = "ACC-P1-PROM-03"
P1_PROMOTION_SIGNATURE_METHOD = "ed25519"
P1_PROMOTION_ALLOWED_SIGNER_TYPES = ("human", "ci", "service")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
_VOLUME_RE = re.compile(r"^VOL-[0-9]{3}$")


class P1PromotionDecisionError(ValueError):
    """Terminal promotion decision input is malformed."""


class PromotionDisposition(str, Enum):
    PROMOTE = "promote"
    REJECT = "reject"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P1PromotionDecisionError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise P1PromotionDecisionError(f"{field} must be normalized")
    return normalized


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise P1PromotionDecisionError(
            f"{field} must be lowercase git sha"
        )
    return value


def _sha64(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA64_RE.fullmatch(value):
        raise P1PromotionDecisionError(
            f"{field} must be lowercase sha256"
        )
    return value


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise P1PromotionDecisionError(
            "promotion payload must be canonical JSON"
        ) from exc


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _blockers(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise P1PromotionDecisionError(
            "explicit_blockers must be an iterable"
        )
    normalized = tuple(
        sorted({_text(item, "explicit_blocker", maximum=512) for item in values})
    )
    return normalized


def _volumes(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise P1PromotionDecisionError(
            "deferred_volume_refs must be an iterable"
        )
    normalized = tuple(sorted(set(values)))
    if not normalized:
        raise P1PromotionDecisionError(
            "deferred_volume_refs must be non-empty"
        )
    for item in normalized:
        if not isinstance(item, str) or not _VOLUME_RE.fullmatch(item):
            raise P1PromotionDecisionError(
                "deferred_volume_refs must contain canonical volume IDs"
            )
    return normalized


@dataclass(frozen=True, slots=True)
class P1PromotionIntent:
    repository: str
    commit_sha: str
    prom02_decision_digest: str
    prom02_accepted: bool
    prom01_bundle_digest: str
    prom01_promotion_ready: bool
    disposition: PromotionDisposition
    deferred_volume_refs: tuple[str, ...]
    explicit_blockers: tuple[str, ...] = ()
    signer_id: str | None = None
    signer_type: str | None = None
    signer_identity_digest: str | None = None
    public_key_fingerprint: str | None = None
    signature_method: str = P1_PROMOTION_SIGNATURE_METHOD
    task_id: str = P1_PROMOTION_DECISION_TASK_ID
    accountability_id: str = P1_PROMOTION_DECISION_ACCOUNTABILITY_ID
    schema_version: int = P1_PROMOTION_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        repository = _text(
            self.repository,
            "repository",
            maximum=256,
        )
        if repository.count("/") != 1:
            raise P1PromotionDecisionError(
                "repository must be owner/name"
            )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
        )
        for field in (
            "prom02_decision_digest",
            "prom01_bundle_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha64(getattr(self, field), field),
            )
        for field in ("prom02_accepted", "prom01_promotion_ready"):
            if not isinstance(getattr(self, field), bool):
                raise P1PromotionDecisionError(
                    f"{field} must be boolean"
                )
        try:
            object.__setattr__(
                self,
                "disposition",
                PromotionDisposition(self.disposition),
            )
        except ValueError as exc:
            raise P1PromotionDecisionError(
                "invalid promotion disposition"
            ) from exc
        object.__setattr__(
            self,
            "deferred_volume_refs",
            _volumes(self.deferred_volume_refs),
        )
        object.__setattr__(
            self,
            "explicit_blockers",
            _blockers(self.explicit_blockers),
        )

        signature_fields = (
            self.signer_id,
            self.signer_type,
            self.signer_identity_digest,
            self.public_key_fingerprint,
        )
        any_signature_identity = any(
            value is not None for value in signature_fields
        )
        all_signature_identity = all(
            value is not None for value in signature_fields
        )
        if any_signature_identity and not all_signature_identity:
            raise P1PromotionDecisionError(
                "signer identity fields must be all present or all absent"
            )
        if all_signature_identity:
            object.__setattr__(
                self,
                "signer_id",
                _text(self.signer_id, "signer_id", maximum=256),
            )
            signer_type = _text(
                self.signer_type,
                "signer_type",
                maximum=32,
            )
            if signer_type not in P1_PROMOTION_ALLOWED_SIGNER_TYPES:
                raise P1PromotionDecisionError(
                    "signer_type must be human, ci, or service; agent signers are forbidden"
                )
            object.__setattr__(self, "signer_type", signer_type)
            object.__setattr__(
                self,
                "signer_identity_digest",
                _sha64(
                    self.signer_identity_digest,
                    "signer_identity_digest",
                ),
            )
            object.__setattr__(
                self,
                "public_key_fingerprint",
                _sha64(
                    self.public_key_fingerprint,
                    "public_key_fingerprint",
                ),
            )

        if self.signature_method != P1_PROMOTION_SIGNATURE_METHOD:
            raise P1PromotionDecisionError(
                "unsupported promotion signature method"
            )
        if self.task_id != P1_PROMOTION_DECISION_TASK_ID:
            raise P1PromotionDecisionError("task_id drift")
        if (
            self.accountability_id
            != P1_PROMOTION_DECISION_ACCOUNTABILITY_ID
        ):
            raise P1PromotionDecisionError(
                "accountability_id drift"
            )
        if self.schema_version != P1_PROMOTION_DECISION_SCHEMA_VERSION:
            raise P1PromotionDecisionError(
                "unsupported promotion decision schema"
            )

        if self.disposition is PromotionDisposition.PROMOTE:
            if self.explicit_blockers:
                raise P1PromotionDecisionError(
                    "PROMOTE intent cannot carry explicit blockers"
                )
            if not all_signature_identity:
                raise P1PromotionDecisionError(
                    "PROMOTE intent requires signer identity and key fingerprint"
                )
        elif not self.explicit_blockers:
            raise P1PromotionDecisionError(
                "REJECT intent requires explicit blockers"
            )

    @property
    def deferred_volume_digest(self) -> str:
        return _canonical_digest(list(self.deferred_volume_refs))

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "prom02_decision_digest": self.prom02_decision_digest,
            "prom02_accepted": self.prom02_accepted,
            "prom01_bundle_digest": self.prom01_bundle_digest,
            "prom01_promotion_ready": self.prom01_promotion_ready,
            "disposition": self.disposition.value,
            "deferred_volume_count": len(self.deferred_volume_refs),
            "deferred_volume_refs": list(self.deferred_volume_refs),
            "deferred_volume_digest": self.deferred_volume_digest,
            "explicit_blockers": list(self.explicit_blockers),
            "signer_id": self.signer_id,
            "signer_type": self.signer_type,
            "signer_identity_digest": self.signer_identity_digest,
            "public_key_fingerprint": self.public_key_fingerprint,
            "signature_method": self.signature_method,
            "maturity_mutation": False,
            "promotion_effect": "terminal_candidate",
        }

    @property
    def intent_digest(self) -> str:
        return _canonical_digest(self.payload())

    def signing_bytes(self) -> bytes:
        return _canonical_bytes(self.payload())

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
    ) -> "P1PromotionIntent":
        if not isinstance(raw, Mapping):
            raise TypeError("promotion intent must be a mapping")
        return cls(
            repository=raw.get("repository"),
            commit_sha=raw.get("commit_sha"),
            prom02_decision_digest=raw.get(
                "prom02_decision_digest"
            ),
            prom02_accepted=raw.get("prom02_accepted"),
            prom01_bundle_digest=raw.get("prom01_bundle_digest"),
            prom01_promotion_ready=raw.get(
                "prom01_promotion_ready"
            ),
            disposition=raw.get("disposition"),
            deferred_volume_refs=tuple(
                raw.get("deferred_volume_refs") or ()
            ),
            explicit_blockers=tuple(
                raw.get("explicit_blockers") or ()
            ),
            signer_id=raw.get("signer_id"),
            signer_type=raw.get("signer_type"),
            signer_identity_digest=raw.get(
                "signer_identity_digest"
            ),
            public_key_fingerprint=raw.get(
                "public_key_fingerprint"
            ),
            signature_method=raw.get(
                "signature_method",
                P1_PROMOTION_SIGNATURE_METHOD,
            ),
        )


@dataclass(frozen=True, slots=True)
class IndependentSignatureObservation:
    repository: str
    commit_sha: str
    intent_digest: str
    signer_id: str
    signer_type: str
    signer_identity_digest: str
    public_key_fingerprint: str
    signature_digest: str
    verifier_id: str
    verifier_digest: str
    signature_method: str
    verified: bool
    independent: bool

    def __post_init__(self) -> None:
        repository = _text(
            self.repository,
            "repository",
            maximum=256,
        )
        if repository.count("/") != 1:
            raise P1PromotionDecisionError(
                "signature repository must be owner/name"
            )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
        )
        for field in (
            "intent_digest",
            "signer_identity_digest",
            "public_key_fingerprint",
            "signature_digest",
            "verifier_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha64(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "signer_id",
            _text(self.signer_id, "signer_id", maximum=256),
        )
        signer_type = _text(
            self.signer_type,
            "signer_type",
            maximum=32,
        )
        if signer_type not in P1_PROMOTION_ALLOWED_SIGNER_TYPES:
            raise P1PromotionDecisionError(
                "signature signer_type must be human, ci, or service; agent signers are forbidden"
            )
        object.__setattr__(self, "signer_type", signer_type)
        object.__setattr__(
            self,
            "verifier_id",
            _text(self.verifier_id, "verifier_id", maximum=256),
        )
        if self.signer_id == self.verifier_id:
            raise P1PromotionDecisionError(
                "signature verifier must be independent of signer"
            )
        if self.signature_method != P1_PROMOTION_SIGNATURE_METHOD:
            raise P1PromotionDecisionError(
                "signature observation method mismatch"
            )
        if not isinstance(self.verified, bool):
            raise P1PromotionDecisionError(
                "verified must be boolean"
            )
        if not isinstance(self.independent, bool):
            raise P1PromotionDecisionError(
                "independent must be boolean"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "intent_digest": self.intent_digest,
            "signer_id": self.signer_id,
            "signer_type": self.signer_type,
            "signer_identity_digest": self.signer_identity_digest,
            "public_key_fingerprint": self.public_key_fingerprint,
            "signature_digest": self.signature_digest,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "signature_method": self.signature_method,
            "verified": self.verified,
            "independent": self.independent,
        }

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
    ) -> "IndependentSignatureObservation":
        if not isinstance(raw, Mapping):
            raise TypeError(
                "signature observation must be a mapping"
            )
        return cls(
            repository=raw.get("repository"),
            commit_sha=raw.get("commit_sha"),
            intent_digest=raw.get("intent_digest"),
            signer_id=raw.get("signer_id"),
            signer_type=raw.get("signer_type"),
            signer_identity_digest=raw.get(
                "signer_identity_digest"
            ),
            public_key_fingerprint=raw.get(
                "public_key_fingerprint"
            ),
            signature_digest=raw.get("signature_digest"),
            verifier_id=raw.get("verifier_id"),
            verifier_digest=raw.get("verifier_digest"),
            signature_method=raw.get("signature_method"),
            verified=raw.get("verified"),
            independent=raw.get("independent"),
        )


@dataclass(frozen=True, slots=True)
class P1SignedPromotionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    disposition: PromotionDisposition
    promotion_granted: bool
    signed: bool
    repository: str
    commit_sha: str
    prom02_decision_digest: str
    intent_digest: str
    deferred_volume_count: int
    deferred_volume_digest: str
    explicit_blockers: tuple[str, ...]
    signature_observation_digest: str | None
    task_id: str = P1_PROMOTION_DECISION_TASK_ID
    accountability_id: str = P1_PROMOTION_DECISION_ACCOUNTABILITY_ID
    schema_version: int = P1_PROMOTION_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise P1PromotionDecisionError(
                "accepted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise P1PromotionDecisionError(
                "reasons must contain non-empty strings"
            )
        try:
            object.__setattr__(
                self,
                "disposition",
                PromotionDisposition(self.disposition),
            )
        except ValueError as exc:
            raise P1PromotionDecisionError(
                "invalid promotion disposition"
            ) from exc
        for field in ("promotion_granted", "signed"):
            if not isinstance(getattr(self, field), bool):
                raise P1PromotionDecisionError(
                    f"{field} must be boolean"
                )
        repository = _text(
            self.repository,
            "repository",
            maximum=256,
        )
        if repository.count("/") != 1:
            raise P1PromotionDecisionError(
                "repository must be owner/name"
            )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
        )
        for field in (
            "prom02_decision_digest",
            "intent_digest",
            "deferred_volume_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha64(getattr(self, field), field),
            )
        if (
            isinstance(self.deferred_volume_count, bool)
            or not isinstance(self.deferred_volume_count, int)
            or self.deferred_volume_count < 1
        ):
            raise P1PromotionDecisionError(
                "deferred_volume_count must be positive integer"
            )
        object.__setattr__(
            self,
            "explicit_blockers",
            _blockers(self.explicit_blockers),
        )
        if self.signature_observation_digest is not None:
            object.__setattr__(
                self,
                "signature_observation_digest",
                _sha64(
                    self.signature_observation_digest,
                    "signature_observation_digest",
                ),
            )
        if self.promotion_granted and (
            not self.accepted
            or not self.signed
            or self.disposition is not PromotionDisposition.PROMOTE
            or self.explicit_blockers
        ):
            raise P1PromotionDecisionError(
                "promotion_granted requires accepted signed blocker-free PROMOTE"
            )
        if self.task_id != P1_PROMOTION_DECISION_TASK_ID:
            raise P1PromotionDecisionError("task_id drift")
        if (
            self.accountability_id
            != P1_PROMOTION_DECISION_ACCOUNTABILITY_ID
        ):
            raise P1PromotionDecisionError(
                "accountability_id drift"
            )
        if self.schema_version != P1_PROMOTION_DECISION_SCHEMA_VERSION:
            raise P1PromotionDecisionError(
                "unsupported signed decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "disposition": self.disposition.value,
            "promotion_granted": self.promotion_granted,
            "signed": self.signed,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "prom02_decision_digest": self.prom02_decision_digest,
            "intent_digest": self.intent_digest,
            "deferred_volume_count": self.deferred_volume_count,
            "deferred_volume_digest": self.deferred_volume_digest,
            "explicit_blockers": list(self.explicit_blockers),
            "signature_observation_digest": (
                self.signature_observation_digest
            ),
            "maturity_mutation": False,
            "promotion_effect": "terminal_candidate",
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:prom-03:terminal-decision",
    ) -> EvidenceRef:
        if not self.accepted:
            raise P1PromotionDecisionError(
                "invalid terminal decision cannot become evidence"
            )
        category = (
            "p1_signed_promotion_decision"
            if self.promotion_granted
            else "p1_explicit_promotion_rejection"
        )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category=category,
        )


def finalize_p1_promotion_decision(
    *,
    intent: P1PromotionIntent,
    prom02: P1FailureJourneyDecision,
    expected_deferred_volume_refs: Iterable[str],
    signature: IndependentSignatureObservation | None = None,
) -> P1SignedPromotionDecision:
    """Qualify a signed promotion or exact-head explicit rejection."""

    if not isinstance(intent, P1PromotionIntent):
        raise TypeError("intent must be P1PromotionIntent")
    if not isinstance(prom02, P1FailureJourneyDecision):
        raise TypeError("prom02 must be P1FailureJourneyDecision")
    if signature is not None and not isinstance(
        signature,
        IndependentSignatureObservation,
    ):
        raise TypeError(
            "signature must be IndependentSignatureObservation"
        )

    expected_deferred = _volumes(expected_deferred_volume_refs)
    expected_deferred_digest = _canonical_digest(
        list(expected_deferred)
    )
    reasons: list[str] = []

    if intent.repository != prom02.repository:
        reasons.append("prom02-repository-mismatch")
    if intent.commit_sha != prom02.commit_sha:
        reasons.append("prom02-exact-head-mismatch")
    if intent.prom02_decision_digest != prom02.decision_digest:
        reasons.append("prom02-decision-digest-mismatch")
    if intent.prom02_accepted != prom02.accepted:
        reasons.append("prom02-acceptance-mismatch")
    if intent.prom01_bundle_digest != prom02.prom01_bundle_digest:
        reasons.append("prom01-bundle-digest-mismatch")
    if intent.prom01_promotion_ready != prom02.prom01_promotion_ready:
        reasons.append("prom01-promotion-ready-mismatch")
    if intent.deferred_volume_refs != expected_deferred:
        reasons.append("deferred-volume-scope-mismatch")
    if intent.deferred_volume_digest != expected_deferred_digest:
        reasons.append("deferred-volume-digest-mismatch")

    signed = False
    signature_digest: str | None = None
    if signature is not None:
        signature_digest = signature.observation_digest
        if signature.repository != intent.repository:
            reasons.append("signature-repository-mismatch")
        if signature.commit_sha != intent.commit_sha:
            reasons.append("signature-exact-head-mismatch")
        if signature.intent_digest != intent.intent_digest:
            reasons.append("signature-intent-digest-mismatch")
        if intent.signer_id is None:
            reasons.append("signature-signer-not-declared")
        elif signature.signer_id != intent.signer_id:
            reasons.append("signature-signer-id-mismatch")
        if intent.signer_type is None:
            reasons.append("signature-signer-type-not-declared")
        elif signature.signer_type != intent.signer_type:
            reasons.append("signature-signer-type-mismatch")
        if intent.signer_identity_digest is None:
            reasons.append("signature-identity-not-declared")
        elif (
            signature.signer_identity_digest
            != intent.signer_identity_digest
        ):
            reasons.append("signature-identity-digest-mismatch")
        if intent.public_key_fingerprint is None:
            reasons.append("signature-key-not-declared")
        elif (
            signature.public_key_fingerprint
            != intent.public_key_fingerprint
        ):
            reasons.append("signature-key-fingerprint-mismatch")
        if not signature.verified:
            reasons.append("signature-not-verified")
        if not signature.independent:
            reasons.append("signature-verification-not-independent")
        signed = (
            signature.verified
            and signature.independent
            and not any(
                reason.startswith("signature-")
                for reason in reasons
            )
        )

    if intent.disposition is PromotionDisposition.PROMOTE:
        if not prom02.accepted:
            reasons.append("prom02-rejected")
        if not prom02.prom01_promotion_ready:
            reasons.append("prom01-not-promotion-ready")
        if signature is None:
            reasons.append("independent-signature-missing")
        elif not signed:
            reasons.append("independent-signature-invalid")
    else:
        if not intent.explicit_blockers:
            reasons.append("explicit-rejection-blockers-missing")

    normalized = tuple(sorted(set(reasons)))
    accepted = not normalized
    promotion_granted = (
        accepted
        and intent.disposition is PromotionDisposition.PROMOTE
        and signed
    )
    return P1SignedPromotionDecision(
        accepted=accepted,
        reasons=normalized,
        disposition=intent.disposition,
        promotion_granted=promotion_granted,
        signed=signed,
        repository=intent.repository,
        commit_sha=intent.commit_sha,
        prom02_decision_digest=prom02.decision_digest,
        intent_digest=intent.intent_digest,
        deferred_volume_count=len(intent.deferred_volume_refs),
        deferred_volume_digest=intent.deferred_volume_digest,
        explicit_blockers=intent.explicit_blockers,
        signature_observation_digest=signature_digest,
    )


__all__ = [
    "P1_PROMOTION_ALLOWED_SIGNER_TYPES",
    "P1_PROMOTION_DECISION_ACCOUNTABILITY_ID",
    "P1_PROMOTION_DECISION_SCHEMA_VERSION",
    "P1_PROMOTION_SIGNATURE_METHOD",
    "P1_PROMOTION_DECISION_TASK_ID",
    "IndependentSignatureObservation",
    "P1PromotionDecisionError",
    "P1PromotionIntent",
    "P1SignedPromotionDecision",
    "PromotionDisposition",
    "finalize_p1_promotion_decision",
]

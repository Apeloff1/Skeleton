"""Independent signed P1 promotion decision contract.

P1-PROM-03 is the only P1 terminal decision contract. It may assert promotion
of the bounded P1 frontier only when PROM-02 is accepted and promotion-ready,
the exact deferred scope remains visible, and two independently attributable
signoffs bind the same exact-head subject. It never promotes the full
masterplan or mutates maturity source data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.p1_failure_journeys import P1FailureJourneyDecision


P1_PROMOTION_SCHEMA_VERSION = 1
P1_PROMOTION_TASK_ID = "P1-PROM-03"
P1_PROMOTION_ACCOUNTABILITY_ID = "ACC-P1-PROM-03"

_PHASES = frozenset({"implementation", "verification"})
_SIGNER_TYPES = frozenset({"human", "agent", "ci", "service"})
_SIGNATURE_METHODS = frozenset(
    {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"}
)
_STRONG_SIGNATURE_REF_METHODS = frozenset(
    {"git_gpg", "git_ssh", "sigstore", "ci_oidc"}
)
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


class P1PromotionDecisionError(ValueError):
    """PROM-03 input violates the terminal promotion contract."""


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
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
    return hashlib.sha256(raw).hexdigest()


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
            f"{field} must be lowercase 40-character git sha"
        )
    return value


def _sha64(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA64_RE.fullmatch(value):
        raise P1PromotionDecisionError(f"{field} must be lowercase sha256")
    return value


def _utc_text(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise P1PromotionDecisionError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise P1PromotionDecisionError(f"{field} must include timezone")
    utc = parsed.astimezone(timezone.utc)
    canonical = utc.isoformat(timespec="seconds").replace("+00:00", "Z")
    if text != canonical:
        raise P1PromotionDecisionError(
            f"{field} must use canonical RFC3339 UTC seconds"
        )
    return canonical


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _volume_refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise P1PromotionDecisionError(
            "deferred_volume_refs must be an iterable of volume refs"
        )
    rows = tuple(sorted({_text(item, "deferred_volume_ref", maximum=64) for item in values}))
    if not rows:
        raise P1PromotionDecisionError("deferred_volume_refs must be non-empty")
    return rows


@dataclass(frozen=True, slots=True)
class P1PromotionAttestation:
    """One identity-bound signoff over the exact PROM-03 subject."""

    phase: str
    repository: str
    commit_sha: str
    subject_digest: str
    signer_id: str
    signer_type: str
    role: str
    signed_at_utc: str
    signature_method: str
    signature_ref: str | None
    verifier_digest: str
    evidence_digest: str
    task_id: str = P1_PROMOTION_TASK_ID
    accountability_id: str = P1_PROMOTION_ACCOUNTABILITY_ID
    schema_version: int = P1_PROMOTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        phase = _text(self.phase, "phase", maximum=32)
        if phase not in _PHASES:
            raise P1PromotionDecisionError("unsupported attestation phase")
        object.__setattr__(self, "phase", phase)

        repository = _text(self.repository, "repository", maximum=200)
        if repository.count("/") != 1:
            raise P1PromotionDecisionError("repository must be owner/name")
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "commit_sha", _sha40(self.commit_sha, "commit_sha"))
        object.__setattr__(
            self,
            "subject_digest",
            _sha64(self.subject_digest, "subject_digest"),
        )
        object.__setattr__(
            self,
            "signer_id",
            _text(self.signer_id, "signer_id", maximum=512),
        )
        signer_type = _text(self.signer_type, "signer_type", maximum=32)
        if signer_type not in _SIGNER_TYPES:
            raise P1PromotionDecisionError("unsupported signer_type")
        object.__setattr__(self, "signer_type", signer_type)
        object.__setattr__(self, "role", _text(self.role, "role", maximum=128))
        object.__setattr__(
            self,
            "signed_at_utc",
            _utc_text(self.signed_at_utc, "signed_at_utc"),
        )
        method = _text(self.signature_method, "signature_method", maximum=64)
        if method not in _SIGNATURE_METHODS:
            raise P1PromotionDecisionError("unsupported signature_method")
        object.__setattr__(self, "signature_method", method)

        if self.signature_ref is not None:
            object.__setattr__(
                self,
                "signature_ref",
                _text(self.signature_ref, "signature_ref", maximum=2048),
            )
        if method in _STRONG_SIGNATURE_REF_METHODS and self.signature_ref is None:
            raise P1PromotionDecisionError(
                f"{method} attestation requires signature_ref"
            )

        object.__setattr__(
            self,
            "verifier_digest",
            _sha64(self.verifier_digest, "verifier_digest"),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _sha64(self.evidence_digest, "evidence_digest"),
        )
        if self.task_id != P1_PROMOTION_TASK_ID:
            raise P1PromotionDecisionError("attestation task_id drift")
        if self.accountability_id != P1_PROMOTION_ACCOUNTABILITY_ID:
            raise P1PromotionDecisionError("attestation accountability_id drift")
        if self.schema_version != P1_PROMOTION_SCHEMA_VERSION:
            raise P1PromotionDecisionError("unsupported attestation schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "phase": self.phase,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "subject_digest": self.subject_digest,
            "signer_id": self.signer_id,
            "signer_type": self.signer_type,
            "role": self.role,
            "signed_at_utc": self.signed_at_utc,
            "signature_method": self.signature_method,
            "signature_ref": self.signature_ref,
            "verifier_digest": self.verifier_digest,
            "evidence_digest": self.evidence_digest,
        }

    @property
    def attestation_digest(self) -> str:
        return _canonical_digest(self.payload())


def p1_promotion_subject_payload(
    *,
    repository: str,
    commit_sha: str,
    prom02_decision_digest: str,
    primary_volume_count: int,
    masterplan_volume_count: int,
    deferred_volume_refs: Iterable[str],
) -> dict[str, Any]:
    repository = _text(repository, "repository", maximum=200)
    if repository.count("/") != 1:
        raise P1PromotionDecisionError("repository must be owner/name")
    head = _sha40(commit_sha, "commit_sha")
    prom02 = _sha64(prom02_decision_digest, "prom02_decision_digest")
    if (
        isinstance(primary_volume_count, bool)
        or not isinstance(primary_volume_count, int)
        or primary_volume_count < 1
    ):
        raise P1PromotionDecisionError("primary_volume_count must be positive integer")
    if (
        isinstance(masterplan_volume_count, bool)
        or not isinstance(masterplan_volume_count, int)
        or masterplan_volume_count < 1
    ):
        raise P1PromotionDecisionError("masterplan_volume_count must be positive integer")
    deferred = _volume_refs(deferred_volume_refs)
    if primary_volume_count + len(deferred) != masterplan_volume_count:
        raise P1PromotionDecisionError(
            "primary plus deferred volume count must equal masterplan volume count"
        )
    return {
        "schema_version": P1_PROMOTION_SCHEMA_VERSION,
        "task_id": P1_PROMOTION_TASK_ID,
        "accountability_id": P1_PROMOTION_ACCOUNTABILITY_ID,
        "repository": repository,
        "commit_sha": head,
        "prom02_decision_digest": prom02,
        "primary_volume_count": primary_volume_count,
        "deferred_volume_count": len(deferred),
        "deferred_scope_digest": _canonical_digest(list(deferred)),
        "masterplan_volume_count": masterplan_volume_count,
    }


def p1_promotion_subject_digest(**kwargs: Any) -> str:
    return _canonical_digest(p1_promotion_subject_payload(**kwargs))


@dataclass(frozen=True, slots=True)
class P1PromotionDecision:
    promoted: bool
    reasons: tuple[str, ...]
    repository: str
    commit_sha: str
    subject_digest: str
    prom02_decision_digest: str
    primary_volume_count: int
    deferred_volume_count: int
    deferred_scope_digest: str
    masterplan_volume_count: int
    implementation_attestation_digest: str | None
    verification_attestation_digest: str | None
    task_id: str = P1_PROMOTION_TASK_ID
    accountability_id: str = P1_PROMOTION_ACCOUNTABILITY_ID
    schema_version: int = P1_PROMOTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.promoted, bool):
            raise P1PromotionDecisionError("promoted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise P1PromotionDecisionError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(sorted(set(self.reasons))),
        )
        repository = _text(self.repository, "repository", maximum=200)
        if repository.count("/") != 1:
            raise P1PromotionDecisionError("repository must be owner/name")
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "commit_sha", _sha40(self.commit_sha, "commit_sha"))
        for field in (
            "subject_digest",
            "prom02_decision_digest",
            "deferred_scope_digest",
        ):
            object.__setattr__(self, field, _sha64(getattr(self, field), field))
        for field in (
            "primary_volume_count",
            "deferred_volume_count",
            "masterplan_volume_count",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise P1PromotionDecisionError(
                    f"{field} must be a non-negative integer"
                )
        if self.primary_volume_count < 1:
            raise P1PromotionDecisionError(
                "primary_volume_count must be positive"
            )
        if self.primary_volume_count + self.deferred_volume_count != self.masterplan_volume_count:
            raise P1PromotionDecisionError(
                "promotion scope count does not cover masterplan"
            )
        for field in (
            "implementation_attestation_digest",
            "verification_attestation_digest",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha64(value, field))
        if self.task_id != P1_PROMOTION_TASK_ID:
            raise P1PromotionDecisionError("decision task_id drift")
        if self.accountability_id != P1_PROMOTION_ACCOUNTABILITY_ID:
            raise P1PromotionDecisionError("decision accountability_id drift")
        if self.schema_version != P1_PROMOTION_SCHEMA_VERSION:
            raise P1PromotionDecisionError("unsupported decision schema")
        if self.promoted:
            if self.reasons:
                raise P1PromotionDecisionError(
                    "promoted decision cannot contain rejection reasons"
                )
            if (
                self.implementation_attestation_digest is None
                or self.verification_attestation_digest is None
            ):
                raise P1PromotionDecisionError(
                    "promoted decision requires both attestations"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "promoted": self.promoted,
            "reasons": list(self.reasons),
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "subject_digest": self.subject_digest,
            "prom02_decision_digest": self.prom02_decision_digest,
            "primary_volume_count": self.primary_volume_count,
            "deferred_volume_count": self.deferred_volume_count,
            "deferred_scope_digest": self.deferred_scope_digest,
            "masterplan_volume_count": self.masterplan_volume_count,
            "implementation_attestation_digest": self.implementation_attestation_digest,
            "verification_attestation_digest": self.verification_attestation_digest,
            "p1_promotion_authority": self.promoted,
            "signed_promotion": self.promoted,
            "masterplan_maturity_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


def decide_p1_promotion(
    *,
    prom02_bundle: P1FailureJourneyDecision,
    expected_repository: str,
    expected_head: str,
    primary_volume_count: int,
    masterplan_volume_count: int,
    deferred_volume_refs: Iterable[str],
    implementation_attestation: P1PromotionAttestation | None,
    verification_attestation: P1PromotionAttestation | None,
) -> P1PromotionDecision:
    """Return signed promotion only when every terminal invariant is satisfied."""

    if not isinstance(prom02_bundle, P1FailureJourneyDecision):
        raise TypeError("prom02_bundle must be P1FailureJourneyDecision")

    subject = p1_promotion_subject_payload(
        repository=expected_repository,
        commit_sha=expected_head,
        prom02_decision_digest=prom02_bundle.decision_digest,
        primary_volume_count=primary_volume_count,
        masterplan_volume_count=masterplan_volume_count,
        deferred_volume_refs=deferred_volume_refs,
    )
    subject_digest = _canonical_digest(subject)
    reasons: list[str] = []

    if not prom02_bundle.accepted:
        reasons.append("prom02-bundle-rejected")
    if not prom02_bundle.prom01_promotion_ready:
        reasons.append("prom01-not-promotion-ready")
    if prom02_bundle.repository != subject["repository"]:
        reasons.append("prom02-repository-mismatch")
    if prom02_bundle.commit_sha != subject["commit_sha"]:
        reasons.append("prom02-exact-head-mismatch")

    def validate_attestation(
        attestation: P1PromotionAttestation | None,
        *,
        phase: str,
        role: str,
    ) -> None:
        if attestation is None:
            reasons.append(f"missing-{phase}-attestation")
            return
        if not isinstance(attestation, P1PromotionAttestation):
            raise TypeError("attestations must be P1PromotionAttestation")
        if attestation.phase != phase:
            reasons.append(f"{phase}-phase-mismatch")
        if attestation.role != role:
            reasons.append(f"{phase}-role-mismatch")
        if attestation.repository != subject["repository"]:
            reasons.append(f"{phase}-repository-mismatch")
        if attestation.commit_sha != subject["commit_sha"]:
            reasons.append(f"{phase}-exact-head-mismatch")
        if attestation.subject_digest != subject_digest:
            reasons.append(f"{phase}-subject-mismatch")

    validate_attestation(
        implementation_attestation,
        phase="implementation",
        role="promotion-implementation",
    )
    validate_attestation(
        verification_attestation,
        phase="verification",
        role="independent-promotion-verification",
    )

    if (
        implementation_attestation is not None
        and verification_attestation is not None
    ):
        if implementation_attestation.signer_id == verification_attestation.signer_id:
            reasons.append("verification-signer-not-independent")
        if (
            implementation_attestation.verifier_digest
            == verification_attestation.verifier_digest
        ):
            reasons.append("verification-implementation-not-independent")
        if _utc_datetime(verification_attestation.signed_at_utc) < _utc_datetime(
            implementation_attestation.signed_at_utc
        ):
            reasons.append("verification-predates-implementation")
        if (
            implementation_attestation.evidence_digest
            != verification_attestation.evidence_digest
        ):
            reasons.append("attestation-evidence-digest-mismatch")

    normalized = tuple(sorted(set(reasons)))
    deferred_count = int(subject["deferred_volume_count"])
    return P1PromotionDecision(
        promoted=not normalized,
        reasons=normalized,
        repository=str(subject["repository"]),
        commit_sha=str(subject["commit_sha"]),
        subject_digest=subject_digest,
        prom02_decision_digest=str(subject["prom02_decision_digest"]),
        primary_volume_count=int(subject["primary_volume_count"]),
        deferred_volume_count=deferred_count,
        deferred_scope_digest=str(subject["deferred_scope_digest"]),
        masterplan_volume_count=int(subject["masterplan_volume_count"]),
        implementation_attestation_digest=(
            implementation_attestation.attestation_digest
            if implementation_attestation is not None
            else None
        ),
        verification_attestation_digest=(
            verification_attestation.attestation_digest
            if verification_attestation is not None
            else None
        ),
    )


__all__ = [
    "P1_PROMOTION_ACCOUNTABILITY_ID",
    "P1_PROMOTION_SCHEMA_VERSION",
    "P1_PROMOTION_TASK_ID",
    "P1PromotionAttestation",
    "P1PromotionDecision",
    "P1PromotionDecisionError",
    "decide_p1_promotion",
    "p1_promotion_subject_digest",
    "p1_promotion_subject_payload",
]

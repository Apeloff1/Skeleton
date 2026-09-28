"""Independent terminal P1 promotion decision.

PROM-03 consumes exact-head PROM-01 and PROM-02 evidence. It may record an
explicit rejection without a signature, but a production promotion is valid
only when a distinct independent verifier supplies an identity-bound signature
over the exact promotion subject. CI validates that signature record; it never
creates one.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef


P1_PROMOTION_DECISION_SCHEMA_VERSION = 1
P1_PROMOTION_DECISION_TASK_ID = "P1-PROM-03"
P1_PROMOTION_DECISION_ACCOUNTABILITY_ID = "ACC-P1-PROM-03"

_ALLOWED_SIGNATURE_METHODS = frozenset(
    {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"}
)
_SIGNATURE_REF_REQUIRED = frozenset(
    {"git_gpg", "git_ssh", "sigstore", "ci_oidc"}
)
_ALLOWED_SIGNER_TYPES = frozenset({"human", "ci", "service"})
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


class P1PromotionDecisionError(ValueError):
    """Terminal promotion decision input is malformed."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value:
        raise P1PromotionDecisionError(f"{field} must be non-empty")
    if value != value.strip() or len(value) > maximum:
        raise P1PromotionDecisionError(f"{field} must be normalized")
    return value


def _sha40(value: object, field: str) -> str:
    text = _text(value, field, maximum=40)
    if not _SHA40_RE.fullmatch(text):
        raise P1PromotionDecisionError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return text


def _sha64(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if not _SHA64_RE.fullmatch(text):
        raise P1PromotionDecisionError(
            f"{field} must be lowercase sha256"
        )
    return text


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise P1PromotionDecisionError(
            "promotion subject must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _refs(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise P1PromotionDecisionError(
            "evidence_refs must contain EvidenceRef values"
        )
    rows: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise P1PromotionDecisionError(
                "evidence_refs must contain EvidenceRef values"
            )
        rows[(item.source, item.digest, item.category)] = item
    if not rows:
        raise P1PromotionDecisionError("evidence_refs must be non-empty")
    return tuple(rows[key] for key in sorted(rows))


def promotion_subject_digest(
    *,
    repository: str,
    commit_sha: str,
    prom01_bundle_digest: str,
    prom02_bundle_digest: str,
) -> str:
    """Return the exact subject an independent verifier must sign."""

    return _canonical_digest(
        {
            "schema_version": P1_PROMOTION_DECISION_SCHEMA_VERSION,
            "task_id": P1_PROMOTION_DECISION_TASK_ID,
            "accountability_id": P1_PROMOTION_DECISION_ACCOUNTABILITY_ID,
            "repository": _text(repository, "repository", maximum=256),
            "commit_sha": _sha40(commit_sha, "commit_sha"),
            "prom01_bundle_digest": _sha64(
                prom01_bundle_digest,
                "prom01_bundle_digest",
            ),
            "prom02_bundle_digest": _sha64(
                prom02_bundle_digest,
                "prom02_bundle_digest",
            ),
        }
    )


@dataclass(frozen=True, slots=True)
class IndependentPromotionAttestation:
    repository: str
    commit_sha: str
    signer_id: str
    signer_type: str
    role: str
    signature_method: str
    signature_ref: str | None
    subject_digest: str
    independent: bool
    evidence_refs: tuple[EvidenceRef, ...]
    task_id: str = P1_PROMOTION_DECISION_TASK_ID
    accountability_id: str = P1_PROMOTION_DECISION_ACCOUNTABILITY_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "repository",
            _text(self.repository, "repository", maximum=256),
        )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
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
        if signer_type not in _ALLOWED_SIGNER_TYPES:
            raise P1PromotionDecisionError(
                "promotion signer_type must be human, ci, or service"
            )
        object.__setattr__(self, "signer_type", signer_type)
        object.__setattr__(
            self,
            "role",
            _text(self.role, "role", maximum=128),
        )
        method = _text(
            self.signature_method,
            "signature_method",
            maximum=64,
        )
        if method not in _ALLOWED_SIGNATURE_METHODS:
            raise P1PromotionDecisionError(
                "unsupported promotion signature method"
            )
        object.__setattr__(self, "signature_method", method)
        if method in _SIGNATURE_REF_REQUIRED:
            if self.signature_ref is None:
                raise P1PromotionDecisionError(
                    f"{method} requires signature_ref"
                )
            object.__setattr__(
                self,
                "signature_ref",
                _text(
                    self.signature_ref,
                    "signature_ref",
                    maximum=2048,
                ),
            )
        elif self.signature_ref is not None:
            object.__setattr__(
                self,
                "signature_ref",
                _text(
                    self.signature_ref,
                    "signature_ref",
                    maximum=2048,
                ),
            )
        object.__setattr__(
            self,
            "subject_digest",
            _sha64(self.subject_digest, "subject_digest"),
        )
        if self.independent is not True:
            raise P1PromotionDecisionError(
                "promotion attestation must be independent"
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs),
        )
        if self.task_id != P1_PROMOTION_DECISION_TASK_ID:
            raise P1PromotionDecisionError("task_id drift")
        if self.accountability_id != P1_PROMOTION_DECISION_ACCOUNTABILITY_ID:
            raise P1PromotionDecisionError("accountability_id drift")

    def payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "signer_id": self.signer_id,
            "signer_type": self.signer_type,
            "role": self.role,
            "signature_method": self.signature_method,
            "signature_ref": self.signature_ref,
            "subject_digest": self.subject_digest,
            "independent": self.independent,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
        }

    @property
    def attestation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class P1TerminalPromotionDecision:
    valid: bool
    outcome: str
    reasons: tuple[str, ...]
    repository: str
    commit_sha: str
    prom01_bundle_digest: str
    prom02_bundle_digest: str
    promotion_subject_digest: str
    blocker_count: int
    signer_id: str | None = None
    signer_type: str | None = None
    signature_method: str | None = None
    signature_ref: str | None = None
    attestation_digest: str | None = None
    schema_version: int = P1_PROMOTION_DECISION_SCHEMA_VERSION
    task_id: str = P1_PROMOTION_DECISION_TASK_ID
    accountability_id: str = P1_PROMOTION_DECISION_ACCOUNTABILITY_ID

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise P1PromotionDecisionError("valid must be boolean")
        if self.outcome not in {"promoted", "rejected"}:
            raise P1PromotionDecisionError(
                "outcome must be promoted or rejected"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise P1PromotionDecisionError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "repository",
            _text(self.repository, "repository", maximum=256),
        )
        object.__setattr__(
            self,
            "commit_sha",
            _sha40(self.commit_sha, "commit_sha"),
        )
        for field in (
            "prom01_bundle_digest",
            "prom02_bundle_digest",
            "promotion_subject_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha64(getattr(self, field), field),
            )
        if (
            isinstance(self.blocker_count, bool)
            or not isinstance(self.blocker_count, int)
            or self.blocker_count < 0
        ):
            raise P1PromotionDecisionError(
                "blocker_count must be non-negative integer"
            )
        signed_fields = (
            self.signer_id,
            self.signer_type,
            self.signature_method,
            self.attestation_digest,
        )
        if self.outcome == "promoted":
            if not self.valid or self.reasons:
                raise P1PromotionDecisionError(
                    "promoted decision must be valid and reason-free"
                )
            if self.blocker_count != 0:
                raise P1PromotionDecisionError(
                    "promoted decision cannot retain blockers"
                )
            if any(value is None for value in signed_fields):
                raise P1PromotionDecisionError(
                    "promoted decision requires independent signature"
                )
        if self.attestation_digest is not None:
            object.__setattr__(
                self,
                "attestation_digest",
                _sha64(self.attestation_digest, "attestation_digest"),
            )

    @property
    def promoted(self) -> bool:
        return self.valid and self.outcome == "promoted"

    @property
    def signed_promotion(self) -> bool:
        return self.promoted and self.attestation_digest is not None

    @property
    def promotion_authority(self) -> bool:
        return self.signed_promotion

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "valid": self.valid,
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "prom01_bundle_digest": self.prom01_bundle_digest,
            "prom02_bundle_digest": self.prom02_bundle_digest,
            "promotion_subject_digest": self.promotion_subject_digest,
            "blocker_count": self.blocker_count,
            "signer_id": self.signer_id,
            "signer_type": self.signer_type,
            "signature_method": self.signature_method,
            "signature_ref": self.signature_ref,
            "attestation_digest": self.attestation_digest,
            "signed_promotion": self.signed_promotion,
            "promotion_authority": self.promotion_authority,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def decision_evidence_ref(
        self,
        *,
        source: str = "p1:prom-03:terminal-decision",
    ) -> EvidenceRef:
        if not self.valid:
            raise P1PromotionDecisionError(
                "invalid terminal decision cannot become evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="p1_terminal_promotion_decision",
        )


def decide_p1_terminal_promotion(
    *,
    prom01_bundle: dict[str, Any],
    prom02_bundle: dict[str, Any],
    expected_repository: str,
    expected_head: str,
    implementation_signer_id: str,
    attestation: IndependentPromotionAttestation | None = None,
) -> P1TerminalPromotionDecision:
    repository = _text(
        expected_repository,
        "expected_repository",
        maximum=256,
    )
    head = _sha40(expected_head, "expected_head")
    implementation_signer = _text(
        implementation_signer_id,
        "implementation_signer_id",
        maximum=256,
    )
    if not isinstance(prom01_bundle, dict):
        raise TypeError("prom01_bundle must be dict")
    if not isinstance(prom02_bundle, dict):
        raise TypeError("prom02_bundle must be dict")

    reasons: list[str] = []
    if prom01_bundle.get("accepted") is not True:
        reasons.append("prom01-rejected")
    if prom02_bundle.get("accepted") is not True:
        reasons.append("prom02-rejected")
    if prom01_bundle.get("repository") != repository:
        reasons.append("prom01-repository-mismatch")
    if prom02_bundle.get("repository") != repository:
        reasons.append("prom02-repository-mismatch")
    if prom01_bundle.get("commit_sha") != head:
        reasons.append("prom01-exact-head-mismatch")
    if prom02_bundle.get("commit_sha") != head:
        reasons.append("prom02-exact-head-mismatch")

    prom01_digest = _sha64(
        prom01_bundle.get("decision_digest"),
        "prom01.decision_digest",
    )
    prom02_digest = _sha64(
        prom02_bundle.get("decision_digest"),
        "prom02.decision_digest",
    )
    if prom02_bundle.get("prom01_bundle_digest") != prom01_digest:
        reasons.append("prom02-prom01-link-mismatch")

    blockers_raw = prom01_bundle.get("promotion_blockers")
    if not isinstance(blockers_raw, list) or any(
        not isinstance(item, str) or not item for item in blockers_raw
    ):
        raise P1PromotionDecisionError(
            "PROM-01 promotion_blockers must be string list"
        )
    blocker_count = len(blockers_raw)
    promotion_ready = prom01_bundle.get("promotion_ready") is True

    subject = promotion_subject_digest(
        repository=repository,
        commit_sha=head,
        prom01_bundle_digest=prom01_digest,
        prom02_bundle_digest=prom02_digest,
    )

    signer_id = None
    signer_type = None
    signature_method = None
    signature_ref = None
    attestation_digest = None

    if not promotion_ready:
        reasons.append("prom01-not-promotion-ready")
        reasons.extend(
            f"blocker:{item}"
            for item in sorted(set(blockers_raw))
        )
        if attestation is not None:
            reasons.append("signature-present-while-blocked")
    elif attestation is None:
        reasons.append("independent-signature-missing")
    else:
        if not isinstance(attestation, IndependentPromotionAttestation):
            raise TypeError(
                "attestation must be IndependentPromotionAttestation"
            )
        if attestation.repository != repository:
            reasons.append("attestation-repository-mismatch")
        if attestation.commit_sha != head:
            reasons.append("attestation-exact-head-mismatch")
        if attestation.subject_digest != subject:
            reasons.append("attestation-subject-mismatch")
        if attestation.signer_id == implementation_signer:
            reasons.append("self-certification-forbidden")
        signer_id = attestation.signer_id
        signer_type = attestation.signer_type
        signature_method = attestation.signature_method
        signature_ref = attestation.signature_ref
        attestation_digest = attestation.attestation_digest

    normalized = tuple(sorted(set(reasons)))
    structurally_valid = not any(
        reason
        for reason in normalized
        if reason.startswith("prom01-rejected")
        or reason.startswith("prom02-rejected")
        or "mismatch" in reason
    )
    promoted = (
        structurally_valid
        and promotion_ready
        and not normalized
        and attestation is not None
    )
    return P1TerminalPromotionDecision(
        valid=structurally_valid,
        outcome="promoted" if promoted else "rejected",
        reasons=normalized,
        repository=repository,
        commit_sha=head,
        prom01_bundle_digest=prom01_digest,
        prom02_bundle_digest=prom02_digest,
        promotion_subject_digest=subject,
        blocker_count=blocker_count,
        signer_id=signer_id,
        signer_type=signer_type,
        signature_method=signature_method,
        signature_ref=signature_ref,
        attestation_digest=attestation_digest,
    )


__all__ = [
    "P1_PROMOTION_DECISION_ACCOUNTABILITY_ID",
    "P1_PROMOTION_DECISION_SCHEMA_VERSION",
    "P1_PROMOTION_DECISION_TASK_ID",
    "IndependentPromotionAttestation",
    "P1PromotionDecisionError",
    "P1TerminalPromotionDecision",
    "decide_p1_terminal_promotion",
    "promotion_subject_digest",
]

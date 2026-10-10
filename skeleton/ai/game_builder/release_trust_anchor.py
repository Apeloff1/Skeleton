"""Pinned external Ed25519 trust roots for independent game rights reviewers.

Do not accept a reviewer registry supplied by the same game-authoring process
without authenticating it to an *out-of-band pinned root key*. The caller must
provide the expected root-key SHA-256 and a minimum accepted monotonically
increasing policy epoch from independently administered state. This module
never creates signing keys, grants publishing rights or uploads game content.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .legal_paths import HomebrewLegalAssessment
from .plagiarism_guard import OriginalityReport
from .release_assurance import (
    ReleaseCandidate, ReleaseChannel, ReleaseReviewError, ReleaseReviewReceipt,
    ReviewAttestation, TrustedReviewer, _is_ident, _utc, evaluate_independent_review,
)


_HEX32 = re.compile(r"^[a-f0-9]{64}$")
_HEX64 = re.compile(r"^[a-f0-9]{128}$")


def _digest(payload: dict[str, object]) -> str:
    return sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _trusted_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _row(row: TrustedReviewer) -> dict[str, object]:
    return {
        "reviewer_id": row.reviewer_id,
        "key_id": row.key_id,
        "public_key_hex": row.public_key_hex,
        "role": row.role.value,
        "allowed_domains": sorted(d.value for d in row.allowed_domains),
        "valid_from_utc": row.valid_from_utc,
        "expires_utc": row.expires_utc,
        "revoked": row.revoked,
    }


@dataclass(frozen=True, slots=True)
class SignedReviewerRegistry:
    """Policy authority's signed, project/channel/territory-scoped key registry."""
    project_id: str
    target_platform_id: str
    channel: ReleaseChannel
    jurisdictions: tuple[str, ...]
    policy_epoch: int
    issued_utc: str
    expires_utc: str
    root_public_key_hex: str
    reviewers: tuple[TrustedReviewer, ...]
    root_signature_hex: str

    def __post_init__(self) -> None:
        if not _is_ident(self.project_id) or not _is_ident(self.target_platform_id):
            raise ReleaseReviewError("missing or unsafe trust-policy project and target scope")
        if not isinstance(self.channel, ReleaseChannel):
            raise ReleaseReviewError("trust-policy channel invalid")
        if (not isinstance(self.jurisdictions, tuple) or not self.jurisdictions
            or len(self.jurisdictions) > 32
            or any(not isinstance(x, str) or not x for x in self.jurisdictions)
            or len({x.casefold() for x in self.jurisdictions}) != len(self.jurisdictions)):
            raise ReleaseReviewError("trust policy needs exact unambiguous legal territories")
        if type(self.policy_epoch) is not int or not 1 <= self.policy_epoch <= 2**63 - 1:
            raise ReleaseReviewError("signed reviewer policy epoch must be positive")
        if not isinstance(self.root_public_key_hex, str) or not _HEX32.fullmatch(self.root_public_key_hex):
            raise ReleaseReviewError("trust root requires an Ed25519 32-byte public key")
        if not isinstance(self.root_signature_hex, str) or not _HEX64.fullmatch(self.root_signature_hex):
            raise ReleaseReviewError("trust root requires a real Ed25519 signature")
        if _utc(self.issued_utc) >= _utc(self.expires_utc):
            raise ReleaseReviewError("invalid signed trust-policy lifetime")
        if (not isinstance(self.reviewers, tuple) or not self.reviewers
            or len(self.reviewers) > 128
            or any(not isinstance(r, TrustedReviewer) for r in self.reviewers)):
            raise ReleaseReviewError("nonempty typed reviewer trust registry required")
        if any(r.public_key_hex == self.root_public_key_hex for r in self.reviewers):
            raise ReleaseReviewError("reviewer signing key cannot equal administrative policy root")
        if (
            len({r.key_id.casefold() for r in self.reviewers}) != len(self.reviewers)
            or len({r.reviewer_id.casefold() for r in self.reviewers}) != len(self.reviewers)
            or len({r.public_key_hex for r in self.reviewers}) != len(self.reviewers)
        ):
            raise ReleaseReviewError("duplicate reviewer identity or shared Ed25519 signing key")

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.signed_reviewer_registry.v1",
            "project_id": self.project_id,
            "target_platform_id": self.target_platform_id,
            "channel": self.channel.value,
            "jurisdictions": list(self.jurisdictions),
            "policy_epoch": self.policy_epoch,
            "issued_utc": self.issued_utc,
            "expires_utc": self.expires_utc,
            "reviewers": [_row(r) for r in sorted(self.reviewers, key=lambda r:r.key_id)],
            "root_public_key_hex": self.root_public_key_hex,
        }

    @property
    def signed_bytes(self) -> bytes:
        return _trusted_bytes(self.unsigned_payload())

    @property
    def digest(self) -> str:
        return sha256(self.signed_bytes).hexdigest()

    @property
    def trust_root_sha256(self) -> str:
        return sha256(bytes.fromhex(self.root_public_key_hex)).hexdigest()


@dataclass(frozen=True, slots=True)
class PinnedReviewerResult:
    review: ReleaseReviewReceipt
    candidate_sha256: str
    trust_registry_sha256: str
    trust_root_sha256: str
    trusted_policy_epoch: int
    evaluation_sha256: str
    externally_root_key_pinned: bool = True
    release_authorized: bool = False
    legal_infringement_certified: bool = False

    def __post_init__(self) -> None:
        if (self.release_authorized is not False
            or self.legal_infringement_certified is not False):
            raise ReleaseReviewError("pinned reviewer trust is not legal permission to publish")
        if self.externally_root_key_pinned is not True:
            raise ReleaseReviewError("pinned review cannot represent an unauthenticated root")
        if self.candidate_sha256 != self.review.candidate_sha256:
            raise ReleaseReviewError("review and pinned-root result concern different games")

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.pinned_reviewer_evaluation.v1",
            "candidate_sha256":self.candidate_sha256,
            "trust_registry_sha256":self.trust_registry_sha256,
            "trust_root_sha256":self.trust_root_sha256,
            "trusted_policy_epoch":self.trusted_policy_epoch,
            "evaluation_sha256":self.evaluation_sha256,
            "review_status":self.review.status.value,
            "independent_review_receipt_sha256":self.review.receipt_sha256,
            "externally_root_key_pinned":True,
            "release_authorized":False,
            "legal_infringement_certified":False,
        }


def evaluate_pinned_independent_review(
    candidate: ReleaseCandidate, legal: HomebrewLegalAssessment,
    originality: OriginalityReport, *, registry: SignedReviewerRegistry,
    attestations: tuple[ReviewAttestation, ...], evaluation_utc: str,
    expected_root_key_sha256: str, minimum_policy_epoch: int,
) -> PinnedReviewerResult:
    """Refuse forged/unpinned reviewer registries before any review evaluation."""
    if not isinstance(registry, SignedReviewerRegistry):
        raise ReleaseReviewError("signed external trust registry required")
    if not isinstance(candidate, ReleaseCandidate):
        raise ReleaseReviewError("typed candidate required")
    if type(minimum_policy_epoch) is not int or minimum_policy_epoch < 1:
        raise ReleaseReviewError("independent anti-rollback epoch required")
    if not isinstance(expected_root_key_sha256, str) or not _HEX32.fullmatch(expected_root_key_sha256):
        raise ReleaseReviewError("out-of-band pinned policy authority key digest required")
    if expected_root_key_sha256 != registry.trust_root_sha256:
        raise ReleaseReviewError("trusted reviewer root key not in independently pinned policy")
    if registry.policy_epoch < minimum_policy_epoch:
        raise ReleaseReviewError("revoked/rolled back reviewer policy epoch")
    if (
        registry.project_id != candidate.project_id or
        registry.target_platform_id != candidate.target_platform_id or
        registry.channel is not candidate.channel or
        registry.jurisdictions != candidate.jurisdictions
    ):
        raise ReleaseReviewError("reviewer trust policy is scoped to a different game/channel/market")
    now = _utc(evaluation_utc)
    if not (_utc(registry.issued_utc) <= now <= _utc(registry.expires_utc)):
        raise ReleaseReviewError("signed reviewer registry has not started or has expired")
    if not isinstance(attestations, tuple) or any(
        not isinstance(a, ReviewAttestation) for a in attestations
    ):
        raise ReleaseReviewError("typed reviewer evidence required")
    if any(_utc(a.issued_utc) < _utc(registry.issued_utc) for a in attestations):
        raise ReleaseReviewError("review signature predates its independently authorized trust policy")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(
            registry.root_public_key_hex
        )).verify(bytes.fromhex(registry.root_signature_hex), registry.signed_bytes)
    except ImportError as exc:
        raise ReleaseReviewError("required reviewer root signature verification unavailable") from exc
    except (InvalidSignature, ValueError) as exc:
        raise ReleaseReviewError("forged or modified independent reviewer trust registry") from exc

    review = evaluate_independent_review(
        candidate, legal, originality, trust_registry=registry.reviewers,
        attestations=attestations, evaluation_utc=evaluation_utc,
    )
    result_digest = _digest({
        "schema":"skeleton.game_builder.pinned_reviewer_evaluation.v1",
        "candidate_sha256":candidate.digest,
        "review_receipt_sha256":review.receipt_sha256,
        "registry_sha256":registry.digest,
        "root_key_sha256":expected_root_key_sha256,
        "policy_epoch":registry.policy_epoch,
        "evaluation_utc":evaluation_utc,
    })
    return PinnedReviewerResult(
        review=review,
        candidate_sha256=candidate.digest,
        trust_registry_sha256=registry.digest,
        trust_root_sha256=expected_root_key_sha256,
        trusted_policy_epoch=registry.policy_epoch,
        evaluation_sha256=result_digest,
    )

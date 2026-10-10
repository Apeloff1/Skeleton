"""Independent cryptographic review boundary for lawful homebrew publication.

Attestations are individually Ed25519-signed by reviewers enrolled in a
separately administered trust registry, bound to an exact binary, generated
world, rights packet, legal assessment, originality scan, distribution scope
and jurisdictions. Approval is a *review gate*, NOT a legal determination, a
console maker license, or authorization to publish. No signing private keys
or automatic review delegation are available in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re

from .legal_paths import HomebrewLegalAssessment
from .plagiarism_guard import OriginalityReport
from .platform_registry import PlatformRegistryError, default_registry

_SHA = re.compile(r"^[0-9a-f]{64}$")
_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ReleaseReviewError(ValueError):
    """Invalid or untrusted reviewer, submission, authorization or receipt."""


class ReleaseChannel(str, Enum):
    PRIVATE_HOMEBREW = "private_homebrew"
    DIRECT_DOWNLOAD = "direct_download"
    CONSOLE_STOREFRONT = "console_storefront"
    COMMERCIAL_DISTRIBUTION = "commercial_distribution"


class ReviewRole(str, Enum):
    CREATIVE = "creative_ip"
    LEGAL = "rights_and_legal"
    TECHNICAL = "build_and_hardware"


class ReviewDomain(str, Enum):
    AUTHORSHIP = "independent_authorship"
    CODE_TEXT = "source_text_similarity"
    ART_CHARACTERS = "art_and_character_rights"
    AUDIO_MUSIC = "audio_and_music_rights"
    LEVEL_NARRATIVE = "story_and_level_rights"
    TRADEMARK = "trade_dress_and_trademark"
    LICENSE_CHAIN = "asset_license_chain"
    JURISDICTION_TPM = "jurisdiction_and_hardware_tpm"
    NATIVE_VALIDATION = "native_target_validation"
    DISTRIBUTION_RIGHTS = "platform_and_distribution_terms"


_ROLE_BY_DOMAIN = {
    ReviewDomain.AUTHORSHIP: ReviewRole.CREATIVE,
    ReviewDomain.CODE_TEXT: ReviewRole.CREATIVE,
    ReviewDomain.ART_CHARACTERS: ReviewRole.CREATIVE,
    ReviewDomain.AUDIO_MUSIC: ReviewRole.CREATIVE,
    ReviewDomain.LEVEL_NARRATIVE: ReviewRole.CREATIVE,
    ReviewDomain.TRADEMARK: ReviewRole.LEGAL,
    ReviewDomain.LICENSE_CHAIN: ReviewRole.LEGAL,
    ReviewDomain.JURISDICTION_TPM: ReviewRole.LEGAL,
    ReviewDomain.NATIVE_VALIDATION: ReviewRole.TECHNICAL,
    ReviewDomain.DISTRIBUTION_RIGHTS: ReviewRole.LEGAL,
}


class ReviewDecision(str, Enum):
    ACCEPTED = "accepted"
    NEEDS_CHANGES = "needs_changes"
    REJECTED = "rejected"


class ReleaseReadiness(str, Enum):
    BLOCKED = "blocked"
    INDEPENDENT_REVIEW_PENDING = "independent_review_pending"
    REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING = "review_receipts_satisfied_publication_pending"


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _is_ident(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENT.fullmatch(value))


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"20[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z", value
    ):
        raise ReleaseReviewError("review timestamps must be explicit UTC seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReleaseReviewError("invalid UTC timestamp") from exc


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ReleaseCandidate:
    project_id: str
    target_platform_id: str
    world_sha256: str
    native_source_sha256: str
    native_binary_sha256: str
    rights_evidence_sha256: str
    legal_assessment_sha256: str
    originality_screen_sha256: str
    credits_bundle_sha256: str
    channel: ReleaseChannel
    jurisdictions: tuple[str, ...]
    author_ids: tuple[str, ...]
    builder_ids: tuple[str, ...]
    native_build_evidence_sha256: str
    native_gameplay_evidence_sha256: str
    platform_authority_evidence_sha256: str | None = None
    distribution_license_evidence_sha256: str | None = None

    def __post_init__(self) -> None:
        if not _is_ident(self.project_id) or not _is_ident(self.target_platform_id):
            raise ReleaseReviewError("invalid project or native platform identity")
        for name in (
            "world_sha256", "native_source_sha256", "native_binary_sha256",
            "rights_evidence_sha256", "legal_assessment_sha256",
            "originality_screen_sha256", "credits_bundle_sha256", "native_build_evidence_sha256",
            "native_gameplay_evidence_sha256",
        ):
            if not _is_sha(getattr(self, name)):
                raise ReleaseReviewError("missing or invalid required evidence: " + name)
        for name in ("platform_authority_evidence_sha256",
                     "distribution_license_evidence_sha256"):
            value = getattr(self, name)
            if value is not None and not _is_sha(value):
                raise ReleaseReviewError("invalid independent distribution evidence")
        if not isinstance(self.channel, ReleaseChannel):
            raise ReleaseReviewError("invalid release channel")
        if self.channel in {ReleaseChannel.CONSOLE_STOREFRONT,
                            ReleaseChannel.COMMERCIAL_DISTRIBUTION} and (
            not self.platform_authority_evidence_sha256 or
            not self.distribution_license_evidence_sha256
        ):
            raise ReleaseReviewError("commercial/store submissions need channel and distribution evidence")
        if (
            not isinstance(self.jurisdictions, tuple) or
            not self.jurisdictions or len(self.jurisdictions) > 32 or
            len(set(self.jurisdictions)) != len(self.jurisdictions) or
            any(not _is_ident(j) for j in self.jurisdictions) or
            "OTHER" in self.jurisdictions
        ):
            raise ReleaseReviewError("unknown/global jurisdictions are not automatically cleared")
        if len({j.casefold() for j in self.jurisdictions}) != len(self.jurisdictions):
            raise ReleaseReviewError("ambiguous jurisdictions")
        for name in ("author_ids", "builder_ids"):
            identities = getattr(self, name)
            if not isinstance(identities, tuple) or not identities or (
                len({i.casefold() for i in identities}) != len(identities)
            ) or any(not _is_ident(i) for i in identities):
                raise ReleaseReviewError("explicit human author/build operators required")

    def payload(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.review_candidate.v1",
            **{name:getattr(self, name) for name in (
                "project_id", "target_platform_id", "world_sha256",
                "native_source_sha256", "native_binary_sha256",
                "rights_evidence_sha256", "legal_assessment_sha256",
                "originality_screen_sha256", "credits_bundle_sha256", "native_build_evidence_sha256",
                "native_gameplay_evidence_sha256", "platform_authority_evidence_sha256",
                "distribution_license_evidence_sha256",
            )},
            "channel":self.channel.value,"jurisdictions":list(self.jurisdictions),
            "author_ids":list(self.author_ids),"builder_ids":list(self.builder_ids),
        }

    @property
    def digest(self) -> str:
        return sha256(_canonical(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class TrustedReviewer:
    """Trusted external operator provisioned by policy administrators."""
    reviewer_id: str
    key_id: str
    public_key_hex: str
    role: ReviewRole
    allowed_domains: frozenset[ReviewDomain]
    valid_from_utc: str
    expires_utc: str
    revoked: bool = False

    def __post_init__(self) -> None:
        if not _is_ident(self.reviewer_id) or not _is_ident(self.key_id):
            raise ReleaseReviewError("invalid reviewer identity")
        if not isinstance(self.public_key_hex, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.public_key_hex
        ):
            raise ReleaseReviewError("Ed25519 reviewer public key must be 32 bytes")
        if not isinstance(self.role, ReviewRole) or (
            not isinstance(self.allowed_domains, frozenset) or not self.allowed_domains
        ) or any(not isinstance(x, ReviewDomain) for x in self.allowed_domains):
            raise ReleaseReviewError("reviewer must have explicit role and permitted domains")
        if any(_ROLE_BY_DOMAIN[d] is not self.role for d in self.allowed_domains):
            raise ReleaseReviewError("reviewer cannot sign another professional domain")
        if _utc(self.valid_from_utc) >= _utc(self.expires_utc):
            raise ReleaseReviewError("invalid reviewer trust window")
        if type(self.revoked) is not bool:
            raise ReleaseReviewError("revocation must be explicit")


@dataclass(frozen=True, slots=True)
class ReviewAttestation:
    """Detached signature over exact review decision and scoped evidence."""
    key_id: str
    reviewer_id: str
    domain: ReviewDomain
    candidate_sha256: str
    review_evidence_sha256: str
    decision: ReviewDecision
    issued_utc: str
    expires_utc: str
    signature_hex: str

    def __post_init__(self) -> None:
        if not _is_ident(self.key_id) or not _is_ident(self.reviewer_id):
            raise ReleaseReviewError("unsigned review identity")
        if not isinstance(self.domain, ReviewDomain) or not isinstance(self.decision, ReviewDecision):
            raise ReleaseReviewError("reviewer decision and domain must be typed")
        if not _is_sha(self.candidate_sha256) or not _is_sha(self.review_evidence_sha256):
            raise ReleaseReviewError("attestation missing content-bound evidence")
        if not isinstance(self.signature_hex, str) or not re.fullmatch(
            r"[0-9a-f]{128}", self.signature_hex
        ):
            raise ReleaseReviewError("Ed25519 signature requires 64 bytes")
        if _utc(self.issued_utc) >= _utc(self.expires_utc):
            raise ReleaseReviewError("invalid review validity period")

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.review_attestation.v1",
            "key_id":self.key_id,"reviewer_id":self.reviewer_id,
            "domain":self.domain.value,"candidate_sha256":self.candidate_sha256,
            "review_evidence_sha256":self.review_evidence_sha256,
            "decision":self.decision.value,"issued_utc":self.issued_utc,
            "expires_utc":self.expires_utc,
        }

    @property
    def signed_bytes(self) -> bytes:
        return _canonical(self.unsigned_payload())


@dataclass(frozen=True, slots=True)
class ReleaseReviewReceipt:
    candidate_sha256: str
    status: ReleaseReadiness
    verified_attestations: tuple[str, ...]
    unsigned_or_missing_domains: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    pending_reasons: tuple[str, ...]
    receipt_sha256: str
    legal_noninfringement_certified: bool = False
    release_authorized: bool = False
    publisher_approval_granted: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, key) is not False for key in (
            "legal_noninfringement_certified", "release_authorized",
            "publisher_approval_granted",
        )):
            raise ReleaseReviewError("review gate cannot issue legal or distribution authorization")

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema":"skeleton.game_builder.independent_review_gate.v1",
            "candidate_sha256":self.candidate_sha256,
            "status":self.status.value,
            "verified_domains":list(self.verified_attestations),
            "missing_domains":list(self.unsigned_or_missing_domains),
            "blocking_reasons":list(self.blocking_reasons),
            "pending_reasons":list(self.pending_reasons),
            "receipt_sha256":self.receipt_sha256,
            "legal_noninfringement_certified":False,
            "release_authorized":False,
            "publisher_approval_granted":False,
        }


def evaluate_independent_review(
    candidate: ReleaseCandidate, legal: HomebrewLegalAssessment,
    originality: OriginalityReport, *, trust_registry: tuple[TrustedReviewer, ...],
    attestations: tuple[ReviewAttestation, ...], evaluation_utc: str,
) -> ReleaseReviewReceipt:
    """Verify detached signatures against *externally* provisioned trust root."""
    if not isinstance(candidate, ReleaseCandidate) or not isinstance(
        legal, HomebrewLegalAssessment
    ) or not isinstance(originality, OriginalityReport):
        raise ReleaseReviewError("typed release, rights and originality evidence required")
    if not isinstance(trust_registry, tuple) or not isinstance(attestations, tuple):
        raise ReleaseReviewError("immutable reviewer trust and signed receipts required")
    if len(trust_registry) > 128 or len(attestations) > 128:
        raise ReleaseReviewError("review trust batch exceeds bounded audit budget")
    now = _utc(evaluation_utc)
    blockers: set[str] = set()
    pending: set[str] = set()
    if candidate.project_id != legal.project_id or candidate.project_id != originality.project_id:
        blockers.add("MISMATCHED_PROJECT_IDENTITY")
    if candidate.target_platform_id != legal.target_platform_id:
        blockers.add("TARGET_HARDWARE_CHANGED")
    if candidate.jurisdictions != legal.jurisdictions:
        blockers.add("RELEASE_JURISDICTIONS_NOT_IN_LEGAL_ASSESSMENT")
    try:
        default_registry().get(candidate.target_platform_id)
    except PlatformRegistryError:
        blockers.add("TARGET_PLATFORM_NOT_IN_VERIFIED_CATALOGUE")
    if (candidate.legal_assessment_sha256 != legal.assessment_digest or
        candidate.rights_evidence_sha256 != legal.rights_packet_sha256 or
        candidate.originality_screen_sha256 != originality.screen_digest or
        candidate.world_sha256 != originality.artifact_sha256):
        blockers.add("REVIEW_EVIDENCE_DOES_NOT_BIND_TO_BUILT_GAME")
    if not legal.design_admissible or legal.blocking_issues:
        blockers.add("LEGAL_SOURCE_RIGHTS_NOT_ADMISSIBLE")
    if not originality.design_admissible or originality.blockers or (
        originality.overlap_findings or originality.media_overlap_findings
    ):
        blockers.add("PLAGIARISM_OR_ORIGINALITY_REVIEW_UNRESOLVED")
    reviewers = {r.key_id:r for r in trust_registry if isinstance(r, TrustedReviewer)}
    if len(reviewers) != len(trust_registry):
        raise ReleaseReviewError("duplicate or malformed external trust keys")
    if len({r.key_id.casefold() for r in trust_registry}) != len(trust_registry):
        raise ReleaseReviewError("ambiguous signer key identity in external reviewer registry")
    if len({r.reviewer_id.casefold() for r in trust_registry}) != len(trust_registry):
        raise ReleaseReviewError("multiple keys for one reviewer require separate key rotation")
    if len({r.public_key_hex for r in trust_registry}) != len(trust_registry):
        raise ReleaseReviewError("one Ed25519 private key cannot represent multiple independent reviewers")
    seen_domains: set[ReviewDomain] = set()
    approved_domains: set[ReviewDomain] = set()
    covered_roles: set[ReviewRole] = set()
    valid_signers: set[str] = set()
    for att in attestations:
        if not isinstance(att, ReviewAttestation):
            raise ReleaseReviewError("malformed reviewer attestation")
        if att.domain in seen_domains:
            blockers.add("DUPLICATE_OR_CONFLICTING_ATTESTATIONS:" + att.domain.value)
            continue
        seen_domains.add(att.domain)
        if att.candidate_sha256 != candidate.digest:
            blockers.add("STALE_OR_FOREIGN_ARTIFACT_SIGNATURE:" + att.domain.value)
            continue
        reviewer = reviewers.get(att.key_id)
        if reviewer is None or reviewer.reviewer_id != att.reviewer_id:
            blockers.add("REVIEW_SIGNER_NOT_IN_EXTERNAL_TRUST_REGISTRY:" + att.domain.value)
            continue
        if reviewer.revoked:
            blockers.add("REVOKED_REVIEWER_KEY:" + att.domain.value)
            continue
        if (reviewer.reviewer_id.casefold() in {
            person.casefold() for person in (*candidate.author_ids, *candidate.builder_ids)
        }):
            blockers.add("NON_INDEPENDENT_SELF_REVIEW:" + att.domain.value)
            continue
        if att.domain not in reviewer.allowed_domains or _ROLE_BY_DOMAIN[att.domain] != reviewer.role:
            blockers.add("REVIEWER_DOMAIN_ROLE_MISMATCH:" + att.domain.value)
            continue
        if not (
            _utc(reviewer.valid_from_utc) <= _utc(att.issued_utc) <= now
            <= _utc(att.expires_utc) <= _utc(reviewer.expires_utc)
        ):
            blockers.add("REVIEW_TIMESTAMP_OUTSIDE_TRUST_WINDOW:" + att.domain.value)
            continue
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(
                reviewer.public_key_hex
            )).verify(bytes.fromhex(att.signature_hex), att.signed_bytes)
        except ImportError as exc:
            raise ReleaseReviewError("signature verification provider unavailable") from exc
        except (InvalidSignature, ValueError):
            blockers.add("INVALID_REVIEW_SIGNATURE:" + att.domain.value)
            continue
        if att.decision is ReviewDecision.REJECTED:
            blockers.add("REVIEWER_REJECTED:" + att.domain.value)
            continue
        if att.decision is ReviewDecision.NEEDS_CHANGES:
            pending.add("REVIEWER_REQUIRES_CHANGES:" + att.domain.value)
            continue
        covered_roles.add(reviewer.role)
        valid_signers.add(reviewer.reviewer_id)
        approved_domains.add(att.domain)
    missing = set(ReviewDomain) - approved_domains
    if missing:
        pending.add("INDEPENDENT_DOMAIN_REVIEW_INCOMPLETE")
    if set(ReviewRole) - covered_roles or len(valid_signers) < 3:
        pending.add("INDEPENDENT_CREATIVE_LEGAL_AND_TECHNICAL_REVIEW_REQUIRED")
    if not trust_registry:
        pending.add("EXTERNALLY_PROVISIONED_REVIEWER_TRUST_ROOT_MISSING")
    if not candidate.platform_authority_evidence_sha256 and candidate.channel is ReleaseChannel.CONSOLE_STOREFRONT:
        blockers.add("CONSOLE_STOREFRONT_AUTHORITY_UNVERIFIED")
    if candidate.channel is ReleaseChannel.COMMERCIAL_DISTRIBUTION and (
        not candidate.distribution_license_evidence_sha256
    ):
        blockers.add("COMMERCIAL_DISTRIBUTION_PERMISSION_UNVERIFIED")
    if blockers:
        state = ReleaseReadiness.BLOCKED
    elif pending:
        state = ReleaseReadiness.INDEPENDENT_REVIEW_PENDING
    else:
        state = ReleaseReadiness.REVIEW_RECEIPTS_SATISFIED_PUBLICATION_PENDING
        pending.add("FINAL_HUMAN_PUBLISHER_DECISION_REQUIRED")
    data: dict[str, object] = {
        "schema":"skeleton.game_builder.release_evaluation.v1",
        "candidate_sha256":candidate.digest,
        "status":state.value,
        "verified_domains":sorted(d.value for d in approved_domains),
        "missing_domains":sorted(d.value for d in missing),
        "blocking_reasons":sorted(blockers),"pending_reasons":sorted(pending),
        "attestation_signatures":sorted(a.signature_hex for a in attestations),
        "trust_reviewers":sorted(reviewers),
        "evaluation_utc":evaluation_utc,
    }
    digest = sha256(_canonical(data)).hexdigest()
    return ReleaseReviewReceipt(
        candidate_sha256=candidate.digest,
        status=state,
        verified_attestations=tuple(sorted(d.value for d in approved_domains)),
        unsigned_or_missing_domains=tuple(sorted(d.value for d in missing)),
        blocking_reasons=tuple(sorted(blockers)),
        pending_reasons=tuple(sorted(pending)),
        receipt_sha256=digest,
    )

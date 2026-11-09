"""Consumer game release evidence verification without self-attestation.

An offline source export is not the same thing as a consumer-release approval.
This module verifies independently issued HMAC evidence over one exact
content-addressed source package, with typed role separations. Trust anchors
are injected by the operator's runtime; never serialize signing secrets into
game content or project manifests. HMACs prove possession of a configured key,
not real-world legal correctness or store acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import hmac
import re
from typing import Mapping, Sequence

from .contracts import canonical_digest, canonical_json
from .original_game_studio import StudioRun, ConsumerReview


class ReleaseEvidenceError(ValueError):
    """Signed release proof failed its trust, freshness or identity conditions."""


class EvidenceKind(str, Enum):
    RIGHTS = "rights_reviewed"
    PLAYTEST = "human_playtested"
    HARDWARE = "platform_hardware_tested"
    ACCESSIBILITY = "accessibility_reviewed"
    LOCALIZATION = "localization_reviewed"
    MALWARE = "malware_scan_passed"
    CODESIGN = "code_signed"
    PLATFORM_PERMISSION = "platform_permission_verified"
    PUBLICATION = "approved_for_publication"


class ReviewerRole(str, Enum):
    LEGAL = "legal"
    PLAYER_QA = "player_qa"
    PLATFORM_QA = "platform_qa"
    ACCESSIBILITY_QA = "accessibility_qa"
    LOCALIZATION_QA = "localization_qa"
    SECURITY_QA = "security_qa"
    SIGNING = "signing"
    PLATFORM_RIGHTS = "platform_rights"
    PUBLISHER = "publisher"


ROLES = {
    EvidenceKind.RIGHTS: ReviewerRole.LEGAL,
    EvidenceKind.PLAYTEST: ReviewerRole.PLAYER_QA,
    EvidenceKind.HARDWARE: ReviewerRole.PLATFORM_QA,
    EvidenceKind.ACCESSIBILITY: ReviewerRole.ACCESSIBILITY_QA,
    EvidenceKind.LOCALIZATION: ReviewerRole.LOCALIZATION_QA,
    EvidenceKind.MALWARE: ReviewerRole.SECURITY_QA,
    EvidenceKind.CODESIGN: ReviewerRole.SIGNING,
    EvidenceKind.PLATFORM_PERMISSION: ReviewerRole.PLATFORM_RIGHTS,
    EvidenceKind.PUBLICATION: ReviewerRole.PUBLISHER,
}
MAX_AGE_DAYS = {
    EvidenceKind.MALWARE: 30,
    EvidenceKind.HARDWARE: 180,
    EvidenceKind.PLAYTEST: 365,
    EvidenceKind.PUBLICATION: 90,
}


@dataclass(frozen=True, slots=True)
class SignedReleaseEvidence:
    kind: EvidenceKind
    issuer_id: str
    subject_manifest_digest: str
    evidence_digest: str
    observed_at: str
    signature: str

    def __post_init__(self):
        if not isinstance(self.kind, EvidenceKind):
            raise ReleaseEvidenceError("unknown consumer evidence kind")
        if not isinstance(self.issuer_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{2,95}", self.issuer_id
        ):
            raise ReleaseEvidenceError("invalid reviewer identity")
        for field in ("subject_manifest_digest", "evidence_digest", "signature"):
            if not isinstance(getattr(self, field), str) or not re.fullmatch(
                r"[a-f0-9]{64}", getattr(self, field)
            ):
                raise ReleaseEvidenceError("evidence requires SHA-256 digests")
        if not isinstance(self.observed_at, str):
            raise ReleaseEvidenceError("evidence timestamp required")
        _date(self.observed_at)

    def signed_body(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.signed_release_evidence.v1",
            "kind": self.kind.value,
            "issuer_id": self.issuer_id,
            "subject_manifest_digest": self.subject_manifest_digest,
            "evidence_digest": self.evidence_digest,
            "observed_at": self.observed_at,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.signed_body(), "signature": self.signature}


@dataclass(frozen=True, slots=True)
class TrustedReviewer:
    issuer_id: str
    role: ReviewerRole
    key: bytes

    def __post_init__(self):
        if not isinstance(self.issuer_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{2,95}", self.issuer_id
        ):
            raise ReleaseEvidenceError("invalid trusted reviewer")
        if not isinstance(self.role, ReviewerRole):
            raise ReleaseEvidenceError("trusted reviewer role required")
        if not isinstance(self.key, bytes) or len(self.key) < 32:
            raise ReleaseEvidenceError("trusted key must be 256-bit or stronger")


def _date(stamp: str) -> datetime:
    try:
        value = datetime.fromisoformat(stamp)
    except ValueError as exc:
        raise ReleaseEvidenceError("invalid ISO-8601 evidence time") from exc
    if (value.tzinfo is None or value.utcoffset() is None
            or value.utcoffset().total_seconds() != 0
            or value.second is None):
        raise ReleaseEvidenceError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _mac(key: bytes, body: dict[str, object]) -> str:
    return hmac.new(key, canonical_json(body).encode("utf-8"), sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class ConsumerAssurance:
    source_manifest_digest: str
    evaluated_at: str
    proof: ConsumerReview
    reviewers: tuple[tuple[str, str], ...]
    evidence_receipts: tuple[dict[str, object], ...]

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.consumer_assurance.v1",
            "source_manifest_digest": self.source_manifest_digest,
            "evaluated_at": self.evaluated_at,
            "reviewers": [{"kind": kind, "issuer_id": issuer}
                          for kind, issuer in self.reviewers],
            "evidence_receipts": list(self.evidence_receipts),
            "consumer_review": self.proof.to_payload(),
            "independent_trust_keys_included": False,
            "not_a_substitute_for_real_world_rights": True,
        }


def assess_consumer_release(
    run: StudioRun,
    evidence: Sequence[SignedReleaseEvidence],
    trust: Mapping[str, TrustedReviewer],
    *,
    now_utc: datetime,
    authorized: bool,
) -> ConsumerAssurance:
    """Verify real evidence from separate legal, QA, security, signing authorities.

    No caller-supplied boolean can clear an assurance gate. Each evidence claim
    must bind exactly this release source manifest, pass HMAC constant-time
    verification and be fresh for its specific kind. A publisher's signature
    may only approve *after* all other independent controls have passed.
    """
    if not authorized:
        raise PermissionError("release assurance requires authenticated operator")
    if not isinstance(run, StudioRun) or not run.mirror.passed:
        raise ReleaseEvidenceError("canonical successful studio run required")
    if not isinstance(evidence, (tuple, list)) or len(evidence) > len(EvidenceKind):
        raise ReleaseEvidenceError("unexpected evidence count")
    if not isinstance(trust, Mapping) or len(trust) > 64:
        raise ReleaseEvidenceError("trusted reviewer list exceeded")
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        raise ReleaseEvidenceError("UTC evaluation clock required")
    if now_utc.utcoffset().total_seconds() != 0:
        raise ReleaseEvidenceError("evaluation time must be UTC")
    now = now_utc.astimezone(timezone.utc)
    manifest_digest = run.package.manifest["manifest_digest"]
    accepted: dict[EvidenceKind, SignedReleaseEvidence] = {}
    for row in evidence:
        if not isinstance(row, SignedReleaseEvidence):
            raise ReleaseEvidenceError("typed signed evidence required")
        if row.kind in accepted:
            raise ReleaseEvidenceError("duplicate consumer evidence type")
        if row.subject_manifest_digest != manifest_digest:
            raise ReleaseEvidenceError("review attests a different source release")
        reviewer = trust.get(row.issuer_id)
        if not isinstance(reviewer, TrustedReviewer) or reviewer.issuer_id != row.issuer_id:
            raise ReleaseEvidenceError("independent reviewer has no configured trust key")
        if reviewer.role is not ROLES[row.kind]:
            raise ReleaseEvidenceError("reviewer cannot sign outside designated authority")
        actual = _mac(reviewer.key, row.signed_body())
        if not hmac.compare_digest(actual, row.signature):
            raise ReleaseEvidenceError("review evidence signature invalid")
        date = _date(row.observed_at)
        if date > now:
            raise ReleaseEvidenceError("consumer review evidence is from the future")
        if row.kind in MAX_AGE_DAYS and (now - date).days >= MAX_AGE_DAYS[row.kind]:
            raise ReleaseEvidenceError("consumer review evidence expired")
        accepted[row.kind] = row
    if EvidenceKind.PUBLICATION in accepted and (
        set(accepted) != set(EvidenceKind)
        or len({row.issuer_id for row in accepted.values()}) != len(EvidenceKind)
    ):
        raise ReleaseEvidenceError("publication approval requires all independent reviews")
    # Approved status is based on independent signed claims, never on user
    # supplied flags or the source compiler's self-reported confidence.
    proof = replace(
        run.consumer,
        **{kind.value: kind in accepted for kind in EvidenceKind},
    )
    return ConsumerAssurance(
        source_manifest_digest=manifest_digest,
        evaluated_at=now.isoformat(),
        proof=proof,
        reviewers=tuple(sorted((kind.value, item.issuer_id)
                               for kind, item in accepted.items())),
        evidence_receipts=tuple(
            {"kind": kind.value, "receipt_digest": canonical_digest(item.to_payload())}
            for kind, item in sorted(accepted.items(), key=lambda row: row[0].value)
        ),
    )


__all__ = [
    "ReleaseEvidenceError", "EvidenceKind", "ReviewerRole", "SignedReleaseEvidence",
    "TrustedReviewer", "ConsumerAssurance", "assess_consumer_release",
]

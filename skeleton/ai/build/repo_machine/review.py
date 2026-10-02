"""Independent review and verification routing for repository changes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


class ReviewRoutingError(RuntimeError):
    pass


def _identity(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > 192:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _parse_utc_timestamp(value: str, field: str) -> datetime:
    text = str(value).strip()
    if not text.endswith("Z"):
        raise ValueError(f"{field} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must be UTC")
    return parsed


def _utc_timestamp(value: str, field: str) -> str:
    text = str(value).strip()
    _parse_utc_timestamp(text, field)
    return text


def _evidence_refs(values: Iterable[str], field: str) -> tuple[str, ...]:
    refs = tuple(_identity(item, field) for item in values)
    if not refs:
        raise ValueError(f"{field} requires at least one reference")
    if len(refs) != len(set(refs)):
        raise ValueError(f"{field} references must be unique")
    return refs


@dataclass(frozen=True, slots=True)
class ReviewRoute:
    author_id: str
    reviewer_id: str
    verifier_id: str
    exception_ref: str | None = None

    def __post_init__(self) -> None:
        author = _identity(self.author_id, "author_id")
        reviewer = _identity(self.reviewer_id, "reviewer_id")
        verifier = _identity(self.verifier_id, "verifier_id")
        object.__setattr__(self, "author_id", author)
        object.__setattr__(self, "reviewer_id", reviewer)
        object.__setattr__(self, "verifier_id", verifier)
        if len({author, reviewer, verifier}) != 3:
            raise ReviewRoutingError(
                "author, reviewer, and verifier must be independent identities"
            )
        if self.exception_ref is not None:
            ref = str(self.exception_ref).strip()
            if not ref or len(ref) > 512:
                raise ReviewRoutingError("independence exception_ref is invalid")
            object.__setattr__(self, "exception_ref", ref)


@dataclass(frozen=True, slots=True)
class ReviewVerdict:
    reviewer_id: str
    decision: str
    evidence_refs: tuple[str, ...]
    reviewed_at_utc: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reviewer_id",
            _identity(self.reviewer_id, "reviewer_id"),
        )
        if self.decision not in {"approve", "block"}:
            raise ValueError("review decision must be approve or block")
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence_refs(self.evidence_refs, "review_evidence_ref"),
        )
        object.__setattr__(
            self,
            "reviewed_at_utc",
            _utc_timestamp(self.reviewed_at_utc, "reviewed_at_utc"),
        )


@dataclass(frozen=True, slots=True)
class VerificationVerdict:
    verifier_id: str
    passed: bool
    evidence_refs: tuple[str, ...]
    verified_at_utc: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "verifier_id",
            _identity(self.verifier_id, "verifier_id"),
        )
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence_refs(self.evidence_refs, "verification_evidence_ref"),
        )
        object.__setattr__(
            self,
            "verified_at_utc",
            _utc_timestamp(self.verified_at_utc, "verified_at_utc"),
        )


def route_independent_review(
    author_id: str,
    reviewer_candidates: Iterable[str],
    verifier_candidates: Iterable[str],
) -> ReviewRoute:
    author = _identity(author_id, "author_id")
    reviewers = sorted({_identity(item, "reviewer") for item in reviewer_candidates if str(item).strip()})
    verifiers = sorted({_identity(item, "verifier") for item in verifier_candidates if str(item).strip()})
    reviewer = next((item for item in reviewers if item != author), None)
    if reviewer is None:
        raise ReviewRoutingError("no independent reviewer is available")
    verifier = next(
        (item for item in verifiers if item not in {author, reviewer}),
        None,
    )
    if verifier is None:
        raise ReviewRoutingError("no independent verifier is available")
    return ReviewRoute(author, reviewer, verifier)


def validate_verdicts(
    route: ReviewRoute,
    review: ReviewVerdict,
    verification: VerificationVerdict,
) -> None:
    if review.reviewer_id != route.reviewer_id:
        raise ReviewRoutingError("review verdict identity does not match route")
    if verification.verifier_id != route.verifier_id:
        raise ReviewRoutingError("verification verdict identity does not match route")
    if review.decision != "approve":
        raise ReviewRoutingError("blocked review cannot be promoted")
    if verification.passed is not True:
        raise ReviewRoutingError("failed verification cannot be promoted")
    reviewed_at = _parse_utc_timestamp(review.reviewed_at_utc, "reviewed_at_utc")
    verified_at = _parse_utc_timestamp(
        verification.verified_at_utc,
        "verified_at_utc",
    )
    if verified_at < reviewed_at:
        raise ReviewRoutingError(
            "verification cannot predate the approved review"
        )


__all__ = [
    "ReviewRoute",
    "ReviewRoutingError",
    "ReviewVerdict",
    "VerificationVerdict",
    "route_independent_review",
    "validate_verdicts",
]

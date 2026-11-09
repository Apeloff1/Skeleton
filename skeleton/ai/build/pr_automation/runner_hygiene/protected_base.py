"""Protected-base evidence and fail-closed enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .types import Finding, HeadBinding, HygienePolicy, HygieneVerdict, valid_ref, valid_sha


@dataclass(frozen=True, slots=True)
class ProtectedBaseEvidence:
    ref: str
    sha: str
    protected: bool | None
    enforcement: str | None = None
    required_reviews: int | None = None
    require_code_owner_reviews: bool | None = None
    allow_force_pushes: bool | None = None
    allow_deletions: bool | None = None
    raw: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not valid_ref(self.ref):
            raise ValueError("invalid protected base ref")
        if not valid_sha(self.sha):
            raise ValueError("protected base sha must be canonical")


@dataclass(frozen=True, slots=True)
class ProtectedBaseAssessment:
    verdict: HygieneVerdict
    reasons: tuple[str, ...]
    findings: tuple[Finding, ...]
    evidence: ProtectedBaseEvidence | None


def parse_protection_payload(
    ref: str,
    sha: str,
    payload: Mapping[str, Any] | None,
) -> ProtectedBaseEvidence:
    """Parse GitHub branch-protection style payloads fail-closed.

    Missing or malformed protection evidence yields ``protected=None`` so
    callers that require protection deny by default.
    """
    if payload is None:
        return ProtectedBaseEvidence(ref=ref, sha=sha, protected=None)

    enabled = payload.get("enabled")
    if isinstance(enabled, bool):
        protected = enabled
    elif "protection" in payload or "required_status_checks" in payload or "required_pull_request_reviews" in payload:
        protected = True
    else:
        protected = None

    reviews = payload.get("required_pull_request_reviews") or {}
    required_reviews = None
    require_owners = None
    if isinstance(reviews, Mapping):
        count = reviews.get("required_approving_review_count")
        if isinstance(count, int) and count >= 0:
            required_reviews = count
        owners = reviews.get("require_code_owner_reviews")
        if isinstance(owners, bool):
            require_owners = owners

    allow_force = payload.get("allow_force_pushes")
    if isinstance(allow_force, Mapping):
        allow_force = allow_force.get("enabled")
    allow_del = payload.get("allow_deletions")
    if isinstance(allow_del, Mapping):
        allow_del = allow_del.get("enabled")

    enforcement = payload.get("enforcement_level")
    if enforcement is not None and not isinstance(enforcement, str):
        enforcement = str(enforcement)

    return ProtectedBaseEvidence(
        ref=ref,
        sha=sha,
        protected=protected,
        enforcement=enforcement if isinstance(enforcement, str) else None,
        required_reviews=required_reviews,
        require_code_owner_reviews=require_owners,
        allow_force_pushes=allow_force if isinstance(allow_force, bool) else None,
        allow_deletions=allow_del if isinstance(allow_del, bool) else None,
        raw=dict(payload),
    )


def assess_protected_base(
    binding: HeadBinding,
    evidence: ProtectedBaseEvidence | None,
    policy: HygienePolicy,
) -> ProtectedBaseAssessment:
    findings: list[Finding] = []
    reasons: list[str] = []

    if binding.base_ref not in policy.allowed_bases:
        reasons.append("base_not_allowed")
        findings.append(
            Finding(
                code="protected_base.not_allowed",
                severity="high",
                message=f"base {binding.base_ref!r} is outside the allowed set",
                subject=binding.base_ref,
            )
        )

    if evidence is None:
        if policy.protected_base_required:
            reasons.append("protected_base_evidence_missing")
            findings.append(
                Finding(
                    code="protected_base.missing",
                    severity="critical",
                    message="protected-base evidence is required but missing",
                    subject=binding.base_ref,
                )
            )
        verdict = HygieneVerdict.DENY if reasons else HygieneVerdict.HOLD
        return ProtectedBaseAssessment(
            verdict=verdict,
            reasons=tuple(reasons) or ("protected_base_unknown",),
            findings=tuple(findings),
            evidence=None,
        )

    if evidence.ref != binding.base_ref:
        reasons.append("protected_base_ref_mismatch")
        findings.append(
            Finding(
                code="protected_base.ref_mismatch",
                severity="critical",
                message=f"evidence ref {evidence.ref!r} != binding base {binding.base_ref!r}",
                subject=evidence.ref,
            )
        )

    if evidence.sha != binding.base_sha:
        reasons.append("protected_base_sha_mismatch")
        findings.append(
            Finding(
                code="protected_base.sha_mismatch",
                severity="critical",
                message=(
                    f"evidence sha {evidence.sha} != binding base sha {binding.base_sha}"
                ),
                subject=evidence.sha,
            )
        )

    if policy.protected_base_required:
        if evidence.protected is not True:
            reasons.append("protected_base_not_confirmed")
            findings.append(
                Finding(
                    code="protected_base.unconfirmed",
                    severity="critical",
                    message=(
                        "base branch protection must be confirmed True; "
                        f"got {evidence.protected!r}"
                    ),
                    subject=binding.base_ref,
                )
            )
        if evidence.allow_force_pushes is True:
            reasons.append("force_pushes_allowed")
            findings.append(
                Finding(
                    code="protected_base.force_pushes",
                    severity="high",
                    message="protected base allows force pushes",
                    subject=binding.base_ref,
                )
            )
        if evidence.allow_deletions is True:
            reasons.append("deletions_allowed")
            findings.append(
                Finding(
                    code="protected_base.deletions",
                    severity="high",
                    message="protected base allows deletions",
                    subject=binding.base_ref,
                )
            )

    if reasons:
        verdict = HygieneVerdict.DENY
    else:
        verdict = HygieneVerdict.ALLOW
        reasons.append("protected_base_ok")

    return ProtectedBaseAssessment(
        verdict=verdict,
        reasons=tuple(reasons),
        findings=tuple(findings),
        evidence=evidence,
    )


__all__ = [
    "ProtectedBaseAssessment",
    "ProtectedBaseEvidence",
    "assess_protected_base",
    "parse_protection_payload",
]

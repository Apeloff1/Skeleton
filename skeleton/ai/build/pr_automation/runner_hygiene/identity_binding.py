"""Exact-head and same-repository identity binding helpers.

These helpers never authorize mutation. They only decide whether a candidate
identity is coherent and whether live evidence still matches the expected head.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .types import (
    CheckObservation,
    Finding,
    HeadBinding,
    HygienePolicy,
    HygieneVerdict,
    ReviewObservation,
    valid_ref,
    valid_repository,
    valid_sha,
)


@dataclass(frozen=True, slots=True)
class BindingAssessment:
    verdict: HygieneVerdict
    reasons: tuple[str, ...]
    findings: tuple[Finding, ...]
    same_repository: bool
    base_allowed: bool
    head_coherent: bool

    @property
    def admitted(self) -> bool:
        return self.verdict is HygieneVerdict.ALLOW


def build_binding(
    *,
    repository: str,
    pr_number: int,
    head_sha: str,
    head_ref: str,
    head_repository: str,
    base_ref: str,
    base_sha: str,
) -> HeadBinding:
    """Construct a binding, raising on malformed identity."""
    return HeadBinding(
        repository=repository,
        pr_number=pr_number,
        head_sha=head_sha,
        head_ref=head_ref,
        head_repository=head_repository,
        base_ref=base_ref,
        base_sha=base_sha,
    )


def assess_binding(binding: HeadBinding, policy: HygienePolicy) -> BindingAssessment:
    reasons: list[str] = []
    findings: list[Finding] = []

    head_coherent = (
        valid_sha(binding.head_sha)
        and valid_sha(binding.base_sha)
        and valid_ref(binding.head_ref)
        and valid_ref(binding.base_ref)
        and valid_repository(binding.repository)
        and valid_repository(binding.head_repository)
    )
    if not head_coherent:
        reasons.append("identity_malformed")
        findings.append(
            Finding(
                code="identity.malformed",
                severity="critical",
                message="head/base identity failed structural validation",
                subject=binding.binding_key(),
            )
        )

    same_repository = binding.same_repository_head
    if policy.require_same_repository_head and not same_repository:
        reasons.append("fork_head_denied")
        findings.append(
            Finding(
                code="identity.fork_head",
                severity="high",
                message=(
                    f"head repository {binding.head_repository} differs from "
                    f"{binding.repository}; same-repository heads required"
                ),
                subject=binding.binding_key(),
            )
        )

    base_allowed = binding.base_ref in policy.allowed_bases
    if not base_allowed:
        reasons.append("base_not_allowed")
        findings.append(
            Finding(
                code="identity.base_denied",
                severity="high",
                message=f"base ref {binding.base_ref!r} not in allowed bases",
                subject=binding.base_ref,
            )
        )

    if reasons:
        verdict = HygieneVerdict.DENY
    else:
        verdict = HygieneVerdict.ALLOW
        reasons.append("identity_bound")

    return BindingAssessment(
        verdict=verdict,
        reasons=tuple(reasons),
        findings=tuple(findings),
        same_repository=same_repository,
        base_allowed=base_allowed,
        head_coherent=head_coherent,
    )


def filter_checks_for_head(
    checks: Sequence[CheckObservation],
    expected_head: str,
    *,
    require_exact: bool,
) -> tuple[tuple[CheckObservation, ...], tuple[Finding, ...]]:
    if not valid_sha(expected_head):
        return (), (
            Finding(
                code="binding.invalid_expected_head",
                severity="critical",
                message="expected head SHA is not canonical",
            ),
        )
    matched: list[CheckObservation] = []
    findings: list[Finding] = []
    for check in checks:
        if check.matches_head(expected_head):
            matched.append(check)
            continue
        if require_exact:
            findings.append(
                Finding(
                    code="binding.check_head_mismatch",
                    severity="high",
                    message=(
                        f"check {check.context!r} bound to {check.head_sha}, "
                        f"expected {expected_head}"
                    ),
                    subject=check.context,
                )
            )
    return tuple(matched), tuple(findings)


def filter_reviews_for_head(
    reviews: Sequence[ReviewObservation],
    expected_head: str,
    *,
    require_exact: bool,
) -> tuple[tuple[ReviewObservation, ...], tuple[Finding, ...]]:
    if not valid_sha(expected_head):
        return (), (
            Finding(
                code="binding.invalid_expected_head",
                severity="critical",
                message="expected head SHA is not canonical",
            ),
        )
    matched: list[ReviewObservation] = []
    findings: list[Finding] = []
    for review in reviews:
        if review.matches_head(expected_head):
            matched.append(review)
            continue
        if require_exact:
            findings.append(
                Finding(
                    code="binding.review_head_mismatch",
                    severity="high",
                    message=(
                        f"review by {review.login!r} bound to {review.commit_id!r}, "
                        f"expected {expected_head}"
                    ),
                    subject=review.login,
                )
            )
    return tuple(matched), tuple(findings)


def latest_check_per_context(
    checks: Iterable[CheckObservation],
) -> dict[str, CheckObservation]:
    """Reduce to latest observation per context using updated_at then insertion."""
    latest: dict[str, CheckObservation] = {}
    for check in checks:
        prior = latest.get(check.context)
        if prior is None:
            latest[check.context] = check
            continue
        prior_ts = prior.updated_at or ""
        new_ts = check.updated_at or ""
        if new_ts >= prior_ts:
            latest[check.context] = check
    return latest


def approvals_matching_head(
    reviews: Sequence[ReviewObservation],
    expected_head: str,
) -> tuple[str, ...]:
    approved: list[str] = []
    seen: set[str] = set()
    for review in reviews:
        state = review.state.casefold()
        if state != "approved":
            continue
        if not review.matches_head(expected_head):
            continue
        key = review.login.casefold()
        if key in seen:
            continue
        seen.add(key)
        approved.append(review.login)
    return tuple(approved)


def changes_requested_matching_head(
    reviews: Sequence[ReviewObservation],
    expected_head: str,
) -> tuple[str, ...]:
    requested: list[str] = []
    seen: set[str] = set()
    for review in reviews:
        state = review.state.casefold().replace(" ", "_")
        if state not in {"changes_requested", "changes-requested"}:
            continue
        if not review.matches_head(expected_head):
            continue
        key = review.login.casefold()
        if key in seen:
            continue
        seen.add(key)
        requested.append(review.login)
    return tuple(requested)


def assert_live_head_unchanged(
    expected: HeadBinding,
    live_head_sha: str,
    live_base_sha: str,
) -> tuple[bool, tuple[Finding, ...]]:
    findings: list[Finding] = []
    ok = True
    if not valid_sha(live_head_sha) or live_head_sha != expected.head_sha:
        ok = False
        findings.append(
            Finding(
                code="binding.live_head_moved",
                severity="critical",
                message=(
                    f"live head {live_head_sha!r} differs from bound "
                    f"{expected.head_sha}"
                ),
                subject=expected.binding_key(),
            )
        )
    if not valid_sha(live_base_sha) or live_base_sha != expected.base_sha:
        ok = False
        findings.append(
            Finding(
                code="binding.live_base_moved",
                severity="critical",
                message=(
                    f"live base {live_base_sha!r} differs from bound "
                    f"{expected.base_sha}"
                ),
                subject=expected.binding_key(),
            )
        )
    return ok, tuple(findings)


__all__ = [
    "BindingAssessment",
    "approvals_matching_head",
    "assess_binding",
    "assert_live_head_unchanged",
    "build_binding",
    "changes_requested_matching_head",
    "filter_checks_for_head",
    "filter_reviews_for_head",
    "latest_check_per_context",
]

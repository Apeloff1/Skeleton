"""Admission evidence aggregation and exact-head reduction.

Collectors here are pure reducers over already-fetched observations. Network
I/O belongs to adapters outside this package (and outside Pack E mutation
authority).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .identity_binding import (
    approvals_matching_head,
    changes_requested_matching_head,
    filter_checks_for_head,
    filter_reviews_for_head,
    latest_check_per_context,
)
from .pagination import PagedResult, assess_pagination, merge_cursors
from .protected_base import ProtectedBaseEvidence, assess_protected_base
from .trust_surface import InventoryTrust, classify_inventory
from .types import (
    CheckObservation,
    Finding,
    GateState,
    HeadBinding,
    HygienePolicy,
    HygieneVerdict,
    PaginationCursor,
    PathObservation,
    RateLimitSnapshot,
    ReviewObservation,
    fingerprint,
)


@dataclass(frozen=True, slots=True)
class CheckSummary:
    required: tuple[str, ...]
    states: Mapping[str, GateState]
    missing: tuple[str, ...]
    failing: tuple[str, ...]
    pending: tuple[str, ...]
    unknown: tuple[str, ...]
    all_success: bool
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    approvals: tuple[str, ...]
    changes_requested: tuple[str, ...]
    unmatched_reviews: int
    findings: tuple[Finding, ...]

    @property
    def clean(self) -> bool:
        return not self.changes_requested and not self.findings


@dataclass(frozen=True, slots=True)
class AdmissionEvidence:
    binding: HeadBinding
    checks: CheckSummary
    reviews: ReviewSummary
    inventory: InventoryTrust
    protected_base: ProtectedBaseEvidence | None
    pagination: PaginationCursor
    rate_limit: RateLimitSnapshot | None
    draft: bool = False
    merged: bool = False
    closed: bool = False
    mergeable: bool | None = None
    unresolved_threads: int | None = None
    labels: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        return fingerprint(
            {
                "binding": self.binding.fingerprint(),
                "checks": {
                    "required": list(self.checks.required),
                    "states": {k: v.value for k, v in self.checks.states.items()},
                    "missing": list(self.checks.missing),
                    "failing": list(self.checks.failing),
                    "pending": list(self.checks.pending),
                    "unknown": list(self.checks.unknown),
                },
                "reviews": {
                    "approvals": list(self.reviews.approvals),
                    "changes_requested": list(self.reviews.changes_requested),
                    "unmatched_reviews": self.reviews.unmatched_reviews,
                },
                "inventory": {
                    "paths": [p.path for p in self.inventory.paths],
                    "privileged": list(self.inventory.privileged_paths),
                    "additions": self.inventory.total_additions,
                    "deletions": self.inventory.total_deletions,
                },
                "protected_base": None
                if self.protected_base is None
                else {
                    "ref": self.protected_base.ref,
                    "sha": self.protected_base.sha,
                    "protected": self.protected_base.protected,
                },
                "pagination": {
                    "status": self.pagination.status.value,
                    "truncated": self.pagination.truncated,
                    "items_seen": self.pagination.items_seen,
                },
                "draft": self.draft,
                "merged": self.merged,
                "closed": self.closed,
                "mergeable": self.mergeable,
                "unresolved_threads": self.unresolved_threads,
                "labels": list(self.labels),
            }
        )


def reduce_checks(
    observations: Sequence[CheckObservation],
    binding: HeadBinding,
    policy: HygienePolicy,
) -> CheckSummary:
    matched, mismatch_findings = filter_checks_for_head(
        observations,
        binding.head_sha,
        require_exact=policy.require_exact_head_checks,
    )
    latest = latest_check_per_context(matched)
    states: dict[str, GateState] = {}
    missing: list[str] = []
    failing: list[str] = []
    pending: list[str] = []
    unknown: list[str] = []
    findings = list(mismatch_findings)
    for context in policy.required_check_contexts:
        obs = latest.get(context)
        if obs is None:
            missing.append(context)
            states[context] = GateState.MISSING
            continue
        state = obs.state
        states[context] = state
        if state is GateState.SUCCESS:
            continue
        if state is GateState.FAILURE:
            failing.append(context)
        elif state is GateState.PENDING:
            pending.append(context)
        elif state is GateState.MISSING:
            missing.append(context)
        else:
            unknown.append(context)
            findings.append(
                Finding(
                    code="evidence.check_unknown",
                    severity="high",
                    message=f"required check {context!r} in unknown state",
                    subject=context,
                )
            )
    all_success = not missing and not failing and not pending and not unknown
    return CheckSummary(
        required=policy.required_check_contexts,
        states=states,
        missing=tuple(missing),
        failing=tuple(failing),
        pending=tuple(pending),
        unknown=tuple(unknown),
        all_success=all_success,
        findings=tuple(findings),
    )


def reduce_reviews(
    observations: Sequence[ReviewObservation],
    binding: HeadBinding,
    policy: HygienePolicy,
) -> ReviewSummary:
    matched, findings = filter_reviews_for_head(
        observations,
        binding.head_sha,
        require_exact=policy.require_exact_head_reviews,
    )
    approvals = approvals_matching_head(matched, binding.head_sha)
    changes = changes_requested_matching_head(matched, binding.head_sha)
    unmatched = len(observations) - len(matched)
    return ReviewSummary(
        approvals=approvals,
        changes_requested=changes,
        unmatched_reviews=unmatched,
        findings=findings,
    )


def build_admission_evidence(
    *,
    binding: HeadBinding,
    policy: HygienePolicy,
    checks: Sequence[CheckObservation],
    reviews: Sequence[ReviewObservation],
    paths: Sequence[PathObservation],
    path_pagination: PagedResult[PathObservation] | PaginationCursor | None = None,
    review_pagination: PagedResult[ReviewObservation] | PaginationCursor | None = None,
    check_pagination: PagedResult[CheckObservation] | PaginationCursor | None = None,
    protected_base: ProtectedBaseEvidence | None = None,
    rate_limit: RateLimitSnapshot | None = None,
    draft: bool = False,
    merged: bool = False,
    closed: bool = False,
    mergeable: bool | None = None,
    unresolved_threads: int | None = None,
    labels: Sequence[str] = (),
    extra: Mapping[str, Any] | None = None,
) -> AdmissionEvidence:
    cursors: list[PaginationCursor] = []
    for item in (path_pagination, review_pagination, check_pagination):
        if item is None:
            continue
        if isinstance(item, PagedResult):
            cursors.append(item.cursor)
        else:
            cursors.append(item)
    if not cursors:
        # No pagination evidence provided — fail closed as unknown.
        from .types import PaginationStatus

        pagination = PaginationCursor(
            status=PaginationStatus.UNKNOWN,
            pages_fetched=0,
            per_page=policy.per_page,
            max_pages=policy.max_pages,
            items_seen=0,
            truncated=False,
            error="pagination_evidence_missing",
        )
    else:
        pagination = merge_cursors(cursors)

    inventory = classify_inventory(
        paths,
        privileged_prefixes=policy.privileged_path_prefixes,
        max_files=policy.max_changed_files,
    )
    check_summary = reduce_checks(checks, binding, policy)
    review_summary = reduce_reviews(reviews, binding, policy)
    return AdmissionEvidence(
        binding=binding,
        checks=check_summary,
        reviews=review_summary,
        inventory=inventory,
        protected_base=protected_base,
        pagination=pagination,
        rate_limit=rate_limit,
        draft=draft,
        merged=merged,
        closed=closed,
        mergeable=mergeable,
        unresolved_threads=unresolved_threads,
        labels=tuple(labels),
        extra=dict(extra or {}),
    )


def evidence_blockers(
    evidence: AdmissionEvidence,
    policy: HygienePolicy,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    findings.extend(evidence.checks.findings)
    findings.extend(evidence.reviews.findings)
    findings.extend(evidence.inventory.findings)

    pag_verdict, pag_findings = assess_pagination(
        evidence.pagination, fail_closed=policy.fail_closed_pagination
    )
    findings.extend(pag_findings)
    if pag_verdict is not HygieneVerdict.ALLOW:
        pass  # findings already include deny reasons

    base_assessment = assess_protected_base(evidence.binding, evidence.protected_base, policy)
    findings.extend(base_assessment.findings)

    if evidence.draft:
        findings.append(
            Finding(code="evidence.draft", severity="medium", message="pull request is draft")
        )
    if evidence.merged:
        findings.append(
            Finding(code="evidence.merged", severity="info", message="pull request already merged")
        )
    if evidence.closed and not evidence.merged:
        findings.append(
            Finding(code="evidence.closed", severity="medium", message="pull request is closed")
        )
    if evidence.mergeable is False:
        findings.append(
            Finding(code="evidence.not_mergeable", severity="high", message="mergeable is false")
        )
    if evidence.mergeable is None:
        findings.append(
            Finding(
                code="evidence.mergeable_unknown",
                severity="high",
                message="mergeable state unknown; fail closed",
            )
        )
    if evidence.unresolved_threads is None:
        findings.append(
            Finding(
                code="evidence.threads_unknown",
                severity="high",
                message="unresolved thread count unknown; fail closed",
            )
        )
    elif evidence.unresolved_threads > 0:
        findings.append(
            Finding(
                code="evidence.unresolved_threads",
                severity="high",
                message=f"{evidence.unresolved_threads} unresolved review threads",
            )
        )
    if evidence.checks.missing:
        findings.append(
            Finding(
                code="evidence.checks_missing",
                severity="high",
                message="missing required checks: " + ", ".join(evidence.checks.missing),
            )
        )
    if evidence.checks.failing:
        findings.append(
            Finding(
                code="evidence.checks_failing",
                severity="high",
                message="failing required checks: " + ", ".join(evidence.checks.failing),
            )
        )
    if evidence.checks.pending:
        findings.append(
            Finding(
                code="evidence.checks_pending",
                severity="medium",
                message="pending required checks: " + ", ".join(evidence.checks.pending),
            )
        )
    if evidence.checks.unknown:
        findings.append(
            Finding(
                code="evidence.checks_unknown",
                severity="critical",
                message="unknown required checks: " + ", ".join(evidence.checks.unknown),
            )
        )
    if evidence.reviews.changes_requested:
        findings.append(
            Finding(
                code="evidence.changes_requested",
                severity="high",
                message="changes requested by: " + ", ".join(evidence.reviews.changes_requested),
            )
        )
    if evidence.inventory.line_delta > policy.max_line_delta:
        findings.append(
            Finding(
                code="evidence.line_delta",
                severity="high",
                message=(
                    f"line delta {evidence.inventory.line_delta} exceeds "
                    f"max_line_delta={policy.max_line_delta}"
                ),
            )
        )
    if len(evidence.inventory.paths) > policy.max_changed_files:
        findings.append(
            Finding(
                code="evidence.changed_files",
                severity="high",
                message=(
                    f"changed files {len(evidence.inventory.paths)} exceed "
                    f"max_changed_files={policy.max_changed_files}"
                ),
            )
        )
    return tuple(findings)


__all__ = [
    "AdmissionEvidence",
    "CheckSummary",
    "ReviewSummary",
    "build_admission_evidence",
    "evidence_blockers",
    "reduce_checks",
    "reduce_reviews",
]

"""Composite admission evaluation for Pack E hygiene.

Combines identity binding, protected base, pagination, checks, reviews,
inventory, observe-mode, and budget signals into a single fail-closed decision.
Pack E never merges; ALLOW means "hygiene-clean candidate signal" only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .admission_evidence import AdmissionEvidence, evidence_blockers
from .budget import BudgetLedger, BudgetLimits, assess_budget, assess_rate_limit
from .identity_binding import assess_binding
from .observe_mode import ObservePolicy, assess_observe_gate
from .protected_base import assess_protected_base
from .types import (
    Finding,
    HeadBinding,
    HygieneMode,
    HygienePolicy,
    HygieneReport,
    HygieneVerdict,
    RateLimitSnapshot,
)


DENY_CODES = frozenset(
    {
        "identity.malformed",
        "identity.fork_head",
        "identity.base_denied",
        "protected_base.missing",
        "protected_base.unconfirmed",
        "protected_base.ref_mismatch",
        "protected_base.sha_mismatch",
        "pagination.pagination_incomplete",
        "pagination.pagination_truncated",
        "pagination.pagination_error",
        "evidence.checks_unknown",
        "evidence.mergeable_unknown",
        "evidence.threads_unknown",
        "budget.rate_limit_unknown",
        "binding.live_head_moved",
        "binding.live_base_moved",
    }
)

HOLD_CODES = frozenset(
    {
        "evidence.checks_pending",
        "evidence.draft",
        "budget.rate_limit_low",
        "budget.request_budget_exceeded",
        "budget.target_budget_exceeded",
        "budget.graphql_budget_exceeded",
        "budget.response_budget_exceeded",
    }
)


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    verdict: HygieneVerdict
    reasons: tuple[str, ...]
    findings: tuple[Finding, ...]
    evidence_fingerprint: str
    policy_fingerprint: str
    mode: HygieneMode
    binding_key: str

    def to_report(self) -> HygieneReport:
        return HygieneReport(
            verdict=self.verdict,
            reasons=self.reasons,
            findings=self.findings,
            binding_fingerprint=self.evidence_fingerprint,
            policy_fingerprint=self.policy_fingerprint,
            mode=self.mode,
            metadata={"binding_key": self.binding_key},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "findings": [f.to_dict() for f in self.findings],
            "evidence_fingerprint": self.evidence_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "mode": self.mode.value,
            "binding_key": self.binding_key,
        }


def _severity_rank(severity: str) -> int:
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    return order.get(severity, 4)


def _verdict_from_findings(
    findings: Sequence[Finding],
    *,
    observe: ObservePolicy | None,
) -> tuple[HygieneVerdict, tuple[str, ...]]:
    if observe is not None and observe.effective_mode is HygieneMode.OBSERVE:
        return HygieneVerdict.OBSERVE, observe.reasons

    reasons: list[str] = []
    deny = False
    hold = False
    incomplete = False
    for finding in findings:
        reasons.append(finding.code)
        if finding.code in DENY_CODES or finding.severity == "critical":
            deny = True
        elif finding.code in HOLD_CODES or finding.severity == "high":
            # high severity without explicit deny code holds unless it's a hard deny family
            if finding.code.startswith("evidence.checks_failing") or finding.code.startswith(
                "evidence.changes_requested"
            ):
                deny = True
            elif finding.code.startswith("evidence.not_mergeable") or finding.code.startswith(
                "evidence.unresolved_threads"
            ):
                deny = True
            elif finding.code.startswith("evidence.line_delta") or finding.code.startswith(
                "evidence.changed_files"
            ):
                deny = True
            elif finding.code.startswith("protected_base."):
                deny = True
            else:
                hold = True
        elif finding.code.endswith("unknown") or "incomplete" in finding.code:
            incomplete = True
            deny = True

    if deny:
        return HygieneVerdict.DENY, tuple(dict.fromkeys(reasons)) or ("denied",)
    if incomplete:
        return HygieneVerdict.INCOMPLETE, tuple(dict.fromkeys(reasons)) or ("incomplete",)
    if hold:
        return HygieneVerdict.HOLD, tuple(dict.fromkeys(reasons)) or ("hold",)
    return HygieneVerdict.ALLOW, ("admitted",)


def evaluate_admission(
    *,
    evidence: AdmissionEvidence,
    policy: HygienePolicy,
    observe: ObservePolicy | None = None,
    budget: BudgetLedger | None = None,
    budget_limits: BudgetLimits | None = None,
) -> AdmissionDecision:
    findings: list[Finding] = []

    binding_assessment = assess_binding(evidence.binding, policy)
    findings.extend(binding_assessment.findings)

    base_assessment = assess_protected_base(
        evidence.binding, evidence.protected_base, policy
    )
    findings.extend(base_assessment.findings)

    findings.extend(evidence_blockers(evidence, policy))

    if evidence.rate_limit is not None:
        limits = budget_limits or BudgetLimits(
            min_remaining_for_signal=policy.min_rate_limit_remaining
        )
        _, rl_findings = assess_rate_limit(evidence.rate_limit, limits)
        findings.extend(rl_findings)
    else:
        findings.append(
            Finding(
                code="budget.rate_limit_unknown",
                severity="critical",
                message="rate-limit snapshot missing; fail closed",
            )
        )

    if budget is not None:
        _, budget_findings = assess_budget(budget)
        findings.extend(budget_findings)

    if observe is not None:
        _, obs_findings = assess_observe_gate(observe)
        findings.extend(obs_findings)

    # Deduplicate by code+subject while preserving order
    deduped: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for finding in sorted(findings, key=lambda f: (-_severity_rank(f.severity), f.code)):
        key = (finding.code, finding.subject)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)

    verdict, reasons = _verdict_from_findings(deduped, observe=observe)
    mode = observe.effective_mode if observe is not None else policy.mode
    if mode is HygieneMode.OBSERVE and verdict is HygieneVerdict.ALLOW:
        verdict = HygieneVerdict.OBSERVE
        reasons = ("observe_mode",) + reasons

    return AdmissionDecision(
        verdict=verdict,
        reasons=reasons,
        findings=tuple(deduped),
        evidence_fingerprint=evidence.fingerprint(),
        policy_fingerprint=policy.fingerprint(),
        mode=mode,
        binding_key=evidence.binding.binding_key(),
    )


def evaluate_binding_only(
    binding: HeadBinding,
    policy: HygienePolicy,
) -> AdmissionDecision:
    assessment = assess_binding(binding, policy)
    return AdmissionDecision(
        verdict=assessment.verdict,
        reasons=assessment.reasons,
        findings=assessment.findings,
        evidence_fingerprint=binding.fingerprint(),
        policy_fingerprint=policy.fingerprint(),
        mode=policy.mode,
        binding_key=binding.binding_key(),
    )


__all__ = [
    "AdmissionDecision",
    "DENY_CODES",
    "HOLD_CODES",
    "evaluate_admission",
    "evaluate_binding_only",
]

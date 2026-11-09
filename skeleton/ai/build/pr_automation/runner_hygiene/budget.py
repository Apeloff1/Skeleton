"""Request, target, and mutation-signal budgets for hygiene sweeps.

Pack E does not perform merges. Budgets still gate how much work a sweep may
inspect and whether candidacy signaling is allowed under quota pressure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .types import Finding, HygieneVerdict, RateLimitSnapshot, fingerprint


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    max_targets: int = 50
    max_requests: int = 200
    max_graphql: int = 40
    max_response_bytes: int = 8_000_000
    min_remaining_for_signal: int = 50
    max_findings: int = 2_000

    def __post_init__(self) -> None:
        for name in (
            "max_targets",
            "max_requests",
            "max_graphql",
            "max_response_bytes",
            "min_remaining_for_signal",
            "max_findings",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive int")

    def fingerprint(self) -> str:
        return fingerprint(
            {
                "max_targets": self.max_targets,
                "max_requests": self.max_requests,
                "max_graphql": self.max_graphql,
                "max_response_bytes": self.max_response_bytes,
                "min_remaining_for_signal": self.min_remaining_for_signal,
                "max_findings": self.max_findings,
            }
        )


@dataclass
class BudgetLedger:
    limits: BudgetLimits
    targets_seen: int = 0
    requests_used: int = 0
    graphql_used: int = 0
    response_bytes: int = 0
    findings_emitted: int = 0
    holds: list[str] = field(default_factory=list)

    def consume_request(self, *, bytes_read: int = 0, graphql: bool = False) -> None:
        self.requests_used += 1
        if graphql:
            self.graphql_used += 1
        self.response_bytes += max(0, bytes_read)
        if self.requests_used > self.limits.max_requests:
            self.holds.append("request_budget_exceeded")
        if self.graphql_used > self.limits.max_graphql:
            self.holds.append("graphql_budget_exceeded")
        if self.response_bytes > self.limits.max_response_bytes:
            self.holds.append("response_budget_exceeded")

    def note_target(self) -> None:
        self.targets_seen += 1
        if self.targets_seen > self.limits.max_targets:
            self.holds.append("target_budget_exceeded")

    def note_findings(self, count: int) -> None:
        self.findings_emitted += max(0, count)
        if self.findings_emitted > self.limits.max_findings:
            self.holds.append("finding_budget_exceeded")

    @property
    def exhausted(self) -> bool:
        return bool(self.holds)

    def snapshot(self) -> dict[str, Any]:
        return {
            "targets_seen": self.targets_seen,
            "requests_used": self.requests_used,
            "graphql_used": self.graphql_used,
            "response_bytes": self.response_bytes,
            "findings_emitted": self.findings_emitted,
            "holds": list(dict.fromkeys(self.holds)),
            "limits": {
                "max_targets": self.limits.max_targets,
                "max_requests": self.limits.max_requests,
                "max_graphql": self.limits.max_graphql,
                "max_response_bytes": self.limits.max_response_bytes,
                "min_remaining_for_signal": self.limits.min_remaining_for_signal,
                "max_findings": self.limits.max_findings,
            },
        }


def assess_rate_limit(
    snapshot: RateLimitSnapshot,
    limits: BudgetLimits,
) -> tuple[HygieneVerdict, tuple[Finding, ...]]:
    if not snapshot.known:
        return HygieneVerdict.DENY, (
            Finding(
                code="budget.rate_limit_unknown",
                severity="critical",
                message="rate-limit evidence unknown; fail closed",
                subject=snapshot.resource,
            ),
        )
    assert snapshot.remaining is not None
    if snapshot.remaining < limits.min_remaining_for_signal:
        return HygieneVerdict.HOLD, (
            Finding(
                code="budget.rate_limit_low",
                severity="high",
                message=(
                    f"remaining={snapshot.remaining} below "
                    f"min_remaining_for_signal={limits.min_remaining_for_signal}"
                ),
                subject=snapshot.resource,
            ),
        )
    return HygieneVerdict.ALLOW, ()


def assess_budget(ledger: BudgetLedger) -> tuple[HygieneVerdict, tuple[Finding, ...]]:
    if not ledger.exhausted:
        return HygieneVerdict.ALLOW, ()
    findings = tuple(
        Finding(
            code=f"budget.{hold}",
            severity="high",
            message=hold.replace("_", " "),
        )
        for hold in dict.fromkeys(ledger.holds)
    )
    return HygieneVerdict.HOLD, findings


def budget_from_mapping(data: Mapping[str, Any] | None) -> BudgetLimits:
    if not data:
        return BudgetLimits()
    kwargs = {}
    for key in (
        "max_targets",
        "max_requests",
        "max_graphql",
        "max_response_bytes",
        "min_remaining_for_signal",
        "max_findings",
    ):
        if key in data and data[key] is not None:
            kwargs[key] = int(data[key])
    return BudgetLimits(**kwargs)


__all__ = [
    "BudgetLedger",
    "BudgetLimits",
    "assess_budget",
    "assess_rate_limit",
    "budget_from_mapping",
]

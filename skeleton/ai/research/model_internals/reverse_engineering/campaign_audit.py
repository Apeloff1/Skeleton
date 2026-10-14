"""End-to-end audit summary for a governed reverse-engineering campaign."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class AuditCheck:
    check_id: str
    category: str
    passed: bool
    critical: bool = False

    def __post_init__(self) -> None:
        if not self.check_id or not self.category:
            raise ReverseEngineeringError("audit check identity is required")


@dataclass(frozen=True)
class CampaignAuditReport:
    check_count: int
    passed_count: int
    failed_count: int
    critical_failure_count: int
    failed_categories: tuple[str, ...]
    readiness: str
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_count": self.check_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "critical_failure_count": self.critical_failure_count,
            "failed_categories": list(self.failed_categories),
            "readiness": self.readiness,
            "digest": self.digest,
        }


def audit_campaign(
    checks: Sequence[AuditCheck],
) -> CampaignAuditReport:
    if not checks:
        raise ReverseEngineeringError("campaign audit requires checks")
    ids = [check.check_id for check in checks]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("audit check ids must be unique")
    failed = [check for check in checks if not check.passed]
    critical = [check for check in failed if check.critical]
    if critical:
        readiness = "blocked"
    elif failed:
        readiness = "hold"
    else:
        readiness = "ready"
    payload = {
        "checks": [
            {
                "check_id": check.check_id,
                "category": check.category,
                "passed": check.passed,
                "critical": check.critical,
            }
            for check in sorted(checks, key=lambda value: value.check_id)
        ]
    }
    return CampaignAuditReport(
        check_count=len(checks),
        passed_count=len(checks) - len(failed),
        failed_count=len(failed),
        critical_failure_count=len(critical),
        failed_categories=tuple(sorted({check.category for check in failed})),
        readiness=readiness,
        digest=stable_digest(payload),
    )

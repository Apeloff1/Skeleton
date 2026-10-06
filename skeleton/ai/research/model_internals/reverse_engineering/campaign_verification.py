"""End-to-end campaign verification across research governance controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class CampaignVerificationControl:
    control_id: str
    category: str
    report_digest: str
    passed: bool
    critical: bool = True

    def __post_init__(self) -> None:
        if not self.control_id or not self.category:
            raise ReverseEngineeringError("campaign verification control identity is required")
        if not is_sha256_digest(self.report_digest):
            raise ReverseEngineeringError("report_digest must be sha256 hex")


@dataclass(frozen=True)
class CampaignVerificationReport:
    control_count: int
    passed_count: int
    failed_count: int
    critical_failure_count: int
    verified_categories: tuple[str, ...]
    failed_control_ids: tuple[str, ...]
    status: str
    digest: str

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def as_dict(self) -> dict[str, Any]:
        return {
            "control_count": self.control_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "critical_failure_count": self.critical_failure_count,
            "verified_categories": list(self.verified_categories),
            "failed_control_ids": list(self.failed_control_ids),
            "status": self.status,
            "digest": self.digest,
        }


def verify_campaign(
    controls: Sequence[CampaignVerificationControl],
    *,
    required_categories: Sequence[str] = (
        "authorization",
        "protocol",
        "coverage",
        "power",
        "replay",
        "reproducibility",
        "lineage",
        "falsification",
        "replication",
        "freshness",
        "closure",
    ),
) -> CampaignVerificationReport:
    if not controls:
        raise ReverseEngineeringError("campaign verification requires controls")
    ids = [control.control_id for control in controls]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("campaign control ids must be unique")
    required = tuple(dict.fromkeys(required_categories))
    if any(not category for category in required):
        raise ReverseEngineeringError("required categories must be non-empty")

    by_category: dict[str, list[CampaignVerificationControl]] = {}
    for control in controls:
        by_category.setdefault(control.category, []).append(control)
    missing_categories = set(required) - set(by_category)
    failed = [control for control in controls if not control.passed]
    critical_failed = [control for control in failed if control.critical]

    status = "verified"
    if missing_categories or critical_failed:
        status = "blocked"
    elif failed:
        status = "hold"

    payload = {
        "required_categories": list(required),
        "controls": [
            {
                "control_id": control.control_id,
                "category": control.category,
                "report_digest": control.report_digest,
                "passed": control.passed,
                "critical": control.critical,
            }
            for control in sorted(controls, key=lambda value: value.control_id)
        ],
    }
    return CampaignVerificationReport(
        control_count=len(controls),
        passed_count=len(controls) - len(failed),
        failed_count=len(failed),
        critical_failure_count=len(critical_failed) + len(missing_categories),
        verified_categories=tuple(sorted(category for category in by_category if category not in missing_categories)),
        failed_control_ids=tuple(sorted(control.control_id for control in failed)),
        status=status,
        digest=stable_digest(payload),
    )

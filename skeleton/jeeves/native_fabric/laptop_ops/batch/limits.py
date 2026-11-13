"""Finite 20 x 8 first-laptop inspection limits, never native work budgets."""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.policy import DEFAULT_LIMITS

DOMAIN_COUNT = 20
STAGES_PER_DOMAIN = 8
TOTAL_STAGES = DOMAIN_COUNT * STAGES_PER_DOMAIN


@dataclass(frozen=True, slots=True)
class BundleLimits:
    max_evidence_bytes: int = DEFAULT_LIMITS.max_evidence_bytes
    max_report_bytes: int = DEFAULT_LIMITS.max_report_bytes
    domain_count: int = DOMAIN_COUNT
    stage_count: int = TOTAL_STAGES

    def __post_init__(self) -> None:
        if (type(self.max_evidence_bytes) is not int
                or not 1024 <= self.max_evidence_bytes <= 65536
                or type(self.max_report_bytes) is not int
                or not 1024 <= self.max_report_bytes <= 131072
                or type(self.domain_count) is not int
                or self.domain_count != 20
                or type(self.stage_count) is not int
                or self.stage_count != 160):
            raise LaptopGateHold("noncanonical bundle size limits")

    def require_evidence_bytes(self, raw: object) -> bytes:
        if type(raw) is not bytes or not 1 <= len(raw) <= self.max_evidence_bytes:
            raise LaptopGateHold("bounded bundle evidence bytes required")
        return raw

    def require_report(self, raw: object) -> bytes:
        if type(raw) is not bytes or len(raw) > self.max_report_bytes:
            raise LaptopGateHold("bounded bundle report required")
        return raw


DEFAULT_BUNDLE_LIMITS = BundleLimits()

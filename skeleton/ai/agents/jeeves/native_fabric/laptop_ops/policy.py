"""Read-only source diagnostic limits; runtime limits remain canonical elsewhere."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import LaptopGateHold, integer


@dataclass(frozen=True, slots=True)
class DiagnosticLimits:
    max_stages: int = 8
    max_domains: int = 20
    max_evidence_bytes: int = 65536
    max_report_bytes: int = 131072

    def __post_init__(self) -> None:
        if (integer(self.max_stages, ceiling=8) != 8
            or integer(self.max_domains, ceiling=20) != 20
            or not 1024 <= integer(self.max_evidence_bytes, ceiling=65536)
            or not 1024 <= integer(self.max_report_bytes, ceiling=131072)):
            raise LaptopGateHold("diagnostic ceilings cannot be relaxed")

    def assert_report(self, data: bytes) -> None:
        if type(data) is not bytes or len(data) > self.max_report_bytes:
            raise LaptopGateHold("bounded diagnostic report required")


DEFAULT_LIMITS = DiagnosticLimits()

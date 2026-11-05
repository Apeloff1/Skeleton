"""Conservative grading policy, independent of generated answer or model claims."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import integer
from .errors import deny


@dataclass(frozen=True, slots=True)
class Threshold:
    minimum_total_percent: int = 95
    critical_must_pass: bool = True
    minimum_domain_percent: int = 90
    maximum_failed_calls: int = 0
    maximum_latency_ms: int = 300000

    def __post_init__(self) -> None:
        integer(self.minimum_total_percent, "total-percent", 0, 100)
        integer(self.minimum_domain_percent, "domain-percent", 0, 100)
        integer(self.maximum_failed_calls, "failed-calls", 0, 480)
        integer(self.maximum_latency_ms, "latency-limit", 1, 3600000)
        if type(self.critical_must_pass) is not bool:
            deny("critical-policy")

    def decide(
        self, *,
        total: int, passed: int, failed_calls: int,
        critical_failed: int, domains: dict[str, tuple[int, int]],
        evidence_complete: bool,
    ) -> bool:
        if type(evidence_complete) is not bool or not evidence_complete:
            return False
        integer(total, "total", 1, 1000000)
        integer(passed, "passed", 0, total)
        if failed_calls > self.maximum_failed_calls:
            return False
        if critical_failed and self.critical_must_pass:
            return False
        if 100 * passed < self.minimum_total_percent * total:
            return False
        for successes, domain_total in domains.values():
            if domain_total <= 0 or successes > domain_total:
                return False
            if 100 * successes < self.minimum_domain_percent * domain_total:
                return False
        return True

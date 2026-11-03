"""Finite numerical evaluation counters, bounded percentiles, no false CI claims."""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil
from .canonical import integer
from .errors import deny


def percentile_int(values: list[int], percentile: int) -> int | None:
    integer(percentile, "percentile", 0, 100)
    if type(values) is not list or len(values) > 100000:
        deny("metric-data")
    if not values:
        return None
    for value in values:
        integer(value, "metric-value", 0, 2**63 - 1)
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, ceil(percentile * len(ordered) / 100) - 1))
    return ordered[index]


@dataclass(frozen=True, slots=True)
class DomainMetrics:
    domain: str
    passed: int
    total: int
    failed_calls: int
    failed_critical: int
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    generated_tokens: int

    def record(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def aggregate(results: tuple) -> dict[str, DomainMetrics]:
    by_domain: dict[str, list] = {}
    for row in results:
        by_domain.setdefault(row.domain, []).append(row)
    output = {}
    for domain, rows in sorted(by_domain.items()):
        latencies = [step.latency_ms for row in rows for step in row.steps]
        output[domain] = DomainMetrics(
            domain=domain,
            passed=sum(row.passed for row in rows),
            total=len(rows),
            failed_calls=sum(row.error_code is not None for row in rows),
            failed_critical=sum(not row.passed and row.severity == "critical" for row in rows),
            p50_latency_ms=percentile_int(latencies, 50),
            p95_latency_ms=percentile_int(latencies, 95),
            generated_tokens=sum(step.generated_tokens for row in rows for step in row.steps),
        )
    return output

"""Finite measured end-to-end latency percentiles and throughput."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import integer
from .errors import deny
from .metrics import percentile_int


@dataclass(frozen=True, slots=True)
class LatencySummary:
    requests: int
    generated_tokens: int
    wall_ms: int
    p50_ms: int | None
    p90_ms: int | None
    p95_ms: int | None
    p99_ms: int | None
    tokens_per_sec: float

    def record(self) -> dict:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


def summarize(latencies: list[int], generated: list[int]) -> LatencySummary:
    if type(latencies) is not list or type(generated) is not list:
        deny("latency-input")
    if len(latencies) != len(generated) or len(latencies) > 100000:
        deny("latency-shape")
    for value in latencies:
        integer(value, "latency", 0, 2**31 - 1)
    for value in generated:
        integer(value, "generated", 0, 2**31 - 1)
    time_ms = sum(latencies)
    tokens = sum(generated)
    return LatencySummary(
        requests=len(latencies), generated_tokens=tokens,
        wall_ms=time_ms,
        p50_ms=percentile_int(latencies, 50),
        p90_ms=percentile_int(latencies, 90),
        p95_ms=percentile_int(latencies, 95),
        p99_ms=percentile_int(latencies, 99),
        tokens_per_sec=round(tokens * 1000 / time_ms, 5) if time_ms else 0.0,
    )

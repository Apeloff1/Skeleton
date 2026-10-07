"""Regression coverage for concurrent API-gateway reliability profiles."""
from __future__ import annotations

import pytest

from skeleton.testing.api_gateway_reliability_profiles import run_api_gateway_throughput_profile


def test_api_gateway_throughput_profile_preserves_concurrent_invariants() -> None:
    result = run_api_gateway_throughput_profile(requests=256, concurrency=8)
    assert result.requests == 256
    assert result.concurrency == 8
    assert result.completed == 256
    assert result.failed == 0
    assert result.body_mismatches == 0
    assert result.route_calls == 256
    assert result.route_errors == 0
    assert result.p50_ms >= 0.0
    assert result.p95_ms >= result.p50_ms
    assert result.max_ms >= result.p95_ms
    assert result.wall_ms > 0.0
    assert result.requests_per_second > 0.0
    assert result.python_version
    assert result.python_implementation
    assert result.platform_system
    assert result.invariants_passed is True


@pytest.mark.parametrize(
    ("requests", "concurrency", "message"),
    [(0, 1, "requests must be at least 1"), (1, 0, "concurrency must be at least 1")],
)
def test_api_gateway_throughput_profile_rejects_invalid_pressure(
    requests: int, concurrency: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_api_gateway_throughput_profile(requests=requests, concurrency=concurrency)

"""Regression coverage for process-level resource soak profiles."""
from __future__ import annotations

import pytest

from skeleton.testing.process_resource_reliability_profiles import (
    run_process_resource_soak_profile,
)


def test_process_resource_soak_keeps_runtime_resources_bounded() -> None:
    result = run_process_resource_soak_profile(
        iterations=2_048,
        warmup_requests=128,
    )

    assert result.completed == 2_048
    assert result.failed == 0
    assert result.route_calls == 2_176
    assert result.route_errors == 0
    assert result.rate_limit_buckets_before == 0
    assert result.rate_limit_buckets_after == 0
    assert result.leaked_threads == 0
    if result.file_descriptor_delta is not None:
        assert result.file_descriptor_delta <= 0
    assert result.gateway_source_growth_bytes <= 64 * 1024
    assert result.traced_peak_bytes >= 0
    assert result.elapsed_ms > 0.0
    assert result.requests_per_second > 0.0
    assert result.invariants_passed is True


@pytest.mark.parametrize(
    ("iterations", "warmup_requests", "message"),
    [
        (0, 1, "iterations must be at least 1"),
        (1, 0, "warmup_requests must be at least 1"),
    ],
)
def test_process_resource_soak_rejects_invalid_pressure(
    iterations: int,
    warmup_requests: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        run_process_resource_soak_profile(
            iterations=iterations,
            warmup_requests=warmup_requests,
        )


def test_process_resource_soak_rejects_boolean_counts() -> None:
    with pytest.raises(TypeError, match="iterations must be an integer"):
        run_process_resource_soak_profile(iterations=True)

"""Regression tests for deterministic orchestration reliability profiles."""

from __future__ import annotations

import asyncio

from skeleton.testing.reliability_profiles import run_orchestration_retry_profile


def test_concurrent_transient_failures_recover_within_retry_budget() -> None:
    result = asyncio.run(
        run_orchestration_retry_profile(
            runs=32,
            concurrency=8,
            transient_failures=2,
            max_attempts=3,
        )
    )

    assert result.completed == 32
    assert result.failed == 0
    assert result.total_tool_attempts == 96
    assert result.max_tool_attempts == 3
    assert result.p50_ms >= 0.0
    assert result.p95_ms >= result.p50_ms
    assert result.max_ms >= result.p95_ms


def test_concurrent_retry_exhaustion_fails_closed_and_stays_bounded() -> None:
    result = asyncio.run(
        run_orchestration_retry_profile(
            runs=24,
            concurrency=6,
            transient_failures=5,
            max_attempts=2,
        )
    )

    assert result.completed == 0
    assert result.failed == 24
    assert result.total_tool_attempts == 48
    assert result.max_tool_attempts == 2


def test_profile_rejects_invalid_pressure_configuration() -> None:
    async def scenario() -> None:
        try:
            await run_orchestration_retry_profile(runs=0)
        except ValueError as exc:
            assert "runs must be at least 1" in str(exc)
        else:
            raise AssertionError("zero-run reliability profile was accepted")

        try:
            await run_orchestration_retry_profile(concurrency=True)
        except TypeError as exc:
            assert "concurrency must be an integer" in str(exc)
        else:
            raise AssertionError("boolean concurrency was accepted")

    asyncio.run(scenario())

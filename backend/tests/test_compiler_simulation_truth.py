"""Truthful results and bounded-input regressions for simulated compiler routes."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes.compiler_tools import (
    BenchmarkRequest,
    VerificationRequest,
    formal_verification,
    simulate_benchmark,
)


@pytest.mark.parametrize("code", ["", "x" * 200_001])
def test_benchmark_model_rejects_unbounded_or_empty_source(code):
    with pytest.raises(ValidationError):
        BenchmarkRequest(code=code, language="python")


def test_benchmark_direct_construct_cannot_divide_by_zero():
    # Direct call skips model field checks, but runtime still refuses blank code.
    req = BenchmarkRequest.model_construct(code="", language="python", iterations=10, warmup_iterations=0)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(simulate_benchmark(req))
    assert exc.value.status_code == 422


def test_valid_benchmark_is_explicitly_simulated():
    req = BenchmarkRequest(code="for item in items: pass", language="python", iterations=10)
    result = asyncio.run(simulate_benchmark(req))
    assert result.simulated is True
    assert result.total_time_ms > 0
    assert result.throughput > 0


@pytest.mark.parametrize("proof_type", ["invariant", "bounds", "null_safety", "unknown"])
def test_formal_illustration_never_claims_unexecuted_proof(proof_type):
    req = VerificationRequest(code="assert 1 == 1", language="python", property_to_verify="P", proof_type=proof_type)
    result = asyncio.run(formal_verification(req))
    assert result["verified"] is False
    assert result["status"] == "verification_not_executed"
    assert result["simulation"] is True
    assert result["counterexample"] is None
    assert result["confidence"] == 0.0
    assert all(step["status"] == "not_executed" for step in result["steps"])

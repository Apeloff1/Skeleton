"""Jeeves advanced acceptance: real local generation, HTTP, durable restart.

The native tiny transformer here is an actual executing model, intentionally
NOT a production GGUF or a model-quality certification. Production deployment
must run the same HTTP/SQLite acceptance with operator-owned pinned GGUF.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer
from scripts.qualify_jeeves_live_local import (
    LiveJeevesFailure, _qualify_actual_local_http, qualify_jeeves_live_local,
)


def native_model():
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def test_real_offline_model_generates_across_loopback_http_then_recovers_sqlite():
    model = native_model()
    report = _qualify_actual_local_http(
        model, timeout_seconds=45, output_tokens=2,
    )
    assert report["qualified"] is True
    assert report["local_only"] is True
    assert report["hosted_provider_used"] is False
    assert report["model_id"] == model.model_id
    assert report["model_digest"] == model.model_digest
    assert report["actual_model_turns"] == 2
    assert report["durable_recovery_verified"] is True
    assert report["read_only_replay_verified"] is True
    assert report["context_continuation_verified"] is True
    assert report["protected_backend_verified"] is False
    assert report["mobile_device_verified"] is False
    assert report["underlying_model_quality_certified"] is False
    assert len(report["run_1_output_sha256"]) == 64
    assert len(report["run_2_output_sha256"]) == 64
    assert len(report["turn_metrics"]) == 2
    assert all(r["actual_output_tokens"] == 2 for r in report["turn_metrics"])


def test_production_live_qualification_refuses_a_different_native_model():
    with pytest.raises(LiveJeevesFailure, match="real loaded local model identity"):
        qualify_jeeves_live_local(native_model())


@pytest.mark.parametrize("timeout,tokens", [
    (0, 2), (601, 2), (True, 2), (45, 0), (45, 65), (45, True),
])
def test_resource_budgets_fail_before_live_generation(timeout, tokens):
    with pytest.raises(LiveJeevesFailure, match="time/token budgets"):
        _qualify_actual_local_http(
            native_model(), timeout_seconds=timeout, output_tokens=tokens,
        )

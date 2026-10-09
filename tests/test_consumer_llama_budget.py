"""Capacity planning for genuinely local, consumer-grade GGUF deployment."""
from __future__ import annotations

import pytest

from skeleton.ai.runtime.inference import (
    ConsumerHardwareBudget,
    LlamaCppConfig,
    LlamaCppRuntimeError,
    plan_consumer_llama_cpp,
)

GIB = 1024 ** 3
MIB = 1024 ** 2


def _config(**overrides):
    values = dict(
        executable="llama-cli", model_path="local.gguf",
        context_size=8192, threads=32, batch_size=1024,
    )
    values.update(overrides)
    return LlamaCppConfig(**values)


def test_consumer_plan_clamps_context_threads_and_batch_without_mutation():
    config = _config(gpu_layers=8)
    budget = ConsumerHardwareBudget(
        ram_bytes=8 * GIB, physical_cpu_cores=8,
        kv_bytes_per_token=1 * MIB, target_context_tokens=8192,
    )
    plan = plan_consumer_llama_cpp(config, budget, model_bytes=4 * GIB)
    assert plan.context_clamped is True
    assert 128 <= plan.configuration.context_size < config.context_size
    assert plan.configuration.context_size % 128 == 0
    assert plan.configuration.threads == 8
    assert plan.configuration.batch_size == 256
    assert plan.configuration.gpu_layers == 8
    assert config.context_size == 8192 and config.threads == 32
    assert plan.estimated_total_bytes <= budget.ram_bytes
    assert plan.reserved_kv_bytes == (
        plan.configuration.context_size * budget.kv_bytes_per_token
    )


def test_consumer_plan_preserves_short_request_and_missing_optional_values():
    config = _config(context_size=None, threads=None, batch_size=None, gpu_layers=None)
    budget = ConsumerHardwareBudget(
        ram_bytes=16 * GIB, physical_cpu_cores=6,
        kv_bytes_per_token=128 * 1024, target_context_tokens=2048,
    )
    plan = plan_consumer_llama_cpp(config, budget, model_bytes=3 * GIB)
    assert plan.context_clamped is False
    assert plan.configuration.context_size == 2048
    assert plan.configuration.threads == 6
    assert plan.configuration.batch_size == 256
    assert plan.configuration.gpu_layers is None


@pytest.mark.parametrize("model_bytes", [0, True, -2])
def test_consumer_plan_rejects_invalid_artifact_sizes(model_bytes):
    budget = ConsumerHardwareBudget(
        ram_bytes=8 * GIB, physical_cpu_cores=4,
        kv_bytes_per_token=128 * 1024,
    )
    with pytest.raises(ValueError, match="model_bytes"):
        plan_consumer_llama_cpp(_config(), budget, model_bytes=model_bytes)


def test_consumer_plan_fails_closed_when_weights_headroom_or_kv_cannot_fit():
    budget = ConsumerHardwareBudget(
        ram_bytes=4 * GIB, physical_cpu_cores=4,
        kv_bytes_per_token=1 * MIB,
    )
    with pytest.raises(LlamaCppRuntimeError, match="RAM budget"):
        plan_consumer_llama_cpp(_config(), budget, model_bytes=4 * GIB)
    with pytest.raises(LlamaCppRuntimeError, match="RAM budget"):
        plan_consumer_llama_cpp(_config(), budget, model_bytes=3 * GIB)


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_consumer_budget_validates_types_and_rejects_boolean_numbers(bad):
    with pytest.raises(ValueError):
        ConsumerHardwareBudget(
            ram_bytes=8 * GIB, physical_cpu_cores=4,
            kv_bytes_per_token=bad,
        )

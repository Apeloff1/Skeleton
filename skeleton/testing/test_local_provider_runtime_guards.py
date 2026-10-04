from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skeleton import provider_runtime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.local import (
    LocalInferenceCancelled,
    ReferenceNGramModel,
)
from skeleton.intelligence.admission import ResourceBudget
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger
from skeleton.provider_contract import ProviderArchitectureError
from skeleton.provider_runtime import (
    ProviderInvocationError,
    ProviderPolicyError,
    ProviderProtocolViolationError,
    ProviderRegistry,
    ProviderRequest,
    ProviderToolDefinition,
    ProviderUnavailableError,
)


def _registry(tmp_path, monkeypatch, *, runtime=None):
    path = tmp_path / "weights.json"
    write_local_model_artifact(
        ReferenceNGramModel.train(("alpha beta gamma",), model_id="guarded-local"), path
    )
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(path))
    monkeypatch.setenv("AI_LOCAL_MODEL_CACHE_SIZE", "0")
    monkeypatch.setenv("AI_LOCAL_MODEL_SEED", "1")
    for name in (
        "AI_SECONDARY_API_KEY",
        "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
        "AI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    return ProviderRegistry.from_env(admission_runtime=runtime)


def _durable_runtime(path):
    ledger = SqliteTenantQuotaLedger(path)
    runtime = AdmissionRuntime(
        quota_ledger=ledger,
        default_tenant_quota=TenantQuota(
            window_id="local-usage",
            max_operations=10,
            max_input_tokens=10000,
            max_output_tokens=10000,
            max_cost_usd=0.0,
            max_tool_calls=0,
            max_artifact_bytes=0,
            max_storage_bytes=0,
            max_concurrent_operations=2,
        ),
    )
    return runtime, ledger


@pytest.mark.asyncio
async def test_local_provider_completes_actual_usage_and_returns_governance_admission_receipts(
    tmp_path, monkeypatch
):
    runtime = AdmissionRuntime()
    registry = _registry(tmp_path, monkeypatch, runtime=runtime)
    response = await registry.require_active().generate(
        ProviderRequest(
            instructions="Use the local model",
            prompt="alpha",
            max_output_tokens=3,
            estimated_cost_usd=99.0,
            resource_budget=ResourceBudget(max_cost_usd=0.0),
        )
    )
    assert response.governance_decision_id.startswith("gov-")
    assert response.admission_decision_id
    assert response.usage.billed_cost == "0"
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens <= 3
    assert runtime.snapshot()["active_operations"] == ()
    assert runtime.telemetry_snapshot()["metrics"]["counters"]["admission.completed_total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    [
        "governance",
        "input_budget",
        "output_budget",
        "no_output_budget",
        "output_hard_bound",
        "model_override",
        "deadline",
        "tools",
        "structured_output",
        "weight_drift",
    ],
)
async def test_local_policy_denial_occurs_before_inference(tmp_path, monkeypatch, denial):
    registry = _registry(tmp_path, monkeypatch)
    adapter = registry.require_active()
    request = ProviderRequest(instructions="local only", prompt="alpha", max_output_tokens=3)
    if denial == "governance":
        request = ProviderRequest(instructions="local only", prompt="alpha", data_class="confidential")
    elif denial == "input_budget":
        request = ProviderRequest(
            instructions="", prompt="!" * 30, resource_budget=ResourceBudget(max_input_tokens=10)
        )
    elif denial == "output_budget":
        request = ProviderRequest(
            instructions="local only",
            prompt="alpha",
            max_output_tokens=3,
            resource_budget=ResourceBudget(max_output_tokens=2),
        )
    elif denial == "no_output_budget":
        request = ProviderRequest(
            instructions="local only", prompt="alpha", resource_budget=ResourceBudget(max_output_tokens=0)
        )
    elif denial == "output_hard_bound":
        request = ProviderRequest(instructions="local only", prompt="alpha", max_output_tokens=8193)
    elif denial == "model_override":
        request = ProviderRequest(instructions="local only", prompt="alpha", model="unactivated-model")
    elif denial == "deadline":
        request = ProviderRequest(
            instructions="local only", prompt="alpha", deadline=datetime.now(UTC) - timedelta(seconds=1)
        )
    elif denial == "tools":
        request = ProviderRequest(
            instructions="local only",
            prompt="alpha",
            tools=(
                ProviderToolDefinition(
                    tool_id="repo.read",
                    description="Read a repository file",
                    input_schema={"type": "object", "properties": {}},
                ),
            ),
        )
    elif denial == "structured_output":
        request = ProviderRequest(
            instructions="local only",
            prompt="alpha",
            structured_output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        )
    else:
        adapter.engine.model = ReferenceNGramModel.train(("different weights",), model_id=adapter.model)

    calls = 0

    def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("policy denial must precede inference")

    monkeypatch.setattr(adapter.engine.model, "infer", forbidden)
    with pytest.raises((ProviderPolicyError, ProviderInvocationError, ProviderUnavailableError)):
        await adapter.generate(request)
    assert calls == 0


@pytest.mark.asyncio
async def test_local_dispatch_requires_actual_canonical_architecture_receipt(tmp_path, monkeypatch):
    registry = _registry(tmp_path, monkeypatch)
    adapter = registry.active

    def denied(*args, **kwargs):
        raise ProviderArchitectureError("missing mandatory architecture document")

    def forbidden(*args, **kwargs):
        raise AssertionError("unacknowledged architecture cannot infer")

    monkeypatch.setattr(provider_runtime, "load_provider_architecture", denied)
    monkeypatch.setattr(adapter.engine.model, "infer", forbidden)
    with pytest.raises(ProviderUnavailableError, match="architecture acknowledgement"):
        await adapter.generate(ProviderRequest(instructions="local only", prompt="alpha"))
    assert adapter.available is False


@pytest.mark.asyncio
async def test_local_timeout_signals_model_cooperative_cancellation(tmp_path, monkeypatch):
    quota_path = tmp_path / "quota.sqlite3"
    runtime, ledger = _durable_runtime(quota_path)
    registry = _registry(tmp_path, monkeypatch, runtime=runtime)
    adapter = registry.require_active()
    observed_cancel = threading.Event()

    def blocking(request, cancel):
        assert cancel.wait(2)
        observed_cancel.set()
        raise LocalInferenceCancelled("local worker interrupted")

    monkeypatch.setattr(adapter.engine.model, "infer", blocking)
    with pytest.raises(ProviderInvocationError, match="deadline exceeded"):
        await adapter.generate(
            ProviderRequest(
                instructions="local only",
                prompt="alpha",
                tenant_id="local-tenant",
                operation_id="local-interrupted",
                resource_budget=ResourceBudget(max_wall_seconds=0.05),
            )
        )
    assert observed_cancel.wait(1)
    assert ledger.snapshot("local-tenant")["active_reservations"] == 1
    assert ledger.snapshot("local-tenant")["unknown_usage_events"] == 1
    assert runtime.snapshot()["unknown_usage_operations"] == ("local-interrupted",)
    assert runtime.telemetry_snapshot()["metrics"]["counters"].get("admission.completed_total", 0) == 0
    restarted = SqliteTenantQuotaLedger(quota_path)
    assert restarted.snapshot("local-tenant")["unknown_usage_events"] == 1


@pytest.mark.asyncio
async def test_local_actual_output_overrun_is_charged_and_denied_without_unknown_marker(
    tmp_path, monkeypatch
):
    runtime, ledger = _durable_runtime(tmp_path / "quota.sqlite3")
    adapter = _registry(tmp_path, monkeypatch, runtime=runtime).require_active()
    original_infer = adapter.engine.model.infer

    def excess_actual(request, cancel):
        return replace(original_infer(request, cancel), output_tokens=4)

    monkeypatch.setattr(adapter.engine.model, "infer", excess_actual)
    with pytest.raises(ProviderPolicyError, match="actual usage exceeded"):
        await adapter.generate(
            ProviderRequest(
                instructions="local only",
                prompt="alpha",
                tenant_id="local-tenant",
                operation_id="local-overrun",
                max_output_tokens=2,
                resource_budget=ResourceBudget(max_output_tokens=2),
            )
        )
    snapshot = ledger.snapshot("local-tenant")
    assert snapshot["completions"] == 1
    assert snapshot["active_reservations"] == 0
    assert snapshot["unknown_usage_events"] == 0
    assert snapshot["committed"]["output_tokens"] == 4
    assert (
        runtime.telemetry_snapshot()["metrics"]["counters"]["admission.operation_overrun.output_tokens_total"]
        == 1
    )


@pytest.mark.asyncio
async def test_local_undeclared_response_feature_is_rejected_after_dispatch(tmp_path, monkeypatch):
    runtime, ledger = _durable_runtime(tmp_path / "quota.sqlite3")
    adapter = _registry(tmp_path, monkeypatch, runtime=runtime).require_active()
    original_infer = adapter.engine.model.infer

    def undeclared_result(request, cancel):
        return replace(original_infer(request, cancel), structured_output={"unexpected": True})

    monkeypatch.setattr(adapter.engine.model, "infer", undeclared_result)
    with pytest.raises(ProviderProtocolViolationError, match="undeclared response feature"):
        await adapter.generate(
            ProviderRequest(
                instructions="local only",
                prompt="alpha",
                tenant_id="local-tenant",
                operation_id="local-undeclared",
                max_output_tokens=2,
            )
        )
    snapshot = ledger.snapshot("local-tenant")
    assert snapshot["completions"] == 0
    assert snapshot["active_reservations"] == 1
    assert snapshot["unknown_usage_events"] == 1


@pytest.mark.asyncio
async def test_local_neural_activation_admits_actual_utf8_input_targets(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

    registry = _registry(tmp_path, monkeypatch)
    write_local_model_artifact(
        NumpyRecurrentLM(model_id="byte-local", config=NeuralLMConfig(hidden_size=4, seed=5)),
        tmp_path / "weights.json",
    )
    registry = ProviderRegistry.from_env()
    adapter = registry.require_active()
    original_infer = adapter.engine.model.infer
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_infer(*args, **kwargs)

    monkeypatch.setattr(adapter.engine.model, "infer", counted)
    with pytest.raises(ProviderPolicyError, match="admission"):
        await adapter.generate(
            ProviderRequest(
                instructions="", prompt="café", resource_budget=ResourceBudget(max_input_tokens=5)
            )
        )
    assert calls == 0
    response = await adapter.generate(
        ProviderRequest(
            instructions="",
            prompt="café",
            max_output_tokens=2,
            resource_budget=ResourceBudget(max_input_tokens=6),
        )
    )
    assert calls == 1
    assert response.model == "byte-local"
    assert response.usage.input_tokens == 6
    assert response.usage.billed_cost == "0"


@pytest.mark.parametrize(
    "field,value",
    [
        ("AI_LOCAL_MODEL_CACHE_SIZE", "-1"),
        ("AI_LOCAL_MODEL_CACHE_SIZE", "4097"),
        ("AI_LOCAL_MODEL_SEED", "true"),
        ("AI_TIMEOUT_SECONDS", "nan"),
        ("AI_TIMEOUT_SECONDS", "0"),
    ],
)
def test_invalid_local_configuration_fails_closed(tmp_path, monkeypatch, field, value):
    _registry(tmp_path, monkeypatch)
    monkeypatch.setenv(field, value)
    with pytest.raises(ProviderUnavailableError, match="integer|bounds"):
        ProviderRegistry.from_env()


def test_local_activation_never_constructs_hosted_adapter_even_when_primary_credentials_exist(
    tmp_path, monkeypatch
):
    _registry(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-hosted-key")

    def forbidden(*args, **kwargs):
        raise AssertionError("local mode must never construct a hosted adapter")

    monkeypatch.setattr(provider_runtime.OpenAIProviderAdapter, "__init__", forbidden)
    registry = ProviderRegistry.from_env()
    assert registry.require_active().provider_id == "local"
    assert len(registry.statuses()) == 1

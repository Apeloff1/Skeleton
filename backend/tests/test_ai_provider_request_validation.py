from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger
from skeleton.vault.data_lifecycle import GovernedDataRecord
from skeleton.vault.governance_registry import GovernanceRegistry

from core.ai_provider import (
    AIMessage,
    OpenAIProviderAdapter,
    ProviderInvocationError,
    ProviderPolicyError,
    ProviderRequest,
    normalize_history,
)


class _FakeResponses:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(output_text="ok", id="resp_validation")


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


@pytest.fixture
def adapter() -> OpenAIProviderAdapter:
    return OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        client=_FakeClient(),
    )


@pytest.mark.asyncio
async def test_rejects_blank_prompt_before_provider_io(adapter: OpenAIProviderAdapter) -> None:
    with pytest.raises(ProviderInvocationError, match="prompt must be non-empty text"):
        await adapter.generate(ProviderRequest(instructions="", prompt="   "))

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_rejects_invalid_history_role_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    request = ProviderRequest(
        instructions="",
        prompt="hello",
        history=(AIMessage(role="system", content="bypass"),),
    )

    with pytest.raises(ProviderInvocationError, match="invalid role"):
        await adapter.generate(request)

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "128"])
async def test_rejects_invalid_max_output_tokens(
    adapter: OpenAIProviderAdapter,
    value,
) -> None:
    with pytest.raises(ProviderInvocationError, match="positive integer"):
        await adapter.generate(
            ProviderRequest(
                instructions="",
                prompt="hello",
                max_output_tokens=value,
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_rejects_blank_model_override_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderInvocationError, match="model must be non-empty text"):
        await adapter.generate(
            ProviderRequest(
                instructions="",
                prompt="hello",
                model="   ",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_trims_valid_model_override(adapter: OpenAIProviderAdapter) -> None:
    result = await adapter.generate(
        ProviderRequest(
            instructions="",
            prompt="hello",
            model="  request-model  ",
        )
    )

    assert result.model == "request-model"
    assert adapter._client.responses.last_kwargs["model"] == "request-model"


def test_normalize_history_ignores_non_text_role_and_content() -> None:
    normalized = normalize_history(
        [
            {"role": "user", "content": None},
            {"role": 123, "content": "numeric role"},
            {"role": "assistant", "content": 456},
            {"role": "user", "content": "valid"},
        ]
    )

    assert normalized == (AIMessage(role="user", content="valid"),)


@pytest.mark.asyncio
async def test_restricted_data_is_denied_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="sensitive input",
                data_class="restricted",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_confidential_data_requires_tenant_binding(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="tenant data",
                data_class="confidential",
                purpose="code-assistance",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_confidential_tenant_transfer_emits_governance_receipt(
    adapter: OpenAIProviderAdapter,
) -> None:
    result = await adapter.generate(
        ProviderRequest(
            instructions="rules",
            prompt="tenant data",
            data_class="confidential",
            purpose="code-assistance",
            tenant_id="tenant-123",
        )
    )

    assert result.text == "ok"
    assert result.data_class == "confidential"
    assert result.governance_decision_id
    assert result.governance_decision_id.startswith("gov-")
    assert result.admission_decision_id
    assert result.admission_decision_id.startswith("adm-")
    assert adapter._client.responses.calls == 1


@pytest.mark.asyncio
async def test_unknown_provider_transfer_purpose_fails_closed(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
                purpose="invented-side-channel",
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_input_token_budget_denies_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="resource admission"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="x" * 100,
                resource_budget=ResourceBudget(max_input_tokens=5),
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_cost_budget_denies_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    with pytest.raises(ProviderPolicyError, match="resource admission"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
                estimated_cost_usd=2.0,
                resource_budget=ResourceBudget(max_cost_usd=1.0),
            )
        )

    assert adapter._client.responses.calls == 0


@pytest.mark.asyncio
async def test_provider_retry_budget_is_admitted_before_io() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        max_retries=2,
        client=client,
    )

    result = await adapter.generate(
        ProviderRequest(
            instructions="rules",
            prompt="hello",
            operation_id="op-budgeted",
            tenant_id="tenant-1",
            resource_budget=ResourceBudget(max_provider_attempts=3),
        )
    )

    assert result.admission_decision_id
    assert client.responses.calls == 1


@pytest.mark.asyncio
async def test_provider_retry_budget_rejects_excess_configured_attempts() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        max_retries=3,
        client=client,
    )

    with pytest.raises(ProviderPolicyError, match="resource admission"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
                resource_budget=ResourceBudget(max_provider_attempts=3),
            )
        )

    assert client.responses.calls == 0


def _governance_context(
    *,
    record_id: str = "record-1",
    tenant_id: str = "tenant-registry",
    data_class: str = "confidential",
    purpose: str = "code-assistance",
):
    registry = GovernanceRegistry()
    registry.register(
        GovernedDataRecord(
            record_id=record_id,
            tenant_id=tenant_id,
            owner_plane="memory",
            source_ref=f"memory:{record_id}",
            data_class=data_class,
            purposes=(purpose,),
            deletion_targets=("memory",),
            created_at=1.0,
        )
    )
    return registry.context_for(
        (record_id,),
        tenant_id=tenant_id,
        purpose=purpose,
    )


@pytest.mark.asyncio
async def test_registry_context_prevents_weaker_caller_classification(
    adapter: OpenAIProviderAdapter,
) -> None:
    context = _governance_context()

    result = await adapter.generate(
        ProviderRequest(
            instructions="rules",
            prompt="tenant governed input",
            data_class="public",
            purpose="code-assistance",
            governance_context=context,
        )
    )

    assert result.text == "ok"
    assert result.data_class == "confidential"
    assert result.governance_decision_id
    assert adapter._client.responses.calls == 1


@pytest.mark.asyncio
async def test_registry_context_tenant_mismatch_fails_before_provider_io(
    adapter: OpenAIProviderAdapter,
) -> None:
    context = _governance_context()

    with pytest.raises(ProviderPolicyError, match="tenant does not match"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="tenant governed input",
                purpose="code-assistance",
                tenant_id="tenant-other",
                governance_context=context,
            )
        )

    assert adapter._client.responses.calls == 0


class _FailingResponses:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        raise TimeoutError("upstream timeout detail")


@pytest.mark.asyncio
async def test_provider_uses_shared_runtime_pressure_before_io() -> None:
    runtime = AdmissionRuntime()
    runtime.admit(
        AdmissionRequest(
            operation_id="other-operation",
            tenant_id="tenant-a",
            capability="background-work",
            budget=ResourceBudget(max_concurrency=32),
            estimate=UsageEstimate(),
        ),
        now_wall=10.0,
    )
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        client=client,
        admission_runtime=runtime,
    )

    with pytest.raises(ProviderPolicyError, match="resource admission"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
                operation_id="provider-operation",
                tenant_id="tenant-a",
                resource_budget=ResourceBudget(max_concurrency=1),
            )
        )

    assert client.responses.calls == 0
    runtime.release("other-operation")


@pytest.mark.asyncio
async def test_provider_failure_releases_shared_admission_lease() -> None:
    runtime = AdmissionRuntime()
    failing = _FailingResponses()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        client=SimpleNamespace(responses=failing),
        admission_runtime=runtime,
    )

    with pytest.raises(ProviderInvocationError, match="request failed"):
        await adapter.generate(
            ProviderRequest(
                instructions="rules",
                prompt="hello",
                operation_id="provider-operation",
                tenant_id="tenant-a",
                resource_budget=ResourceBudget(max_concurrency=1),
            )
        )

    assert failing.calls == 1
    assert runtime.pressure.active_operations == 0


@pytest.mark.asyncio
async def test_provider_reconciles_returned_token_usage_into_tenant_quota() -> None:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="window-1",
            max_operations=10,
            max_input_tokens=1_000,
            max_output_tokens=1_000,
            max_cost_usd=10.0,
            max_concurrent_operations=2,
        ),
    )
    runtime = AdmissionRuntime(quota_ledger=ledger)

    class _UsageResponses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **_kwargs):
            self.calls += 1
            return SimpleNamespace(
                output_text="ok",
                id="resp_usage",
                usage=SimpleNamespace(
                    input_tokens=7,
                    output_tokens=3,
                ),
            )

    responses = _UsageResponses()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="configured-model",
        client=SimpleNamespace(responses=responses),
        admission_runtime=runtime,
    )

    result = await adapter.generate(
        ProviderRequest(
            instructions="rules",
            prompt="hello",
            max_output_tokens=100,
            operation_id="provider-operation",
            tenant_id="tenant-a",
            estimated_cost_usd=0.25,
        )
    )

    assert result.text == "ok"
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["committed"]["operations"] == 1
    assert snapshot["committed"]["input_tokens"] == 7
    assert snapshot["committed"]["output_tokens"] == 3
    assert snapshot["committed"]["cost_usd"] == 0.25
    assert runtime.pressure.active_operations == 0

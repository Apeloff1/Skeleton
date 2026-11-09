from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from skeleton.intelligence.admission import (
    AdmissionRequest,
    AdmissionStatus,
    ResourceBudget,
    RuntimePressure,
    UsageEstimate,
    evaluate_admission,
)
from skeleton.intelligence.quota import (
    QuotaExceeded,
    TenantQuota,
    TenantQuotaLedger,
)
from skeleton.provider_runtime import (
    OpenAIProviderAdapter,
    ProviderPolicyError,
    ProviderRequest,
)


def test_ac15_budget_fault_rejects_cost_overshoot() -> None:
    decision = evaluate_admission(
        AdmissionRequest(
            operation_id="ac15-budget-fault",
            tenant_id="tenant-a",
            capability="model-inference",
            budget=ResourceBudget(max_cost_usd=1.0),
            estimate=UsageEstimate(cost_usd=1.01),
            pressure=RuntimePressure(),
        ),
        now_monotonic=10.0,
    )

    assert decision.status is AdmissionStatus.REJECT
    assert decision.admitted is False
    assert decision.reason_code == "cost_budget_exceeded"


def test_ac15_fanout_stress_cannot_multiply_past_tenant_cost_ceiling() -> None:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="ac15-fanout-window",
            max_operations=16,
            max_input_tokens=1_000_000,
            max_output_tokens=1_000_000,
            max_cost_usd=1.0,
            max_tool_calls=1_000,
            max_artifact_bytes=1_000_000_000,
            max_storage_bytes=1_000_000_000,
            max_concurrent_operations=16,
        ),
    )

    reservations = [
        ledger.reserve(
            "tenant-a",
            f"fanout-child-{index}",
            UsageEstimate(cost_usd=0.25),
            now=10.0 + index,
        )
        for index in range(4)
    ]

    assert len({item.reservation_id for item in reservations}) == 4
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["reserved"]["cost_usd"] == pytest.approx(1.0)

    with pytest.raises(QuotaExceeded, match="tenant_quota_exceeded:cost_usd"):
        ledger.reserve(
            "tenant-a",
            "fanout-child-5",
            UsageEstimate(cost_usd=0.25),
            now=20.0,
        )

    after = ledger.snapshot("tenant-a")
    assert after["active_reservations"] == 4
    assert after["reserved"]["cost_usd"] == pytest.approx(1.0)


def test_ac15_quota_isolation_prevents_noisy_tenant_from_consuming_peer_budget() -> None:
    ledger = TenantQuotaLedger()
    for tenant in ("tenant-a", "tenant-b"):
        ledger.configure(
            tenant,
            TenantQuota(
                window_id=f"ac15-{tenant}",
                max_operations=8,
                max_input_tokens=100_000,
                max_output_tokens=100_000,
                max_cost_usd=0.5,
                max_tool_calls=100,
                max_artifact_bytes=100_000_000,
                max_storage_bytes=100_000_000,
                max_concurrent_operations=8,
            ),
        )

    ledger.reserve(
        "tenant-a",
        "tenant-a-full",
        UsageEstimate(cost_usd=0.5),
        now=10.0,
    )
    with pytest.raises(QuotaExceeded, match="tenant_quota_exceeded:cost_usd"):
        ledger.reserve(
            "tenant-a",
            "tenant-a-over",
            UsageEstimate(cost_usd=0.01),
            now=11.0,
        )

    peer = ledger.reserve(
        "tenant-b",
        "tenant-b-independent",
        UsageEstimate(cost_usd=0.5),
        now=12.0,
    )

    assert peer.tenant_id == "tenant-b"
    assert ledger.snapshot("tenant-a")["reserved"]["cost_usd"] == pytest.approx(0.5)
    assert ledger.snapshot("tenant-b")["reserved"]["cost_usd"] == pytest.approx(0.5)


def test_ac15_provider_reprice_simulation_fails_before_provider_io() -> None:
    class Responses:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            raise AssertionError("provider I/O must not occur after repricing denial")

    responses = Responses()
    client = SimpleNamespace(responses=responses)
    adapter = OpenAIProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        max_retries=0,
        client=client,
    )

    original = ProviderRequest(
        instructions="answer within budget",
        prompt="bounded request",
        operation_id="ac15-before-reprice",
        estimated_cost_usd=0.75,
        resource_budget=ResourceBudget(max_cost_usd=1.0),
        max_output_tokens=64,
    )
    repriced = ProviderRequest(
        instructions=original.instructions,
        prompt=original.prompt,
        operation_id="ac15-after-reprice",
        estimated_cost_usd=1.25,
        resource_budget=original.resource_budget,
        max_output_tokens=original.max_output_tokens,
    )

    assert original.estimated_cost_usd < original.resource_budget.max_cost_usd
    assert repriced.estimated_cost_usd > repriced.resource_budget.max_cost_usd

    with pytest.raises(
        ProviderPolicyError,
        match="request denied by resource admission",
    ):
        asyncio.run(adapter.generate(repriced))

    assert responses.calls == []
    assert adapter.admission_runtime.snapshot()["active_operations"] == ()

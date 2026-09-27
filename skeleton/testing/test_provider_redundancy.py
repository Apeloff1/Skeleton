from __future__ import annotations

import pytest

from skeleton.provider_contract import ProviderArchitectureReceipt
from skeleton.provider_redundancy import (
    ProviderAvailabilityController,
    ProviderAvailabilityPolicy,
    ProviderAvailabilityStrategy,
)
from skeleton.provider_runtime import (
    ProviderAdapter,
    ProviderRegistry,
    ProviderUnavailableError,
)


class _FakeProvider(ProviderAdapter):
    def __init__(
        self,
        provider_id: str,
        *,
        available: bool,
        model: str = "test-model",
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    async def generate(self, request):
        del request
        raise AssertionError("routing contract test must not perform provider I/O")


def _architecture(provider_id: str) -> ProviderArchitectureReceipt:
    return ProviderArchitectureReceipt(
        provider_id=provider_id,
        architecture_tag="test-architecture",
        construction_version="test-v1",
        contract_digest="a" * 64,
        manual_path="docs/AI_APP_CONSTRUCTION_MANUAL.md",
        required_documents=("docs/AI_APP_CONSTRUCTION_MANUAL.md",),
    )


def _registry(*providers: _FakeProvider, active: str) -> ProviderRegistry:
    return ProviderRegistry(
        providers,
        active=active,
        architecture_loader=_architecture,
    )


def test_single_provider_slo_routes_declared_primary_and_emits_telemetry() -> None:
    primary = _FakeProvider("openai", available=True)
    controller = ProviderAvailabilityController(
        _registry(primary, active="openai"),
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.SINGLE_PROVIDER_SLO,
            primary_provider="openai",
            availability_target=0.995,
        ),
    )

    adapter, receipt = controller.require_adapter()

    assert adapter is primary
    assert receipt.selected_provider == "openai"
    assert receipt.failover_used is False
    assert receipt.strategy == "single-provider-slo"
    assert receipt.availability_target == 0.995
    assert receipt.provider_states == (
        {
            "provider_id": "openai",
            "available": True,
            "architecture_acknowledged": True,
            "configured": True,
            "active": True,
            "model": "test-model",
        },
    )
    assert len(receipt.digest) == 64
    assert controller.telemetry() == {
        "strategy": "single-provider-slo",
        "availability_target": 0.995,
        "route_count": 1,
        "failover_count": 0,
        "unavailable_count": 0,
        "selected_counts": {"openai": 1},
        "declared_provider_count": 1,
    }


def test_single_provider_outage_fails_closed_without_undeclared_fallback() -> None:
    primary = _FakeProvider("openai", available=False)
    controller = ProviderAvailabilityController(
        _registry(primary, active="openai"),
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.SINGLE_PROVIDER_SLO,
            primary_provider="openai",
            availability_target=0.99,
        ),
    )

    receipt = controller.plan()
    assert receipt.selected_provider is None
    assert receipt.failover_used is False
    assert "single-provider SLO accepted" in receipt.reason

    with pytest.raises(
        ProviderUnavailableError,
        match="single-provider SLO accepted",
    ):
        controller.require_adapter()

    telemetry = controller.telemetry()
    assert telemetry["route_count"] == 2
    assert telemetry["unavailable_count"] == 2
    assert telemetry["failover_count"] == 0


def test_multi_provider_policy_executes_declared_failover() -> None:
    primary = _FakeProvider("primary", available=False)
    fallback = _FakeProvider("fallback", available=True)
    controller = ProviderAvailabilityController(
        _registry(primary, fallback, active="primary"),
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.MULTI_PROVIDER_FAILOVER,
            primary_provider="primary",
            fallback_providers=("fallback",),
            availability_target=0.999,
        ),
    )

    adapter, receipt = controller.require_adapter()

    assert adapter is fallback
    assert receipt.selected_provider == "fallback"
    assert receipt.failover_used is True
    assert receipt.declared_providers == ("primary", "fallback")
    assert receipt.reason == "primary unavailable; selected declared fallback"
    assert controller.telemetry()["failover_count"] == 1
    assert controller.telemetry()["selected_counts"] == {"fallback": 1}


def test_undeclared_or_unconfigured_provider_is_never_selected() -> None:
    primary = _FakeProvider("primary", available=False)
    controller = ProviderAvailabilityController(
        _registry(primary, active="primary"),
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.MULTI_PROVIDER_FAILOVER,
            primary_provider="primary",
            fallback_providers=("missing-fallback",),
        ),
    )

    receipt = controller.plan()

    assert receipt.selected_provider is None
    assert receipt.provider_states[1] == {
        "provider_id": "missing-fallback",
        "available": False,
        "architecture_acknowledged": False,
        "configured": False,
    }


def test_availability_policy_preserves_provider_runtime_ownership() -> None:
    with pytest.raises(
        ValueError,
        match="credentials must remain owned",
    ):
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.SINGLE_PROVIDER_SLO,
            primary_provider="openai",
            credential_owner="backend/routes/chat.py",
        )

    with pytest.raises(
        ValueError,
        match="network policy",
    ):
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.SINGLE_PROVIDER_SLO,
            primary_provider="openai",
            network_policy="route-owned-network",
        )

    with pytest.raises(
        ValueError,
        match="single-provider SLO policy cannot declare fallback providers",
    ):
        ProviderAvailabilityPolicy(
            strategy=ProviderAvailabilityStrategy.SINGLE_PROVIDER_SLO,
            primary_provider="openai",
            fallback_providers=("fallback",),
        )

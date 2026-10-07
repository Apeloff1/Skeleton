from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.frontier.runtime.model_routing import (
    ModelRouteRequest,
    ModelRouter,
    ProviderMetadata,
    ProviderMetadataError,
    RouteBudget,
)
from skeleton.frontier.runtime.model_runtime import (
    ChatResponse,
    ModelCapability,
    ModelMessage,
    RetryPolicy,
    TokenUsage,
)
from skeleton.intelligence.router_registry import RouterRegistry
from skeleton.intelligence.routing_execution import (
    GovernedModelRouter,
    RouteExecutionPermit,
    issue_route_execution_permit,
    route_request_digest,
)
from skeleton.intelligence.routing_governance import (
    RouteObservation,
    RouteQualificationRequest,
    qualify_registry_routes,
)


class FakeAdapter:
    def __init__(self, name: str, text: str = "ok") -> None:
        self.name = name
        self.text = text
        self.capabilities = frozenset({ModelCapability.CHAT})
        self.calls = 0

    async def chat(self, request):
        self.calls += 1
        return ChatResponse(
            model=request.model,
            text=self.text,
            usage=TokenUsage(input_tokens=2, output_tokens=2),
        )

    async def embed(self, request):
        raise AssertionError("not used")

    async def stream_chat(self, request):
        if False:
            yield None


def metadata(provider_id: str, adapter_name: str, priority: int) -> ProviderMetadata:
    return ProviderMetadata.from_mapping(
        {
            "provider_id": provider_id,
            "adapter_name": adapter_name,
            "model": f"{provider_id}-model",
            "capabilities": ["chat"],
            "max_input_tokens": 4096,
            "max_output_tokens": 256,
            "input_cost_per_million": 1.0,
            "output_cost_per_million": 1.0,
            "timeout_seconds": 1.0,
            "priority": priority,
            "enabled": True,
            "max_attempts": 1,
            "backoff_seconds": 0.0,
        }
    )


def observation(provider_id: str) -> RouteObservation:
    return RouteObservation(
        provider_id=provider_id,
        model=f"{provider_id}-model",
        health_score=1.0,
        risk_score=0.0,
        observed_at=100.0,
        expires_at=200.0,
        evidence=(
            EvidenceRef(
                source=f"health://{provider_id}",
                digest="a" * 64,
                category="health",
            ),
        ),
        verifier_id="independent-health",
        verifier_digest="b" * 64,
    )


def route_request() -> ModelRouteRequest:
    return ModelRouteRequest(
        request_id="req-1",
        messages=(ModelMessage("user", "hello"),),
        required_capabilities=frozenset({"chat"}),
        max_output_tokens=32,
        timeout_seconds=1.0,
        retry_policy=RetryPolicy(max_attempts=1),
        budget=RouteBudget(max_cost=0.01, max_provider_attempts=2),
        estimated_input_tokens=10,
        metadata={"data_class": "internal"},
    )


def qualification_request() -> RouteQualificationRequest:
    return RouteQualificationRequest(
        required_capabilities=("chat",),
        input_tokens=10,
        output_tokens=32,
        min_health_score=0.9,
        max_risk_score=0.1,
        max_estimated_cost=0.01,
    )


def fixture():
    p1 = metadata("p1", "a1", 0)
    p2 = metadata("p2", "a2", 1)
    registry = RouterRegistry((p1, p2))
    a1, a2 = FakeAdapter("a1", "one"), FakeAdapter("a2", "two")
    router = registry.bind({"a1": a1, "a2": a2})
    q = qualification_request()
    decision = qualify_registry_routes(
        registry,
        q,
        {"p1": observation("p1"), "p2": observation("p2")},
        observed_at=110.0,
        expected_registry_digest=registry.snapshot().digest,
    )
    request = route_request()
    permit = issue_route_execution_permit(registry, q, decision, request)
    return registry, router, a1, a2, request, permit


def test_governed_execution_calls_only_qualified_provider():
    registry, router, a1, a2, request, permit = fixture()
    result = asyncio.run(GovernedModelRouter(registry, router).invoke(request, permit))
    assert result.ok
    assert result.selected_provider_id == "p1"
    assert a1.calls == 1
    assert a2.calls == 0
    assert len(permit.digest) == 64


def test_permit_rejects_exact_request_replay_on_modified_prompt():
    registry, router, a1, a2, request, permit = fixture()
    changed = replace(
        request,
        messages=(ModelMessage("user", "different"),),
    )
    with pytest.raises(ProviderMetadataError, match="exact request"):
        asyncio.run(GovernedModelRouter(registry, router).invoke(changed, permit))
    assert a1.calls == 0 and a2.calls == 0


def test_permit_rejects_unqualified_capability_or_token_shape():
    registry, router, _, _, request, _ = fixture()
    q = qualification_request()
    decision = qualify_registry_routes(
        registry,
        q,
        {"p1": observation("p1"), "p2": observation("p2")},
        observed_at=110.0,
    )
    with pytest.raises(ProviderMetadataError, match="capabilities"):
        issue_route_execution_permit(
            registry,
            q,
            decision,
            replace(request, required_capabilities=frozenset({"chat", "tools"})),
        )
    with pytest.raises(ProviderMetadataError, match="input token"):
        issue_route_execution_permit(
            registry,
            q,
            decision,
            replace(request, estimated_input_tokens=11),
        )


def test_stale_registry_fails_before_provider_execution():
    registry, router, a1, a2, request, permit = fixture()
    stale_registry = RouterRegistry(
        (
            metadata("p1", "a1", 0),
            metadata("p2", "a2", 1),
            metadata("p3", "a3", 2),
        )
    )
    with pytest.raises(ProviderMetadataError, match="catalog"):
        GovernedModelRouter(stale_registry, router)
    assert a1.calls == 0 and a2.calls == 0

    forged = RouteExecutionPermit(
        registry_digest="0" * 64,
        qualification_digest=permit.qualification_digest,
        qualification_request_digest=permit.qualification_request_digest,
        execution_request_digest=permit.execution_request_digest,
        selected_provider_id=permit.selected_provider_id,
        observed_at=permit.observed_at,
    )
    with pytest.raises(ProviderMetadataError, match="registry is stale"):
        asyncio.run(GovernedModelRouter(registry, router).invoke(request, forged))
    assert a1.calls == 0 and a2.calls == 0


def test_execution_permit_cannot_escalate_provider_authority():
    _, _, _, _, _, permit = fixture()
    with pytest.raises(ProviderMetadataError, match="cannot grant"):
        RouteExecutionPermit(
            registry_digest=permit.registry_digest,
            qualification_digest=permit.qualification_digest,
            qualification_request_digest=permit.qualification_request_digest,
            execution_request_digest=permit.execution_request_digest,
            selected_provider_id=permit.selected_provider_id,
            observed_at=permit.observed_at,
            authority_scope="provider-credential-authority",
        )


def test_route_request_digest_binds_budget_metadata_and_tools():
    request = route_request()
    assert route_request_digest(request) != route_request_digest(
        replace(request, metadata={"data_class": "restricted"})
    )
    assert route_request_digest(request) != route_request_digest(
        replace(request, budget=RouteBudget(max_cost=0.005, max_provider_attempts=2))
    )


def test_governed_routing_execution_mirror_parity():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (
        root / "skeleton/intelligence/routing_execution.py"
    ).read_bytes() == (
        root / "skeleton/ai/runtime/intelligence/routing_execution.py"
    ).read_bytes()

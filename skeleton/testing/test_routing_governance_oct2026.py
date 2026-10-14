from __future__ import annotations

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.frontier.runtime.model_routing import ProviderMetadataError
from skeleton.intelligence.router_registry import RouterRegistry
from skeleton.intelligence.routing_governance import (
    ROUTING_AUTHORITY_SCOPE,
    RouteObservation,
    RouteQualificationRequest,
    qualify_registry_routes,
)


def _provider(provider_id: str, adapter: str, priority: int) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "adapter_name": adapter,
        "model": "model-1",
        "capabilities": ["chat", "tools"],
        "max_input_tokens": 8192,
        "max_output_tokens": 1024,
        "input_cost_per_million": 1.0,
        "output_cost_per_million": 1.0,
        "timeout_seconds": 3.0,
        "priority": priority,
    }


def _observation(
    provider_id: str,
    *,
    health: float = 0.95,
    risk: float = 0.05,
    expires_at: float = 140.0,
) -> RouteObservation:
    return RouteObservation(
        provider_id=provider_id,
        model="model-1",
        health_score=health,
        risk_score=risk,
        observed_at=100.0,
        expires_at=expires_at,
        evidence=(
            EvidenceRef(
                source=f"health://{provider_id}",
                digest=("a" if provider_id == "p1" else "b") * 64,
                category="route-health",
            ),
        ),
        verifier_id="verifier:route-health",
        verifier_digest="c" * 64,
    )


def _request() -> RouteQualificationRequest:
    return RouteQualificationRequest(
        required_capabilities=("chat",),
        input_tokens=1000,
        output_tokens=200,
        min_health_score=0.90,
        max_risk_score=0.10,
        max_estimated_cost=0.01,
    )


def test_qualification_is_deterministic_and_non_executing() -> None:
    left = RouterRegistry(
        [_provider("p2", "a2", 2), _provider("p1", "a1", 1)]
    )
    right = RouterRegistry(
        [_provider("p1", "a1", 1), _provider("p2", "a2", 2)]
    )
    observations = {"p1": _observation("p1"), "p2": _observation("p2")}
    first = qualify_registry_routes(left, _request(), observations, observed_at=110.0)
    second = qualify_registry_routes(right, _request(), observations, observed_at=110.0)

    assert first.digest == second.digest
    assert first.selected_provider_id == "p1"
    assert first.eligible_provider_ids == ("p1", "p2")
    assert first.authority_scope == ROUTING_AUTHORITY_SCOPE


def test_missing_stale_or_risky_evidence_fails_closed() -> None:
    registry = RouterRegistry(
        [_provider("p1", "a1", 1), _provider("p2", "a2", 2)]
    )
    decision = qualify_registry_routes(
        registry,
        _request(),
        {
            "p1": _observation("p1", expires_at=105.0),
            "p2": _observation("p2", risk=0.50),
        },
        observed_at=110.0,
    )
    rejected = dict(decision.rejected)
    assert decision.selected_provider_id is None
    assert "observation-expired" in rejected["p1"]
    assert "risk-threshold" in rejected["p2"]

    missing = qualify_registry_routes(registry, _request(), {}, observed_at=110.0)
    assert "missing-route-observation" in dict(missing.rejected)["p1"]


def test_exact_registry_digest_fences_qualification() -> None:
    registry = RouterRegistry([_provider("p1", "a1", 1)])
    with pytest.raises(ProviderMetadataError, match="stale router registry digest"):
        qualify_registry_routes(
            registry,
            _request(),
            {"p1": _observation("p1")},
            observed_at=110.0,
            expected_registry_digest="0" * 64,
        )


def test_observation_cannot_self_assert_authority_or_verification() -> None:
    with pytest.raises(ProviderMetadataError, match="independently verified"):
        RouteObservation(
            provider_id="p1",
            model="model-1",
            health_score=1.0,
            risk_score=0.0,
            observed_at=100.0,
            expires_at=120.0,
            evidence=(
                EvidenceRef(source="health://p1", digest="a" * 64, category="health"),
            ),
            verifier_id="producer",
            verifier_digest="b" * 64,
            independent=False,
        )

    with pytest.raises(ProviderMetadataError, match="cannot grant execution authority"):
        RouteObservation(
            provider_id="p1",
            model="model-1",
            health_score=1.0,
            risk_score=0.0,
            observed_at=100.0,
            expires_at=120.0,
            evidence=(
                EvidenceRef(source="health://p1", digest="a" * 64, category="health"),
            ),
            verifier_id="verifier",
            verifier_digest="b" * 64,
            authority_scope="execute-model",
        )

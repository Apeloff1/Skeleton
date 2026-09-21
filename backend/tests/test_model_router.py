import math

import pytest

from skeleton.intelligence.admission import ResourceBudget
from skeleton.vault.data_lifecycle import GovernedDataRecord
from skeleton.vault.governance_registry import GovernanceRegistry

from core.model_router import (
    ModelEndpoint,
    ModelRouter,
    NoRoute,
    PrivacyLevel,
    RouteRequest,
)


def _endpoint(
    endpoint_id: str,
    *,
    provider: str = "provider",
    model: str | None = None,
    capabilities=("text", "code"),
    modalities=("text",),
    context=128_000,
    latency=100.0,
    input_cost=1.0,
    output_cost=2.0,
    privacy=PrivacyLevel.PUBLIC,
    local=False,
    enabled=True,
):
    return ModelEndpoint(
        endpoint_id=endpoint_id,
        provider=provider,
        model=model or endpoint_id,
        capabilities=frozenset(capabilities),
        modalities=frozenset(modalities),
        max_context_tokens=context,
        nominal_latency_ms=latency,
        input_cost_per_million=input_cost,
        output_cost_per_million=output_cost,
        privacy_ceiling=privacy,
        local=local,
        enabled=enabled,
    )


def test_hard_constraints_filter_before_scoring():
    router = ModelRouter()
    router.register(_endpoint("code", capabilities=("code", "tools")))
    router.register(_endpoint("vision", capabilities=("vision",), modalities=("text", "image")))
    router.register(_endpoint("tiny", capabilities=("code", "tools"), context=1000))

    decision = router.route(
        RouteRequest(
            "edit_code",
            required_capabilities=frozenset({"code", "tools"}),
            context_tokens=2000,
            expected_output_tokens=100,
        )
    )
    assert decision.selected.endpoint_id == "code"
    assert "vision" in decision.rejected
    assert any("missing capabilities" in reason for reason in decision.rejected["vision"])
    assert any("context" in reason for reason in decision.rejected["tiny"])


def test_sensitive_and_local_only_data_do_not_route_to_public_endpoints():
    router = ModelRouter()
    router.register(_endpoint("public", privacy=PrivacyLevel.PUBLIC))
    router.register(_endpoint("sensitive", privacy=PrivacyLevel.SENSITIVE))
    router.register(_endpoint("local", local=True))

    sensitive = router.route(RouteRequest("analysis", privacy="sensitive"))
    assert sensitive.selected.endpoint_id in {"sensitive", "local"}
    assert "public" in sensitive.rejected

    local_only = router.route(RouteRequest("analysis", privacy="local-only"))
    assert local_only.selected.endpoint_id == "local"
    assert "public" in local_only.rejected
    assert "sensitive" in local_only.rejected


def test_cost_and_latency_budgets_fail_closed():
    router = ModelRouter()
    router.register(_endpoint("slow", latency=900.0, input_cost=0.1, output_cost=0.1))
    router.register(_endpoint("expensive", latency=50.0, input_cost=100.0, output_cost=100.0))

    with pytest.raises(NoRoute) as exc:
        router.route(
            RouteRequest(
                "bounded",
                context_tokens=1000,
                expected_output_tokens=1000,
                latency_budget_ms=40,
                cost_budget=0.00001,
            )
        )
    text = str(exc.value)
    assert "latency" in text
    assert "cost" in text


def test_observed_quality_and_reliability_change_selection_and_fallback_order():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("a", provider="alpha", latency=100))
    router.register(_endpoint("b", provider="beta", latency=100))

    router.observe("a", ok=True, quality=0.95, latency_ms=100, cost=0.001, observed_at=1)
    router.observe("b", ok=False, quality=0.20, latency_ms=100, cost=0.001, observed_at=1)
    first = router.route(RouteRequest("code"))
    assert first.selected.endpoint_id == "a"
    assert first.fallback_endpoint_ids == ("b",)

    router.observe("a", ok=False, quality=0.10, latency_ms=100, cost=0.001, observed_at=2)
    router.observe("b", ok=True, quality=0.99, latency_ms=100, cost=0.001, observed_at=2)
    second = router.route(RouteRequest("code"))
    assert second.selected.endpoint_id == "b"
    assert second.fallback_endpoint_ids == ("a",)


def test_provider_preference_is_tie_breaking_signal_not_hard_routing():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("a", provider="alpha", latency=100))
    router.register(_endpoint("b", provider="beta", latency=100))

    tied = router.route(RouteRequest("chat", preferred_providers=("beta", "alpha")))
    assert tied.selected.endpoint_id == "b"

    router.observe("a", ok=True, quality=1.0, latency_ms=10, cost=0.0, observed_at=1)
    router.observe("b", ok=False, quality=0.0, latency_ms=1000, cost=1.0, observed_at=1)
    measured = router.route(RouteRequest("chat", preferred_providers=("beta", "alpha")))
    assert measured.selected.endpoint_id == "a"


def test_invalid_telemetry_sample_is_atomic():
    router = ModelRouter(telemetry_alpha=0.5)
    router.register(_endpoint("a"))
    before = router.snapshot()

    with pytest.raises(ValueError, match="quality"):
        router.observe("a", ok=False, quality=math.nan, observed_at=1)
    assert router.snapshot() == before

    with pytest.raises(ValueError, match="latency_ms"):
        router.observe("a", ok=False, latency_ms=-1, observed_at=1)
    assert router.snapshot() == before

    with pytest.raises(ValueError, match="observed_at"):
        router.observe("a", ok=False, observed_at=math.inf)
    assert router.snapshot() == before


def test_replace_resets_telemetry_identity_boundary():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("shared", provider="old", model="old-model"))
    router.observe("shared", ok=False, quality=0.0, latency_ms=5000, cost=10, observed_at=1)
    degraded = router.snapshot()["endpoints"][0]["telemetry"]
    assert degraded["observations"] == 1
    assert degraded["reliability_ewma"] == 0.0

    router.register(
        _endpoint("shared", provider="new", model="new-model"),
        replace=True,
    )
    fresh = router.snapshot()["endpoints"][0]["telemetry"]
    assert fresh["observations"] == 0
    assert fresh["reliability_ewma"] == 1.0
    assert router.route(RouteRequest("chat")).selected.provider == "new"


def test_unregister_drops_telemetry_before_id_reuse():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("x"))
    router.observe("x", ok=False, quality=0.0, observed_at=1)
    assert router.unregister("x") is True
    assert router.unregister("x") is False

    router.register(_endpoint("x", provider="fresh"))
    telemetry = router.snapshot()["endpoints"][0]["telemetry"]
    assert telemetry["observations"] == 0
    assert telemetry["reliability_ewma"] == 1.0


def test_minimum_observed_thresholds_are_enforced():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("a"))
    router.observe("a", ok=True, quality=0.7, observed_at=1)

    with pytest.raises(NoRoute, match="quality"):
        router.route(RouteRequest("quality", minimum_quality=0.8))

    router.observe("a", ok=False, quality=1.0, observed_at=2)
    with pytest.raises(NoRoute, match="reliability"):
        router.route(RouteRequest("reliability", minimum_reliability=0.5))


def test_decision_serialization_exposes_explicit_fallbacks_and_rejections():
    router = ModelRouter()
    router.register(_endpoint("primary", provider="p1", latency=50))
    router.register(_endpoint("fallback", provider="p2", latency=75))
    router.register(_endpoint("disabled", enabled=False))

    payload = router.route(RouteRequest("chat")).as_dict()
    assert payload["selected"] == "primary"
    assert payload["fallbacks"] == ["fallback"]
    assert payload["candidates"][0]["endpoint_id"] == "primary"
    assert payload["rejected"]["disabled"] == ["disabled"]


def test_route_request_projects_resource_budget_into_hard_constraints():
    budget = ResourceBudget(
        max_output_tokens=2048,
        max_cost_usd=0.25,
        max_wall_seconds=3.5,
    )

    request = RouteRequest.from_resource_budget(
        "analysis",
        budget,
        context_tokens=1200,
        expected_output_tokens=4096,
        privacy="sensitive",
    )

    assert request.context_tokens == 1200
    assert request.expected_output_tokens == 2048
    assert request.cost_budget == 0.25
    assert request.latency_budget_ms == 3500.0
    assert request.privacy is PrivacyLevel.SENSITIVE


def test_resource_budget_constraints_cannot_be_overridden_by_caller():
    budget = ResourceBudget(max_cost_usd=1.0)

    with pytest.raises(ValueError, match="resource budget owns"):
        RouteRequest.from_resource_budget(
            "analysis",
            budget,
            cost_budget=999.0,
        )


def test_resource_budget_can_make_expensive_route_ineligible():
    budget = ResourceBudget(
        max_output_tokens=1000,
        max_cost_usd=0.0001,
        max_wall_seconds=1.0,
    )
    router = ModelRouter()
    router.register(
        _endpoint(
            "expensive",
            input_cost=100.0,
            output_cost=100.0,
            latency=100,
        )
    )

    request = RouteRequest.from_resource_budget(
        "analysis",
        budget,
        context_tokens=1000,
        expected_output_tokens=1000,
    )

    with pytest.raises(NoRoute, match="cost"):
        router.route(request)


def _governance_context(data_class: str):
    registry = GovernanceRegistry()
    registry.register(
        GovernedDataRecord(
            record_id="context-record",
            tenant_id="tenant-a",
            owner_plane="retrieval",
            source_ref="retrieval:context-record",
            data_class=data_class,
            purposes=("model-inference",),
            deletion_targets=("retrieval",),
            created_at=10.0,
        )
    )
    return registry.context_for(
        ("context-record",),
        tenant_id="tenant-a",
        purpose="model-inference",
    )


def test_route_request_derives_privacy_from_governance_registry() -> None:
    context = _governance_context("confidential")

    request = RouteRequest.from_governance_context(
        "analysis",
        context,
        context_tokens=1000,
        expected_output_tokens=500,
    )

    assert request.privacy is PrivacyLevel.SENSITIVE
    assert request.governance_record_ids == ("context-record",)
    assert request.governance_tenant_id == "tenant-a"
    assert request.governance_purpose == "model-inference"


def test_governed_route_privacy_cannot_be_weakened_by_caller() -> None:
    context = _governance_context("confidential")

    with pytest.raises(ValueError, match="governance context owns privacy"):
        RouteRequest.from_governance_context(
            "analysis",
            context,
            privacy="public",
        )


def test_governance_and_resource_budget_compose_as_hard_constraints() -> None:
    context = _governance_context("confidential")
    budget = ResourceBudget(
        max_output_tokens=300,
        max_cost_usd=0.01,
        max_wall_seconds=2.0,
    )

    request = RouteRequest.from_governance_context(
        "analysis",
        context,
        budget=budget,
        context_tokens=800,
        expected_output_tokens=1000,
    )

    assert request.privacy is PrivacyLevel.SENSITIVE
    assert request.expected_output_tokens == 300
    assert request.cost_budget == 0.01
    assert request.latency_budget_ms == 2000.0


def test_registry_derived_privacy_filters_public_endpoint() -> None:
    context = _governance_context("confidential")
    router = ModelRouter()
    router.register(_endpoint("public", privacy=PrivacyLevel.PUBLIC))
    router.register(_endpoint("sensitive", privacy=PrivacyLevel.SENSITIVE))

    decision = router.route(
        RouteRequest.from_governance_context("analysis", context)
    )

    assert decision.selected.endpoint_id == "sensitive"
    assert "public" in decision.rejected
    payload = decision.as_dict()
    assert payload["governance"] == {
        "record_ids": ["context-record"],
        "tenant_id": "tenant-a",
        "purpose": "model-inference",
        "privacy": "sensitive",
    }


def test_restricted_governed_data_routes_local_only() -> None:
    context = _governance_context("restricted")
    router = ModelRouter()
    router.register(_endpoint("hosted", privacy=PrivacyLevel.SENSITIVE))
    router.register(_endpoint("local", local=True))

    decision = router.route(
        RouteRequest.from_governance_context("analysis", context)
    )

    assert decision.selected.endpoint_id == "local"
    assert "hosted" in decision.rejected

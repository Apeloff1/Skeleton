import math

import pytest

from skeleton.ai.assistant.turn_runtime import (
    BudgetUsage,
    ExecutionBudget,
    TurnSnapshot,
    TurnState,
)
from skeleton.intelligence.admission import ResourceBudget
from skeleton.vault.data_lifecycle import GovernedDataRecord
from skeleton.vault.governance_registry import GovernanceRegistry

from core.model_router import (
    ModelEndpoint,
    ModelRouter,
    EndpointQuarantine,
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
    jurisdiction=None,
    receipt_capable=True,
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
        jurisdiction=jurisdiction,
        receipt_capable=receipt_capable,
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


def test_turn_budget_projects_into_route_constraints():
    budget = ExecutionBudget(
        max_wall_seconds=4.0,
        max_input_tokens=10_000,
        max_output_tokens=1200,
        max_model_calls=4,
        max_tool_calls=8,
        max_agent_depth=2,
        max_parallel_workers=2,
        max_retrieval_queries=4,
        max_external_writes=1,
        max_cost_usd=0.15,
    )
    request = RouteRequest.from_turn_budget(
        "analysis",
        budget,
        context_tokens=6000,
        expected_output_tokens=2000,
        privacy="sensitive",
    )
    assert request.expected_output_tokens == 1200
    assert request.latency_budget_ms == 4000.0
    assert request.cost_budget == 0.15
    assert request.privacy is PrivacyLevel.SENSITIVE


def test_turn_budget_constraints_cannot_be_overridden():
    budget = ExecutionBudget()
    with pytest.raises(ValueError, match="turn budget owns"):
        RouteRequest.from_turn_budget(
            "analysis",
            budget,
            cost_budget=999.0,
        )


def test_jurisdiction_is_a_hard_routing_constraint():
    router = ModelRouter()
    router.register(_endpoint("eu", jurisdiction="eu"))
    router.register(_endpoint("us", jurisdiction="us"))
    router.register(_endpoint("unknown", jurisdiction=None))

    decision = router.route(
        RouteRequest(
            "chat",
            allowed_jurisdictions=frozenset({"eu"}),
        ),
        routed_at=100.0,
    )
    assert decision.selected.endpoint_id == "eu"
    assert "us" in decision.rejected
    assert "unknown" in decision.rejected
    assert any("not allowed" in reason for reason in decision.rejected["us"])
    assert decision.rejected["unknown"] == ("jurisdiction unknown",)


def test_provider_receipt_capability_can_be_required():
    router = ModelRouter()
    router.register(_endpoint("receipts", receipt_capable=True))
    router.register(_endpoint("opaque", receipt_capable=False))

    decision = router.route(
        RouteRequest("chat", require_provider_receipt=True),
        routed_at=100.0,
    )
    assert decision.selected.endpoint_id == "receipts"
    assert decision.rejected["opaque"] == (
        "provider receipt capability required",
    )


def test_minimum_observations_and_telemetry_freshness_fail_closed():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("a"))
    router.observe(
        "a",
        ok=True,
        quality=0.9,
        latency_ms=50,
        cost=0.001,
        observed_at=10.0,
    )

    with pytest.raises(NoRoute, match="observations"):
        router.route(
            RouteRequest("chat", minimum_observations=2),
            routed_at=20.0,
        )

    with pytest.raises(NoRoute, match="telemetry age"):
        router.route(
            RouteRequest("chat", max_telemetry_age_s=5.0),
            routed_at=20.0,
        )

    fresh = router.route(
        RouteRequest(
            "chat",
            minimum_observations=1,
            max_telemetry_age_s=15.0,
        ),
        routed_at=20.0,
    )
    assert fresh.selected.endpoint_id == "a"


def test_missing_telemetry_rejected_when_freshness_is_required():
    router = ModelRouter()
    router.register(_endpoint("a"))

    with pytest.raises(NoRoute, match="telemetry missing"):
        router.route(
            RouteRequest("chat", max_telemetry_age_s=60.0),
            routed_at=100.0,
        )


def test_quarantine_forces_safe_fallback_and_expiry_restores_endpoint():
    router = ModelRouter(telemetry_alpha=1.0)
    router.register(_endpoint("primary", provider="p1", latency=10))
    router.register(_endpoint("fallback", provider="p2", latency=20))
    router.observe(
        "primary",
        ok=True,
        quality=1.0,
        latency_ms=10,
        cost=0.0,
        observed_at=90.0,
    )
    router.observe(
        "fallback",
        ok=True,
        quality=0.8,
        latency_ms=20,
        cost=0.0,
        observed_at=90.0,
    )

    quarantine = router.quarantine(
        "primary",
        reason_code="provider-health",
        observed_at=100.0,
        expires_at=120.0,
    )
    assert isinstance(quarantine, EndpointQuarantine)

    degraded = router.route(RouteRequest("chat"), routed_at=110.0)
    assert degraded.selected.endpoint_id == "fallback"
    assert degraded.rejected["primary"] == (
        "quarantined:provider-health",
    )

    recovered = router.route(RouteRequest("chat"), routed_at=121.0)
    assert recovered.selected.endpoint_id == "primary"


def test_manual_quarantine_clear_restores_endpoint():
    router = ModelRouter()
    router.register(_endpoint("a", latency=10))
    router.register(_endpoint("b", latency=20))
    router.quarantine(
        "a",
        reason_code="manual",
        observed_at=1.0,
    )
    assert router.route(RouteRequest("chat"), routed_at=2.0).selected.endpoint_id == "b"
    assert router.clear_quarantine("a") is True
    assert router.clear_quarantine("a") is False
    assert router.route(RouteRequest("chat"), routed_at=3.0).selected.endpoint_id == "a"


def test_route_decision_digest_binds_hard_constraint_request():
    router = ModelRouter()
    router.register(_endpoint("a", jurisdiction="eu"))
    first = router.route(
        RouteRequest(
            "chat",
            allowed_jurisdictions=frozenset({"eu"}),
            require_provider_receipt=True,
        ),
        routed_at=42.0,
    )
    second = router.route(
        RouteRequest(
            "chat",
            allowed_jurisdictions=frozenset({"eu"}),
            require_provider_receipt=True,
        ),
        routed_at=42.0,
    )
    assert len(first.request_digest) == 64
    assert len(first.digest) == 64
    assert first.request_digest == second.request_digest
    assert first.digest == second.digest
    payload = first.as_dict()
    assert payload["request_digest"] == first.request_digest
    assert payload["decision_digest"] == first.digest


def test_invalid_routing_evidence_constraints_are_rejected():
    with pytest.raises(ValueError, match="minimum_observations"):
        RouteRequest("chat", minimum_observations=-1)

    with pytest.raises(ValueError, match="max_telemetry_age_s"):
        RouteRequest("chat", max_telemetry_age_s=math.nan)

    with pytest.raises(ValueError, match="receipt_capable"):
        _endpoint("bad-receipt", receipt_capable="yes")


def test_governance_and_turn_budget_compose_as_hard_constraints():
    context = _governance_context("confidential")
    budget = ExecutionBudget(
        max_wall_seconds=2.5,
        max_input_tokens=8000,
        max_output_tokens=400,
        max_model_calls=3,
        max_tool_calls=4,
        max_agent_depth=1,
        max_parallel_workers=1,
        max_retrieval_queries=2,
        max_external_writes=0,
        max_cost_usd=0.02,
    )

    request = RouteRequest.from_governance_context(
        "analysis",
        context,
        budget=budget,
        context_tokens=1200,
        expected_output_tokens=1000,
        require_provider_receipt=True,
    )

    assert request.privacy is PrivacyLevel.SENSITIVE
    assert request.expected_output_tokens == 400
    assert request.cost_budget == 0.02
    assert request.latency_budget_ms == 2500.0
    assert request.require_provider_receipt is True
    assert request.governance_record_ids == ("context-record",)


def _turn_snapshot_for_routing(
    *,
    usage: BudgetUsage | None = None,
    state: TurnState = TurnState.ROUTING,
) -> TurnSnapshot:
    return TurnSnapshot(
        operation_id="route-turn",
        request_digest="a" * 64,
        thread_id="thread",
        causal_user_message_id="message",
        state=state,
        budget=ExecutionBudget(
            max_wall_seconds=10.0,
            max_input_tokens=10_000,
            max_output_tokens=2_000,
            max_model_calls=3,
            max_tool_calls=8,
            max_agent_depth=2,
            max_parallel_workers=2,
            max_retrieval_queries=4,
            max_external_writes=1,
            max_cost_usd=1.0,
        ),
        usage=usage or BudgetUsage(),
    )


def test_turn_snapshot_projects_only_remaining_route_authority():
    turn = _turn_snapshot_for_routing(
        usage=BudgetUsage(
            wall_seconds=4.0,
            input_tokens=1_000,
            output_tokens=500,
            model_calls=1,
            cost_usd=0.25,
        )
    )
    request = RouteRequest.from_turn_snapshot(
        "analysis",
        turn,
        context_tokens=500,
        expected_output_tokens=1_000,
    )
    assert request.latency_budget_ms == 6000.0
    assert request.cost_budget == 0.75
    assert request.expected_output_tokens == 1000


def test_turn_snapshot_does_not_restore_exhausted_model_call_authority():
    turn = _turn_snapshot_for_routing(
        usage=BudgetUsage(model_calls=3)
    )
    with pytest.raises(ValueError, match="model-call budget exhausted"):
        RouteRequest.from_turn_snapshot("analysis", turn)


def test_turn_snapshot_rejects_context_above_remaining_input_budget():
    turn = _turn_snapshot_for_routing(
        usage=BudgetUsage(input_tokens=9_900)
    )
    with pytest.raises(ValueError, match="remaining input-token"):
        RouteRequest.from_turn_snapshot(
            "analysis",
            turn,
            context_tokens=101,
        )


def test_turn_snapshot_rejects_output_above_remaining_output_budget():
    turn = _turn_snapshot_for_routing(
        usage=BudgetUsage(output_tokens=1_900)
    )
    with pytest.raises(ValueError, match="remaining output-token"):
        RouteRequest.from_turn_snapshot(
            "analysis",
            turn,
            expected_output_tokens=101,
        )


def test_terminal_turn_cannot_reacquire_model_routing_authority():
    turn = _turn_snapshot_for_routing(state=TurnState.COMPLETE)
    with pytest.raises(ValueError, match="terminal turn"):
        RouteRequest.from_turn_snapshot("analysis", turn)

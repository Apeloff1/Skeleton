from __future__ import annotations

from dataclasses import replace

from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.model_placement import (
    EndpointHealth,
    EndpointProfile,
    EndpointState,
    ModelPlacementEngine,
    PlacementBudget,
    PlacementPolicy,
    PlacementRequest,
    PrivacyTier,
    ProviderFailureKind,
)
from skeleton.ai.assistant.tool_recovery import (
    PriorToolOutcome,
    ToolRecoveryAction,
    ToolRecoveryEvidence,
    decide_tool_recovery,
)


DIGEST = "a" * 64
ARG_DIGEST = "b" * 64


def profile(
    endpoint_id: str,
    *,
    local: bool = False,
    privacy: PrivacyTier = PrivacyTier.RESTRICTED,
    modalities: tuple[str, ...] = ("text",),
    jurisdictions: tuple[str, ...] = ("NO", "EU"),
    quality: float = 0.95,
    reliability: float = 0.999,
    latency: int = 800,
    cost: float = 0.01,
) -> EndpointProfile:
    return EndpointProfile(
        endpoint_id=endpoint_id,
        provider_id=f"provider-{endpoint_id}",
        model_id=f"model-{endpoint_id}",
        modalities=modalities,
        privacy_ceiling=privacy,
        local=local,
        jurisdictions=jurisdictions,
        context_tokens=200_000,
        max_output_tokens=16_000,
        quality=quality,
        reliability=reliability,
        p95_latency_ms=latency,
        cost_per_1k_tokens_usd=cost,
    )


def health(
    endpoint_id: str,
    *,
    state: EndpointState = EndpointState.HEALTHY,
    observed_at: float = 100.0,
    in_flight: int = 0,
    max_concurrency: int = 10,
    breaker_until: float = 0.0,
) -> EndpointHealth:
    return EndpointHealth(
        endpoint_id=endpoint_id,
        state=state,
        observed_at=observed_at,
        max_age_s=30.0,
        in_flight=in_flight,
        max_concurrency=max_concurrency,
        breaker_until=breaker_until,
    )


def request(
    *,
    local_only: bool = False,
    privacy: PrivacyTier = PrivacyTier.SENSITIVE,
    modalities: tuple[str, ...] = ("text",),
    jurisdictions: tuple[str, ...] = ("NO",),
    quality: float = 0.9,
    reliability: float = 0.99,
) -> PlacementRequest:
    return PlacementRequest(
        operation_id="turn-1",
        request_digest=DIGEST,
        required_modalities=modalities,
        privacy_tier=privacy,
        local_only=local_only,
        allowed_jurisdictions=jurisdictions,
        input_tokens=2_000,
        output_tokens=1_000,
        minimum_quality=quality,
        minimum_reliability=reliability,
    )


def budget(*, calls: int = 2, wall: int = 5_000, cost: float = 10.0) -> PlacementBudget:
    return PlacementBudget(
        model_calls_remaining=calls,
        wall_time_ms_remaining=wall,
        cost_usd_remaining=cost,
    )


def engine(*, allow_degraded: bool = False) -> ModelPlacementEngine:
    return ModelPlacementEngine(
        PlacementPolicy(
            policy_id="chat-routing-v2",
            allow_degraded=allow_degraded,
            max_call_cost_usd=5.0,
        )
    )


def tool_evidence(
    *,
    side_effect: SideEffectClass = SideEffectClass.READ_ONLY,
    outcome: PriorToolOutcome = PriorToolOutcome.KNOWN_FAILURE,
    durable: bool = True,
    receipt_status: str | None = "failed",
    effect_may_have_started: bool = False,
    idempotency: bool = True,
    reconcile: bool = True,
    compensate: bool = True,
    authority: bool = True,
    retries: int = 2,
    downstream_failure: bool = False,
) -> ToolRecoveryEvidence:
    return ToolRecoveryEvidence(
        operation_id="turn-1",
        request_digest=DIGEST,
        proposal_id="proposal-1",
        capability_id="calendar.write",
        arguments_digest=ARG_DIGEST,
        side_effect=side_effect,
        prior_outcome=outcome,
        durable_receipt=durable,
        receipt_status=receipt_status if durable else None,
        receipt_request_digest=DIGEST if durable else None,
        receipt_arguments_digest=ARG_DIGEST if durable else None,
        effect_may_have_started=effect_may_have_started,
        idempotency_key_present=idempotency,
        reconciliation_available=reconcile,
        compensation_available=compensate,
        explicit_user_authority_valid=authority,
        retry_budget_remaining=retries,
        downstream_failure=downstream_failure,
    )


def test_placement_is_deterministic_and_quality_first() -> None:
    endpoints = (
        profile("b", quality=0.94, latency=400),
        profile("a", quality=0.96, latency=900),
    )
    observations = {item.endpoint_id: health(item.endpoint_id) for item in endpoints}
    first = engine().plan(
        request=request(),
        budget=budget(),
        endpoints=endpoints,
        health=observations,
        observed_at=110.0,
    )
    second = engine().plan(
        request=request(),
        budget=budget(),
        endpoints=tuple(reversed(endpoints)),
        health=observations,
        observed_at=110.0,
    )
    assert first.selected_endpoint_id == "a"
    assert first.fallback_endpoint_ids == ("b",)
    assert first.decision_digest == second.decision_digest


def test_stale_health_fails_closed() -> None:
    p = profile("remote")
    decision = engine().plan(
        request=request(),
        budget=budget(),
        endpoints=(p,),
        health={"remote": health("remote", observed_at=10.0)},
        observed_at=100.0,
    )
    assert decision.selected_endpoint_id is None
    assert "health-stale" in decision.admissions[0].reasons


def test_local_only_cannot_fallback_to_remote() -> None:
    endpoints = (profile("remote"), profile("local", local=True))
    decision = engine().plan(
        request=request(local_only=True),
        budget=budget(),
        endpoints=endpoints,
        health={item.endpoint_id: health(item.endpoint_id) for item in endpoints},
        observed_at=110.0,
    )
    assert decision.selected_endpoint_id == "local"
    remote = next(item for item in decision.admissions if item.endpoint_id == "remote")
    assert "local-only-requirement" in remote.reasons


def test_privacy_floor_cannot_be_weakened() -> None:
    endpoints = (
        profile("restricted", privacy=PrivacyTier.RESTRICTED),
        profile("internal", privacy=PrivacyTier.INTERNAL),
    )
    decision = engine().plan(
        request=request(privacy=PrivacyTier.SENSITIVE),
        budget=budget(),
        endpoints=endpoints,
        health={item.endpoint_id: health(item.endpoint_id) for item in endpoints},
        observed_at=110.0,
    )
    assert decision.selected_endpoint_id == "restricted"
    rejected = next(item for item in decision.admissions if item.endpoint_id == "internal")
    assert "privacy-ceiling-insufficient" in rejected.reasons


def test_required_modality_and_jurisdiction_are_hard_constraints() -> None:
    endpoints = (
        profile("text-only", modalities=("text",)),
        profile("vision-us", modalities=("text", "image"), jurisdictions=("US",)),
        profile("vision-no", modalities=("text", "image"), jurisdictions=("NO",)),
    )
    decision = engine().plan(
        request=request(modalities=("text", "image"), jurisdictions=("NO",)),
        budget=budget(),
        endpoints=endpoints,
        health={item.endpoint_id: health(item.endpoint_id) for item in endpoints},
        observed_at=110.0,
    )
    assert decision.selected_endpoint_id == "vision-no"
    reasons = {item.endpoint_id: set(item.reasons) for item in decision.admissions}
    assert "required-modality-missing" in reasons["text-only"]
    assert "jurisdiction-not-admitted" in reasons["vision-us"]


def test_budget_and_deadline_are_admission_invariants() -> None:
    expensive = profile("expensive", cost=10.0)
    slow = profile("slow", latency=20_000)
    decision = engine().plan(
        request=request(),
        budget=budget(wall=1_000, cost=1.0),
        endpoints=(expensive, slow),
        health={"expensive": health("expensive"), "slow": health("slow")},
        observed_at=110.0,
    )
    assert decision.selected_endpoint_id is None
    reasons = {item.endpoint_id: set(item.reasons) for item in decision.admissions}
    assert "turn-cost-budget-insufficient" in reasons["expensive"]
    assert "deadline-budget-insufficient" in reasons["slow"]


def test_degraded_endpoint_requires_explicit_policy() -> None:
    p = profile("degraded")
    observations = {"degraded": health("degraded", state=EndpointState.DEGRADED)}
    denied = engine().plan(
        request=request(),
        budget=budget(),
        endpoints=(p,),
        health=observations,
        observed_at=110.0,
    )
    admitted = engine(allow_degraded=True).plan(
        request=request(),
        budget=budget(),
        endpoints=(p,),
        health=observations,
        observed_at=110.0,
    )
    assert denied.selected_endpoint_id is None
    assert admitted.selected_endpoint_id == "degraded"


def test_open_breaker_and_saturation_fail_closed() -> None:
    endpoints = (profile("breaker"), profile("busy"))
    observations = {
        "breaker": health("breaker", breaker_until=200.0),
        "busy": health("busy", in_flight=10, max_concurrency=10),
    }
    decision = engine().plan(
        request=request(),
        budget=budget(),
        endpoints=endpoints,
        health=observations,
        observed_at=110.0,
    )
    assert decision.selected_endpoint_id is None
    reasons = {item.endpoint_id: set(item.reasons) for item in decision.admissions}
    assert "circuit-breaker-open" in reasons["breaker"]
    assert "endpoint-saturated" in reasons["busy"]


def test_failover_requires_retryable_failure_and_prior_admission() -> None:
    endpoints = (profile("primary", quality=0.99), profile("fallback", quality=0.95))
    observations = {item.endpoint_id: health(item.endpoint_id) for item in endpoints}
    e = engine()
    prior = e.plan(
        request=request(),
        budget=budget(),
        endpoints=endpoints,
        health=observations,
        observed_at=110.0,
    )
    fresh = e.plan(
        request=request(),
        budget=budget(),
        endpoints=endpoints,
        health=observations,
        observed_at=111.0,
        excluded_endpoint_ids=("primary",),
    )
    accepted = e.authorize_failover(
        prior=prior,
        failure_kind=ProviderFailureKind.TRANSIENT,
        fresh=fresh,
    )
    denied = e.authorize_failover(
        prior=prior,
        failure_kind=ProviderFailureKind.POLICY,
        fresh=fresh,
    )
    assert accepted.authorized
    assert accepted.endpoint_id == "fallback"
    assert not denied.authorized
    assert "failure-class-not-failover-eligible" in denied.reasons


def test_failover_allows_consumed_budget_but_refuses_budget_amplification() -> None:
    endpoints = (profile("primary", quality=0.99), profile("fallback", quality=0.95))
    observations = {item.endpoint_id: health(item.endpoint_id) for item in endpoints}
    e = engine()
    prior = e.plan(
        request=request(),
        budget=budget(calls=3, wall=5_000, cost=10.0),
        endpoints=endpoints,
        health=observations,
        observed_at=110.0,
    )
    consumed = e.plan(
        request=request(),
        budget=budget(calls=2, wall=4_000, cost=9.0),
        endpoints=endpoints,
        health=observations,
        observed_at=111.0,
        excluded_endpoint_ids=("primary",),
    )
    allowed = e.authorize_failover(
        prior=prior,
        failure_kind=ProviderFailureKind.CAPACITY,
        fresh=consumed,
    )
    amplified = e.plan(
        request=request(),
        budget=budget(calls=4, wall=6_000, cost=11.0),
        endpoints=endpoints,
        health=observations,
        observed_at=111.0,
        excluded_endpoint_ids=("primary",),
    )
    denied = e.authorize_failover(
        prior=prior,
        failure_kind=ProviderFailureKind.CAPACITY,
        fresh=amplified,
    )
    assert allowed.authorized
    assert not denied.authorized
    assert "failover-budget-amplified" in denied.reasons


def test_placement_and_failover_are_non_executing_authorities() -> None:
    endpoints = (profile("primary"),)
    decision = engine().plan(
        request=request(),
        budget=budget(),
        endpoints=endpoints,
        health={"primary": health("primary")},
        observed_at=110.0,
    )
    assert decision.authority_scope == "model-placement-only"
    assert decision.production_authority is False


def test_unknown_consequential_write_reconciles_before_retry() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.EXTERNAL_WRITE,
        outcome=PriorToolOutcome.UNKNOWN,
        durable=False,
        receipt_status=None,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.RECONCILE
    assert not decision.retry_consumes_budget


def test_unknown_consequential_write_quarantines_without_reconciliation() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.EXTERNAL_WRITE,
        outcome=PriorToolOutcome.UNKNOWN,
        durable=False,
        receipt_status=None,
        reconcile=False,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.QUARANTINE


def test_unknown_read_only_can_retry_under_budget() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.READ_ONLY,
        outcome=PriorToolOutcome.UNKNOWN,
        durable=False,
        receipt_status=None,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.RETRY_READ_ONLY
    assert decision.retry_consumes_budget


def test_write_retry_requires_durable_failure_and_idempotency() -> None:
    evidence = tool_evidence(side_effect=SideEffectClass.EXTERNAL_WRITE)
    accepted = decide_tool_recovery(evidence)
    denied = decide_tool_recovery(replace(evidence, idempotency_key_present=False))
    assert accepted.action is ToolRecoveryAction.RETRY_IDEMPOTENT
    assert denied.action is ToolRecoveryAction.QUARANTINE


def test_write_retry_without_durable_receipt_quarantines() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.EXTERNAL_WRITE,
        durable=False,
        receipt_status=None,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.QUARANTINE
    assert "write-retry-requires-durable-failure-receipt" in decision.reasons


def test_security_sensitive_retry_requires_fresh_user_authority() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.SECURITY_SENSITIVE,
        authority=False,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.REQUIRE_REAUTHORIZATION


def test_reversible_write_compensates_after_downstream_failure() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.REVERSIBLE_WRITE,
        outcome=PriorToolOutcome.SUCCEEDED,
        receipt_status="succeeded",
        downstream_failure=True,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.COMPENSATE


def test_effect_that_may_have_started_never_blindly_retries() -> None:
    evidence = tool_evidence(
        side_effect=SideEffectClass.EXTERNAL_WRITE,
        effect_may_have_started=True,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.RECONCILE


def test_receipt_binding_mismatch_quarantines() -> None:
    evidence = tool_evidence()
    mismatched = replace(evidence, receipt_arguments_digest="c" * 64)
    decision = decide_tool_recovery(mismatched)
    assert decision.action is ToolRecoveryAction.QUARANTINE
    assert "receipt-arguments-binding-mismatch" in decision.reasons


def test_retry_budget_exhaustion_is_terminal_for_known_failure() -> None:
    evidence = tool_evidence(retries=0)
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.TERMINAL_FAILURE
    assert decision.terminal


def test_successful_durable_receipt_is_reused_not_replayed() -> None:
    evidence = tool_evidence(
        outcome=PriorToolOutcome.SUCCEEDED,
        receipt_status="succeeded",
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.RETURN_RECEIPT


def test_not_started_operation_is_not_misclassified_as_retry() -> None:
    evidence = tool_evidence(
        outcome=PriorToolOutcome.NOT_STARTED,
        durable=False,
        receipt_status=None,
        effect_may_have_started=False,
    )
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.EXECUTE_ORIGINAL
    assert not decision.retry_consumes_budget


def test_tool_recovery_decisions_never_gain_production_authority() -> None:
    decision = decide_tool_recovery(tool_evidence())
    assert decision.authority_scope == "tool-recovery-decision-only"
    assert decision.production_authority is False


def test_unknown_outcome_cannot_coexist_with_durable_receipt() -> None:
    evidence = tool_evidence(outcome=PriorToolOutcome.UNKNOWN)
    decision = decide_tool_recovery(evidence)
    assert decision.action is ToolRecoveryAction.QUARANTINE
    assert "unknown-outcome-contradicts-durable-receipt" in decision.reasons

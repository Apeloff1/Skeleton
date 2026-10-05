import pytest

from skeleton.ai.runtime.deferred.operational_health import (
    DependencyHealth, DependencyKind, DependencyRisk, FailoverDecision,
    HealthBlocker, HealthDimension, HealthScorecard, HealthState,
    ProviderDependency, ProviderHealth, ProviderOutcome, ProviderProfile,
    ProviderRisk, decide_failover,
)

D = "a" * 64


def dim(name="latency", state=HealthState.HEALTHY, score=0.99):
    return HealthDimension(name, state, score, "2026-10-06T00:00:00Z", "abc123", "prod", D)


def test_scorecard_never_masks_hard_blocker_with_green_average():
    card = HealthScorecard("api", (dim(), dim("errors", score=1.0)), (HealthBlocker("b1", "errors", "SLO exhausted", D),))
    assert card.aggregate_score > 0.9
    assert card.state is HealthState.BLOCKED


def test_scorecard_surfaces_unknown_and_binds_environment_version_time():
    card = HealthScorecard("worker", (dim(state=HealthState.UNKNOWN),), ())
    assert card.state is HealthState.UNKNOWN
    assert len(card.identity) == 64


def test_scorecard_rejects_blocker_for_hidden_dimension():
    with pytest.raises(ValueError, match="unknown dimension"):
        HealthScorecard("api", (dim(),), (HealthBlocker("b1", "security", "critical", D),))


def test_critical_vulnerable_dependency_requires_disposition():
    with pytest.raises(ValueError, match="risk disposition"):
        DependencyRisk("pkg", "1", DependencyKind.RUNTIME, True, True, True, D)


def test_dependency_health_preserves_dependency_kind_and_blockers():
    bad = DependencyRisk("pkg", "1", DependencyKind.TRANSITIVE, True, False, False, D, "replace")
    health = DependencyHealth(D, (bad,))
    assert health.blockers == (bad,)
    assert bad.kind is DependencyKind.TRANSITIVE


def test_duplicate_dependency_coordinate_is_rejected():
    dep = DependencyRisk("pkg", "1", DependencyKind.BUILD, False, True, False, D)
    with pytest.raises(ValueError, match="duplicate"):
        DependencyHealth(D, (dep, dep))


def test_critical_provider_requires_fallback_or_disposition():
    dependency = ProviderDependency("p1", "llm", "eu", True)
    with pytest.raises(ValueError, match="fallback"):
        ProviderRisk(dependency, 1.0, None, None)


def test_explicit_no_fallback_is_allowed_and_auditable():
    dependency = ProviderDependency("p1", "llm", "eu", True)
    risk = ProviderRisk(dependency, 1.0, None, "service unavailable rather than cross-boundary routing")
    assert risk.no_fallback_disposition


def test_failover_requires_compatible_capability_and_data_boundary():
    p = ProviderProfile("p1", "llm", "eu")
    bad_boundary = ProviderProfile("p2", "llm", "us")
    bad_capability = ProviderProfile("p3", "embedding", "eu")
    health = (ProviderHealth("p1", False, "t", D), ProviderHealth("p2", True, "t", D), ProviderHealth("p3", True, "t", D))
    decision = decide_failover(p, (bad_boundary, bad_capability), health, None)
    assert not decision.allowed
    assert decision.selected is None


def test_unknown_external_outcome_blocks_cross_provider_retry():
    p = ProviderProfile("p1", "llm", "eu")
    p2 = ProviderProfile("p2", "llm", "eu")
    health = (ProviderHealth("p1", False, "t", D), ProviderHealth("p2", True, "t", D))
    outcome = ProviderOutcome("op-1", "p1", False)
    decision = decide_failover(p, (p2,), health, outcome)
    assert decision == FailoverDecision("p1", None, False, "unknown external outcome requires reconciliation")


def test_failover_selects_only_healthy_compatible_provider():
    p = ProviderProfile("p1", "llm", "eu")
    p2 = ProviderProfile("p2", "llm", "eu")
    health = (ProviderHealth("p1", False, "t", D), ProviderHealth("p2", True, "t", D))
    decision = decide_failover(p, (p2,), health, ProviderOutcome("op-1", "p1", True))
    assert decision.allowed
    assert decision.selected == "p2"


def test_missing_primary_health_fails_closed():
    p = ProviderProfile("p1", "llm", "eu")
    decision = decide_failover(p, (), (), None)
    assert not decision.allowed
    assert decision.reason == "primary health unknown"

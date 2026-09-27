from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.intelligence.strategy_registry import (
    ReasoningPolicy,
    ReasoningPolicyError,
    ReasoningPolicyRegistry,
    ReasoningRisk,
    ReasoningStep,
    ReasoningStrategy,
    StopDisposition,
    StrategyCandidate,
    evaluate_stopping,
    select_strategy,
)


def _policy(**overrides: object) -> ReasoningPolicy:
    values: dict[str, object] = {
        "policy_id": "general-reasoning",
        "version": 1,
        "allowed_strategies": (
            ReasoningStrategy.DIRECT,
            ReasoningStrategy.RETRIEVE,
            ReasoningStrategy.DECOMPOSE,
            ReasoningStrategy.SEARCH,
            ReasoningStrategy.VERIFY,
        ),
        "default_strategy": ReasoningStrategy.DIRECT,
        "max_steps": 6,
        "max_tokens": 6000,
        "max_cost_units": 12.0,
        "max_wall_time_s": 120.0,
        "min_value_of_information": 0.10,
        "completion_confidence": 0.85,
        "max_uncertainty": 0.55,
        "max_stall_steps": 3,
        "require_verification_for_high_risk": True,
    }
    values.update(overrides)
    return ReasoningPolicy(**values)


def _candidate(
    strategy: ReasoningStrategy,
    *,
    quality: float = 0.80,
    uncertainty_reduction: float = 0.30,
    cost: float = 1.0,
    tokens: int = 500,
    wall_time: float = 10.0,
    verification: bool = False,
) -> StrategyCandidate:
    return StrategyCandidate(
        strategy=strategy,
        expected_quality=quality,
        expected_uncertainty_reduction=uncertainty_reduction,
        expected_cost_units=cost,
        expected_tokens=tokens,
        expected_wall_time_s=wall_time,
        verification_capable=verification,
    )


def _step(
    index: int = 1,
    *,
    tokens: int = 500,
    cost: float = 1.0,
    elapsed: float = 10.0,
    confidence: float = 0.60,
    uncertainty: float = 0.30,
    voi: float = 0.40,
    progress: str = "a",
    verified: bool = False,
    explicit_stop: bool = False,
) -> ReasoningStep:
    return ReasoningStep(
        step_index=index,
        cumulative_tokens=tokens,
        cumulative_cost_units=cost,
        elapsed_s=elapsed,
        confidence=confidence,
        uncertainty=uncertainty,
        value_of_information=voi,
        progress_digest=progress * 64,
        verification_passed=verified,
        explicit_stop=explicit_stop,
    )


def test_policy_digest_is_deterministic_and_versioned() -> None:
    left = _policy()
    right = _policy()

    assert left.digest == right.digest
    assert len(left.digest) == 64
    assert replace(left, version=2).digest != left.digest


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("max_steps", 0, "max_steps"),
        ("max_tokens", 0, "max_tokens"),
        ("max_cost_units", 0.0, "max_cost_units"),
        ("max_wall_time_s", 0.0, "max_wall_time_s"),
        ("max_stall_steps", 1, "at least two"),
        ("max_stall_steps", 7, "cannot exceed"),
        ("min_value_of_information", -0.1, "min_value_of_information"),
        ("completion_confidence", 1.1, "completion_confidence"),
        ("max_uncertainty", float("nan"), "max_uncertainty"),
    ),
)
def test_policy_rejects_unbounded_or_invalid_limits(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ReasoningPolicyError, match=message):
        _policy(**{field: value})


def test_policy_registry_is_immutable_by_id_and_version() -> None:
    registry = ReasoningPolicyRegistry()
    policy = _policy()
    registry.register(policy)
    registry.register(policy)

    assert registry.get("general-reasoning", 1) == policy

    with pytest.raises(ReasoningPolicyError, match="immutable"):
        registry.register(replace(policy, max_steps=5))

    registry.register(replace(policy, version=2, max_steps=5))
    assert registry.latest("general-reasoning").version == 2
    assert len(registry.snapshot()["digest"]) == 64


def test_low_risk_selection_prefers_highest_bounded_value() -> None:
    policy = _policy()
    direct = _candidate(
        ReasoningStrategy.DIRECT,
        quality=0.90,
        uncertainty_reduction=0.20,
        cost=0.5,
        tokens=300,
        wall_time=5.0,
    )
    search = _candidate(
        ReasoningStrategy.SEARCH,
        quality=0.82,
        uncertainty_reduction=0.45,
        cost=4.0,
        tokens=2500,
        wall_time=50.0,
    )

    decision = select_strategy(
        policy,
        (search, direct),
        risk=ReasoningRisk.LOW,
    )

    assert decision.strategy is ReasoningStrategy.DIRECT
    assert decision.policy_digest == policy.digest
    assert len(decision.candidates_digest) == 64


def test_high_risk_selection_requires_verification_capability() -> None:
    policy = _policy()
    direct = _candidate(
        ReasoningStrategy.DIRECT,
        quality=0.99,
        verification=False,
    )
    verify = _candidate(
        ReasoningStrategy.VERIFY,
        quality=0.70,
        uncertainty_reduction=0.50,
        verification=True,
    )

    decision = select_strategy(
        policy,
        (direct, verify),
        risk=ReasoningRisk.HIGH,
    )

    assert decision.strategy is ReasoningStrategy.VERIFY
    assert decision.reason.endswith("with-verification")


def test_strategy_selection_filters_candidates_over_any_budget() -> None:
    policy = _policy()
    too_many_tokens = _candidate(
        ReasoningStrategy.SEARCH,
        quality=1.0,
        tokens=policy.max_tokens + 1,
    )
    too_expensive = _candidate(
        ReasoningStrategy.DECOMPOSE,
        quality=1.0,
        cost=policy.max_cost_units + 1.0,
    )
    too_slow = _candidate(
        ReasoningStrategy.RETRIEVE,
        quality=1.0,
        wall_time=policy.max_wall_time_s + 1.0,
    )
    direct = _candidate(ReasoningStrategy.DIRECT, quality=0.50)

    decision = select_strategy(
        policy,
        (too_many_tokens, too_expensive, too_slow, direct),
        risk=ReasoningRisk.LOW,
    )

    assert decision.strategy is ReasoningStrategy.DIRECT


def test_no_admissible_strategy_fails_closed() -> None:
    policy = _policy()
    candidate = _candidate(
        ReasoningStrategy.DIRECT,
        tokens=policy.max_tokens + 1,
    )

    with pytest.raises(ReasoningPolicyError, match="no admissible"):
        select_strategy(policy, (candidate,), risk=ReasoningRisk.LOW)


def test_candidate_order_does_not_change_selection_identity() -> None:
    policy = _policy()
    direct = _candidate(ReasoningStrategy.DIRECT, quality=0.90)
    retrieve = _candidate(
        ReasoningStrategy.RETRIEVE,
        quality=0.85,
        uncertainty_reduction=0.50,
    )

    left = select_strategy(
        policy,
        (direct, retrieve),
        risk=ReasoningRisk.MEDIUM,
    )
    right = select_strategy(
        policy,
        (retrieve, direct),
        risk=ReasoningRisk.MEDIUM,
    )

    assert left.strategy == right.strategy
    assert left.candidates_digest == right.candidates_digest
    assert left.digest == right.digest


def test_bounded_search_continues_only_with_budget_and_value() -> None:
    decision = evaluate_stopping(
        _policy(),
        (_step(),),
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.CONTINUE
    assert decision.reason == "bounded-search-has-value-and-budget"
    assert decision.steps_remaining == 5
    with pytest.raises(ReasoningPolicyError, match="not terminal"):
        decision.evidence_ref()


def test_confident_low_risk_step_completes() -> None:
    decision = evaluate_stopping(
        _policy(),
        (_step(confidence=0.90, uncertainty=0.10),),
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.COMPLETE
    assert len(decision.evidence_ref().digest) == 64


def test_high_risk_completion_requires_verification() -> None:
    policy = _policy()
    unverified = evaluate_stopping(
        policy,
        (_step(confidence=0.95, uncertainty=0.10, voi=0.40),),
        risk=ReasoningRisk.HIGH,
    )
    assert unverified.disposition is StopDisposition.CONTINUE

    verified = evaluate_stopping(
        policy,
        (
            _step(
                confidence=0.95,
                uncertainty=0.10,
                voi=0.40,
                verified=True,
            ),
        ),
        risk=ReasoningRisk.HIGH,
    )
    assert verified.disposition is StopDisposition.COMPLETE


def test_high_uncertainty_outranks_high_confidence() -> None:
    decision = evaluate_stopping(
        _policy(),
        (
            _step(
                confidence=0.99,
                uncertainty=0.90,
                verified=True,
            ),
        ),
        risk=ReasoningRisk.HIGH,
    )

    assert decision.disposition is StopDisposition.ESCALATE
    assert decision.reason == "uncertainty-exceeds-policy"


def test_high_risk_without_verification_or_information_value_abstains() -> None:
    decision = evaluate_stopping(
        _policy(),
        (
            _step(
                confidence=0.95,
                uncertainty=0.10,
                voi=0.01,
                verified=False,
            ),
        ),
        risk=ReasoningRisk.CRITICAL,
    )

    assert decision.disposition is StopDisposition.ABSTAIN
    assert "verification-required" in decision.reason


@pytest.mark.parametrize(
    ("step", "disposition"),
    (
        (
            _step(tokens=6000, cost=2.0, elapsed=20.0),
            StopDisposition.BUDGET_EXHAUSTED,
        ),
        (
            _step(tokens=1000, cost=12.0, elapsed=20.0),
            StopDisposition.BUDGET_EXHAUSTED,
        ),
        (
            _step(tokens=1000, cost=2.0, elapsed=120.0),
            StopDisposition.DEADLINE,
        ),
    ),
)
def test_token_cost_and_time_budgets_terminate(
    step: ReasoningStep,
    disposition: StopDisposition,
) -> None:
    decision = evaluate_stopping(
        _policy(),
        (step,),
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is disposition
    assert decision.steps_remaining >= 0
    assert decision.tokens_remaining >= 0
    assert decision.cost_remaining >= 0.0
    assert decision.time_remaining_s >= 0.0


def test_step_budget_requires_real_contiguous_history() -> None:
    history = tuple(
        _step(
            index,
            tokens=index * 300,
            cost=index * 0.5,
            elapsed=index * 5.0,
            progress=str(index),
        )
        for index in range(1, 7)
    )

    decision = evaluate_stopping(
        _policy(),
        history,
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.BUDGET_EXHAUSTED
    assert decision.steps_remaining == 0


def test_value_of_information_floor_stops_search() -> None:
    decision = evaluate_stopping(
        _policy(),
        (_step(voi=0.01),),
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.VALUE_EXHAUSTED


def test_no_progress_window_stops_search() -> None:
    policy = _policy(max_stall_steps=3)
    history = (
        _step(1, tokens=200, cost=0.5, elapsed=5.0, progress="1"),
        _step(2, tokens=400, cost=1.0, elapsed=10.0, progress="1"),
        _step(3, tokens=600, cost=1.5, elapsed=15.0, progress="1"),
    )

    decision = evaluate_stopping(
        policy,
        history,
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.STALLED
    assert decision.reason == "progress-digest-stalled"


def test_changed_progress_prevents_false_stall() -> None:
    policy = _policy(max_stall_steps=3)
    history = (
        _step(1, tokens=200, cost=0.5, elapsed=5.0, progress="1"),
        _step(2, tokens=400, cost=1.0, elapsed=10.0, progress="2"),
        _step(3, tokens=600, cost=1.5, elapsed=15.0, progress="3"),
    )

    decision = evaluate_stopping(
        policy,
        history,
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.CONTINUE


def test_explicit_stop_is_terminal() -> None:
    decision = evaluate_stopping(
        _policy(),
        (_step(explicit_stop=True),),
        risk=ReasoningRisk.LOW,
    )

    assert decision.disposition is StopDisposition.ABSTAIN
    assert decision.reason == "explicit-stop-requested"


def test_history_counters_must_be_monotonic_and_contiguous() -> None:
    policy = _policy()
    with pytest.raises(ReasoningPolicyError, match="contiguous"):
        evaluate_stopping(
            policy,
            (_step(2),),
            risk=ReasoningRisk.LOW,
        )

    with pytest.raises(ReasoningPolicyError, match="cumulative_tokens"):
        evaluate_stopping(
            policy,
            (
                _step(1, tokens=500),
                _step(2, tokens=400, cost=2.0, elapsed=20.0, progress="2"),
            ),
            risk=ReasoningRisk.LOW,
        )


def test_terminal_decision_identity_changes_with_policy_or_history() -> None:
    baseline = evaluate_stopping(
        _policy(),
        (_step(voi=0.01),),
        risk=ReasoningRisk.LOW,
    )
    changed_policy = evaluate_stopping(
        _policy(min_value_of_information=0.20),
        (_step(voi=0.01),),
        risk=ReasoningRisk.LOW,
    )
    changed_history = evaluate_stopping(
        _policy(),
        (_step(voi=0.02),),
        risk=ReasoningRisk.LOW,
    )

    assert baseline.decision_digest != changed_policy.decision_digest
    assert baseline.decision_digest != changed_history.decision_digest

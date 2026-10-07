"""Adversarial VOL-013 residual-budget and cognitive-control regressions."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.intelligence.strategy_registry import (
    CognitiveControlDecision,
    ReasoningPolicy,
    ReasoningPolicyError,
    ReasoningRisk,
    ReasoningStep,
    ReasoningStrategy,
    StopDisposition,
    StrategyCandidate,
    StrategyReservation,
    evaluate_cognitive_control,
    reasoning_budget_snapshot,
    select_strategy,
    verify_cognitive_control_chain,
)


def _policy(**overrides: object) -> ReasoningPolicy:
    values: dict[str, object] = {
        "policy_id": "vol013-budget-control",
        "version": 1,
        "allowed_strategies": (
            ReasoningStrategy.DIRECT,
            ReasoningStrategy.SEARCH,
            ReasoningStrategy.VERIFY,
            ReasoningStrategy.REFLECT,
            ReasoningStrategy.CRITIQUE,
            ReasoningStrategy.REPAIR,
        ),
        "default_strategy": ReasoningStrategy.DIRECT,
        "max_steps": 6,
        "max_tokens": 1_000,
        "max_cost_units": 10.0,
        "max_wall_time_s": 60.0,
        "min_value_of_information": 0.10,
        "completion_confidence": 0.90,
        "max_uncertainty": 0.60,
        "max_stall_steps": 3,
        "require_verification_for_high_risk": True,
    }
    values.update(overrides)
    return ReasoningPolicy(**values)


def _step(
    index: int,
    *,
    tokens: int,
    cost: float,
    elapsed: float,
    confidence: float = 0.50,
    uncertainty: float = 0.30,
    value: float = 0.40,
    progress: str | None = None,
    verified: bool = False,
) -> ReasoningStep:
    return ReasoningStep(
        step_index=index,
        cumulative_tokens=tokens,
        cumulative_cost_units=cost,
        elapsed_s=elapsed,
        confidence=confidence,
        uncertainty=uncertainty,
        value_of_information=value,
        progress_digest=progress or f"{index:064x}",
        verification_passed=verified,
    )


def _candidate(
    strategy: ReasoningStrategy,
    *,
    quality: float = 0.80,
    uncertainty_reduction: float = 0.30,
    tokens: int = 100,
    cost: float = 1.0,
    time_s: float = 5.0,
    verification: bool = False,
) -> StrategyCandidate:
    return StrategyCandidate(
        strategy=strategy,
        expected_quality=quality,
        expected_uncertainty_reduction=uncertainty_reduction,
        expected_cost_units=cost,
        expected_tokens=tokens,
        expected_wall_time_s=time_s,
        verification_capable=verification,
    )


def test_empty_history_budget_snapshot_matches_full_policy() -> None:
    policy = _policy()
    snapshot = reasoning_budget_snapshot(policy)
    assert snapshot.steps_used == 0
    assert snapshot.tokens_used == 0
    assert snapshot.cost_used == 0.0
    assert snapshot.time_used_s == 0.0
    assert snapshot.steps_remaining == policy.max_steps
    assert snapshot.tokens_remaining == policy.max_tokens
    assert snapshot.cost_remaining == policy.max_cost_units
    assert snapshot.time_remaining_s == policy.max_wall_time_s
    assert snapshot.exhausted is False
    assert len(snapshot.digest) == 64


def test_budget_snapshot_is_bound_to_exact_history() -> None:
    policy = _policy()
    first = reasoning_budget_snapshot(
        policy,
        (_step(1, tokens=250, cost=2.0, elapsed=8.0),),
    )
    second = reasoning_budget_snapshot(
        policy,
        (_step(1, tokens=251, cost=2.0, elapsed=8.0),),
    )
    assert first.policy_digest == second.policy_digest
    assert first.history_digest != second.history_digest
    assert first.digest != second.digest


def test_strategy_selection_uses_residual_token_budget() -> None:
    policy = _policy()
    history = (_step(1, tokens=850, cost=2.0, elapsed=8.0),)
    expensive = _candidate(
        ReasoningStrategy.DIRECT,
        quality=0.99,
        tokens=200,
    )
    bounded = _candidate(
        ReasoningStrategy.SEARCH,
        quality=0.70,
        tokens=100,
    )

    assert (
        select_strategy(
            policy,
            (expensive, bounded),
            risk=ReasoningRisk.LOW,
        ).strategy
        is ReasoningStrategy.DIRECT
    )
    assert (
        select_strategy(
            policy,
            (expensive, bounded),
            risk=ReasoningRisk.LOW,
            history=history,
        ).strategy
        is ReasoningStrategy.SEARCH
    )


@pytest.mark.parametrize(
    ("history", "candidate"),
    [
        (
            (_step(1, tokens=100, cost=9.5, elapsed=5.0),),
            _candidate(ReasoningStrategy.DIRECT, cost=0.6),
        ),
        (
            (_step(1, tokens=100, cost=1.0, elapsed=58.0),),
            _candidate(ReasoningStrategy.DIRECT, time_s=2.1),
        ),
        (
            (
                _step(1, tokens=100, cost=1.0, elapsed=5.0),
                _step(2, tokens=200, cost=2.0, elapsed=10.0),
                _step(3, tokens=300, cost=3.0, elapsed=15.0),
                _step(4, tokens=400, cost=4.0, elapsed=20.0),
                _step(5, tokens=500, cost=5.0, elapsed=25.0),
                _step(6, tokens=600, cost=6.0, elapsed=30.0),
            ),
            _candidate(ReasoningStrategy.DIRECT),
        ),
    ],
)
def test_selection_rejects_next_step_that_cannot_fit_residual_budget(
    history: tuple[ReasoningStep, ...],
    candidate: StrategyCandidate,
) -> None:
    with pytest.raises(ReasoningPolicyError, match="no admissible reasoning strategy"):
        select_strategy(
            _policy(),
            (candidate,),
            risk=ReasoningRisk.LOW,
            history=history,
        )


def test_high_risk_residual_selection_still_requires_verification() -> None:
    history = (_step(1, tokens=700, cost=4.0, elapsed=20.0),)
    direct = _candidate(
        ReasoningStrategy.DIRECT,
        quality=0.99,
        tokens=100,
        verification=False,
    )
    verifier = _candidate(
        ReasoningStrategy.VERIFY,
        quality=0.70,
        tokens=100,
        verification=True,
    )
    decision = select_strategy(
        _policy(),
        (direct, verifier),
        risk=ReasoningRisk.HIGH,
        history=history,
    )
    assert decision.strategy is ReasoningStrategy.VERIFY


def test_reflect_critique_and_repair_are_bounded_first_class_strategies() -> None:
    policy = _policy()
    rows = (
        _candidate(ReasoningStrategy.REFLECT, quality=0.70),
        _candidate(ReasoningStrategy.CRITIQUE, quality=0.80),
        _candidate(ReasoningStrategy.REPAIR, quality=0.90),
    )
    selected = select_strategy(policy, rows, risk=ReasoningRisk.LOW)
    assert selected.strategy is ReasoningStrategy.REPAIR


def test_control_decision_reserves_only_the_residual_envelope() -> None:
    policy = _policy()
    history = (_step(1, tokens=850, cost=8.0, elapsed=50.0),)
    candidate = _candidate(
        ReasoningStrategy.REPAIR,
        quality=0.95,
        tokens=120,
        cost=1.5,
        time_s=8.0,
    )
    decision = evaluate_cognitive_control(
        policy,
        (candidate,),
        history,
        risk=ReasoningRisk.LOW,
    )
    assert decision.stopping.disposition is StopDisposition.CONTINUE
    assert decision.selection is not None
    assert decision.reservation is not None
    assert decision.reservation.strategy is ReasoningStrategy.REPAIR
    assert decision.reservation.token_ceiling == 150
    assert decision.reservation.cost_ceiling == 2.0
    assert decision.reservation.time_ceiling_s == 10.0
    assert decision.reservation.expected_tokens == 120
    assert decision.reservation.expected_cost_units == 1.5
    assert decision.reservation.expected_wall_time_s == 8.0


def test_control_decision_fails_closed_when_no_strategy_fits_residual_budget() -> None:
    policy = _policy()
    history = (_step(1, tokens=950, cost=9.8, elapsed=59.0),)
    candidate = _candidate(
        ReasoningStrategy.DIRECT,
        tokens=100,
        cost=0.5,
        time_s=2.0,
    )
    decision = evaluate_cognitive_control(
        policy,
        (candidate,),
        history,
        risk=ReasoningRisk.LOW,
    )
    assert decision.stopping.disposition is StopDisposition.BUDGET_EXHAUSTED
    assert decision.stopping.reason == "no-admissible-strategy-fits-residual-budget"
    assert decision.selection is None
    assert decision.reservation is None


def test_terminal_control_decision_never_reserves_more_work() -> None:
    policy = _policy()
    history = (
        _step(
            1,
            tokens=100,
            cost=1.0,
            elapsed=5.0,
            confidence=0.95,
            uncertainty=0.10,
            verified=True,
        ),
    )
    decision = evaluate_cognitive_control(
        policy,
        (_candidate(ReasoningStrategy.DIRECT),),
        history,
        risk=ReasoningRisk.HIGH,
    )
    assert decision.stopping.disposition is StopDisposition.COMPLETE
    assert decision.selection is None
    assert decision.reservation is None


def test_control_decision_identity_is_candidate_order_independent() -> None:
    policy = _policy()
    history = (_step(1, tokens=100, cost=1.0, elapsed=5.0),)
    a = _candidate(ReasoningStrategy.DIRECT, quality=0.80)
    b = _candidate(ReasoningStrategy.SEARCH, quality=0.85)
    left = evaluate_cognitive_control(
        policy,
        (a, b),
        history,
        risk=ReasoningRisk.LOW,
    )
    right = evaluate_cognitive_control(
        policy,
        (b, a),
        history,
        risk=ReasoningRisk.LOW,
    )
    assert left.candidates_digest == right.candidates_digest
    assert left.decision_digest == right.decision_digest


def test_control_decisions_form_replay_verifiable_hash_chain() -> None:
    policy = _policy()
    candidates = (_candidate(ReasoningStrategy.SEARCH),)
    first = evaluate_cognitive_control(
        policy,
        candidates,
        (_step(1, tokens=100, cost=1.0, elapsed=5.0),),
        risk=ReasoningRisk.LOW,
        decision_index=1,
    )
    second = evaluate_cognitive_control(
        policy,
        candidates,
        (
            _step(1, tokens=100, cost=1.0, elapsed=5.0),
            _step(2, tokens=200, cost=2.0, elapsed=10.0),
        ),
        risk=ReasoningRisk.LOW,
        decision_index=2,
        previous_decision_digest=first.decision_digest,
    )
    assert verify_cognitive_control_chain((first, second))


def test_control_chain_detects_predecessor_rebinding() -> None:
    policy = _policy()
    candidates = (_candidate(ReasoningStrategy.SEARCH),)
    first = evaluate_cognitive_control(
        policy,
        candidates,
        (_step(1, tokens=100, cost=1.0, elapsed=5.0),),
        risk=ReasoningRisk.LOW,
        decision_index=1,
    )
    second = evaluate_cognitive_control(
        policy,
        candidates,
        (
            _step(1, tokens=100, cost=1.0, elapsed=5.0),
            _step(2, tokens=200, cost=2.0, elapsed=10.0),
        ),
        risk=ReasoningRisk.LOW,
        decision_index=2,
        previous_decision_digest="f" * 64,
    )
    assert not verify_cognitive_control_chain((first, second))


def test_control_chain_rejects_work_after_terminal_decision() -> None:
    policy = _policy()
    terminal = evaluate_cognitive_control(
        policy,
        (),
        (
            _step(
                1,
                tokens=100,
                cost=1.0,
                elapsed=5.0,
                confidence=0.95,
                uncertainty=0.10,
            ),
        ),
        risk=ReasoningRisk.LOW,
        decision_index=1,
    )
    after = evaluate_cognitive_control(
        policy,
        (_candidate(ReasoningStrategy.SEARCH),),
        (
            _step(1, tokens=100, cost=1.0, elapsed=5.0),
            _step(2, tokens=200, cost=2.0, elapsed=10.0),
        ),
        risk=ReasoningRisk.LOW,
        decision_index=2,
        previous_decision_digest=terminal.decision_digest,
    )
    assert terminal.stopping.disposition is StopDisposition.COMPLETE
    assert not verify_cognitive_control_chain((terminal, after))


def test_invalid_history_is_rejected_before_residual_budget_selection() -> None:
    policy = _policy()
    history = (
        _step(1, tokens=200, cost=2.0, elapsed=10.0),
        _step(2, tokens=199, cost=2.5, elapsed=12.0),
    )
    with pytest.raises(ReasoningPolicyError, match="cumulative_tokens cannot decrease"):
        select_strategy(
            policy,
            (_candidate(ReasoningStrategy.DIRECT),),
            risk=ReasoningRisk.LOW,
            history=history,
        )


def test_reservation_rejects_expected_usage_above_hard_ceiling() -> None:
    with pytest.raises(ReasoningPolicyError, match="expected tokens exceed"):
        StrategyReservation(
            strategy=ReasoningStrategy.DIRECT,
            policy_digest="a" * 64,
            history_digest="b" * 64,
            selection_digest="c" * 64,
            expected_tokens=11,
            expected_cost_units=1.0,
            expected_wall_time_s=1.0,
            token_ceiling=10,
            cost_ceiling=2.0,
            time_ceiling_s=2.0,
        )


def test_terminal_decision_cannot_smuggle_a_selection_or_reservation() -> None:
    policy = _policy()
    terminal = evaluate_cognitive_control(
        policy,
        (),
        (
            _step(
                1,
                tokens=100,
                cost=1.0,
                elapsed=5.0,
                confidence=0.95,
                uncertainty=0.10,
            ),
        ),
        risk=ReasoningRisk.LOW,
    )
    continuing = evaluate_cognitive_control(
        policy,
        (_candidate(ReasoningStrategy.DIRECT),),
        (_step(1, tokens=100, cost=1.0, elapsed=5.0),),
        risk=ReasoningRisk.LOW,
    )
    assert continuing.selection is not None
    assert continuing.reservation is not None
    with pytest.raises(
        ReasoningPolicyError,
        match="terminal decision cannot reserve",
    ):
        replace(
            terminal,
            selection=continuing.selection,
            reservation=continuing.reservation,
        )


def test_control_chain_rejects_policy_drift() -> None:
    first_policy = _policy(version=1)
    second_policy = _policy(version=2)
    candidates = (_candidate(ReasoningStrategy.SEARCH),)
    first = evaluate_cognitive_control(
        first_policy,
        candidates,
        (_step(1, tokens=100, cost=1.0, elapsed=5.0),),
        risk=ReasoningRisk.LOW,
        decision_index=1,
    )
    second = evaluate_cognitive_control(
        second_policy,
        candidates,
        (
            _step(1, tokens=100, cost=1.0, elapsed=5.0),
            _step(2, tokens=200, cost=2.0, elapsed=10.0),
        ),
        risk=ReasoningRisk.LOW,
        decision_index=2,
        previous_decision_digest=first.decision_digest,
    )
    assert not verify_cognitive_control_chain((first, second))

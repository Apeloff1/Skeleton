from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.mesh.capacity_qualification import (
    CapacityDisposition,
    CapacityQualificationDecision,
)
from skeleton.observability.budget_accounting import (
    BudgetAccountingDecision,
)
from skeleton.observability.forecasting import (
    AccountableActionReceipt,
    ActionDisposition,
    AnomalySeverity,
    ForecastMetric,
    ForecastModelKind,
    ForecastObservation,
    ForecastPolicy,
    ForecastSeries,
    ForecastingError,
    backtest_forecast,
    classify_cost_anomaly,
    cost_anomaly_identity,
    qualify_forecasting_loop,
)


NOW = 1_800_001_000.0


def _ref(source: str, digit: str) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=digit * 64,
        category="forecast_observation",
    )


def _policy(**overrides: object) -> ForecastPolicy:
    values: dict[str, object] = {
        "policy_id": "dist-06-anomaly",
        "version": 1,
        "model_kind": ForecastModelKind.LINEAR_TREND,
        "training_window": 4,
        "min_backtest_points": 4,
        "horizon_steps": 2,
        "max_mape": 0.05,
        "max_absolute_error": 1.0,
        "anomaly_relative_error": 0.10,
        "high_anomaly_relative_error": 0.25,
        "critical_anomaly_relative_error": 0.50,
        "require_action_from": AnomalySeverity.HIGH,
    }
    values.update(overrides)
    return ForecastPolicy(**values)


def _series(
    metric: ForecastMetric,
    values: list[float],
) -> ForecastSeries:
    return ForecastSeries(
        series_id=f"{metric.value}-series",
        metric=metric,
        unit=(
            "requests"
            if metric is ForecastMetric.DEMAND
            else "workers"
            if metric is ForecastMetric.CAPACITY
            else "usd"
        ),
        interval_s=60.0,
        observations=tuple(
            ForecastObservation(
                observed_at=1_800_000_000.0 + i * 60.0,
                value=value,
                evidence_refs=(
                    _ref(
                        f"fixture://{metric.value}/{i}",
                        str((i + 1) % 10),
                    ),
                ),
            )
            for i, value in enumerate(values)
        ),
    )


def _backtests(policy: ForecastPolicy):
    demand = backtest_forecast(
        series=_series(
            ForecastMetric.DEMAND,
            [100, 110, 120, 130, 140, 150, 160, 170],
        ),
        policy=policy,
    )
    capacity = backtest_forecast(
        series=_series(
            ForecastMetric.CAPACITY,
            [2, 3, 4, 5, 6, 7, 8, 9],
        ),
        policy=policy,
    )
    cost = backtest_forecast(
        series=_series(
            ForecastMetric.COST,
            [1, 2, 3, 4, 5, 6, 7, 8],
        ),
        policy=policy,
    )
    return demand, capacity, cost


def _capacity(**overrides: object) -> CapacityQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "disposition": CapacityDisposition.HEALTHY,
        "profile_digest": "1" * 64,
        "autoscaling_decision_digest": "2" * 64,
        "observation_digest": "3" * 64,
        "queue_utilization": 0.50,
        "cost_reconciliation_error_usd": 0.0,
    }
    values.update(overrides)
    return CapacityQualificationDecision(**values)


def _budget(**overrides: object) -> BudgetAccountingDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "tenant_id": "tenant-a",
        "window_id": "window-1",
        "operation_id": "operation-1",
        "reservation_id": "reservation-1",
        "reservation_digest": "4" * 64,
        "completion_digest": "5" * 64,
        "snapshot_digest": "6" * 64,
        "actual_usage_digest": "7" * 64,
        "usage_event_count": 3,
        "evidence_refs": (
            EvidenceRef(
                source="fixture://budget",
                digest="8" * 64,
                category="cost_reconciliation",
            ),
        ),
    }
    values.update(overrides)
    return BudgetAccountingDecision(**values)


def _action(
    anomaly_digest: str,
    **overrides: object,
) -> AccountableActionReceipt:
    values: dict[str, object] = {
        "action_id": "action-1",
        "owner_id": "oncall-finops",
        "workflow_ref": "workflow:cost-anomaly",
        "incident_ref": "incident:cost-spike-1",
        "anomaly_digest": anomaly_digest,
        "created_at": NOW,
        "due_at": NOW + 3600.0,
        "disposition": ActionDisposition.OPEN,
        "evidence_refs": (
            EvidenceRef(
                source="incident://cost-spike-1",
                digest="9" * 64,
                category="incident_action",
            ),
        ),
        "independent": True,
    }
    values.update(overrides)
    return AccountableActionReceipt(**values)


def test_low_cost_variance_needs_no_action() -> None:
    policy = _policy()
    _, _, cost = _backtests(policy)
    expected = cost.forecast[0].value

    decision = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=expected * 1.05,
    )

    assert decision.severity is AnomalySeverity.LOW
    assert decision.action_required is False
    assert decision.action_receipt_digest is None


def test_high_cost_anomaly_requires_exact_accountable_action() -> None:
    policy = _policy()
    _, _, cost = _backtests(policy)
    observed = cost.forecast[0].value * 1.30

    with pytest.raises(
        ForecastingError,
        match="requires AccountableActionReceipt",
    ):
        classify_cost_anomaly(
            cost_backtest=cost,
            policy=policy,
            observed_cost=observed,
        )

    identity = cost_anomaly_identity(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
    )
    action = _action(identity)
    decision = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
        action_receipt=action,
    )

    assert decision.severity is AnomalySeverity.HIGH
    assert decision.action_required is True
    assert decision.action_receipt_digest == action.receipt_digest


def test_critical_anomaly_is_classified_deterministically() -> None:
    policy = _policy()
    _, _, cost = _backtests(policy)
    observed = cost.forecast[0].value * 2.0
    identity = cost_anomaly_identity(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
    )

    decision = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
        action_receipt=_action(identity),
    )

    assert decision.severity is AnomalySeverity.CRITICAL


def test_action_receipt_must_bind_exact_anomaly_identity() -> None:
    policy = _policy()
    _, _, cost = _backtests(policy)
    observed = cost.forecast[0].value * 1.30

    with pytest.raises(
        ForecastingError,
        match="anomaly digest mismatch",
    ):
        classify_cost_anomaly(
            cost_backtest=cost,
            policy=policy,
            observed_cost=observed,
            action_receipt=_action("0" * 64),
        )


def test_non_actionable_anomaly_rejects_spurious_action_receipt() -> None:
    policy = _policy()
    _, _, cost = _backtests(policy)
    observed = cost.forecast[0].value
    identity = cost_anomaly_identity(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
    )

    with pytest.raises(
        ForecastingError,
        match="non-actionable",
    ):
        classify_cost_anomaly(
            cost_backtest=cost,
            policy=policy,
            observed_cost=observed,
            action_receipt=_action(identity),
        )


def test_terminal_dist06_qualification_binds_all_authorities() -> None:
    policy = _policy()
    demand, capacity_forecast, cost = _backtests(policy)
    observed = cost.forecast[0].value * 1.30
    identity = cost_anomaly_identity(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
    )
    anomaly = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=observed,
        action_receipt=_action(identity),
    )

    decision = qualify_forecasting_loop(
        capacity_decision=_capacity(),
        budget_decision=_budget(),
        demand_backtest=demand,
        capacity_backtest=capacity_forecast,
        cost_backtest=cost,
        anomaly_decision=anomaly,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "forecast_anomaly_qualification"
    assert evidence.digest == decision.decision_digest


def test_rejected_capacity_or_budget_blocks_terminal_qualification() -> None:
    policy = _policy()
    demand, capacity_forecast, cost = _backtests(policy)
    anomaly = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=cost.forecast[0].value,
    )

    capacity_rejected = qualify_forecasting_loop(
        capacity_decision=_capacity(
            accepted=False,
            reasons=("capacity-regressed",),
        ),
        budget_decision=_budget(),
        demand_backtest=demand,
        capacity_backtest=capacity_forecast,
        cost_backtest=cost,
        anomaly_decision=anomaly,
    )
    assert capacity_rejected.accepted is False
    assert "capacity-qualification-rejected" in capacity_rejected.reasons

    budget_rejected = qualify_forecasting_loop(
        capacity_decision=_capacity(),
        budget_decision=_budget(
            accepted=False,
            reasons=("budget-regressed",),
        ),
        demand_backtest=demand,
        capacity_backtest=capacity_forecast,
        cost_backtest=cost,
        anomaly_decision=anomaly,
    )
    assert budget_rejected.accepted is False
    assert "budget-accounting-rejected" in budget_rejected.reasons


def test_policy_and_cost_backtest_substitution_block() -> None:
    policy = _policy()
    demand, capacity_forecast, cost = _backtests(policy)
    anomaly = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=cost.forecast[0].value,
    )

    other_policy = _policy(version=2)
    other_cost = backtest_forecast(
        series=_series(
            ForecastMetric.COST,
            [1, 2, 3, 4, 5, 6, 7, 8],
        ),
        policy=other_policy,
    )
    decision = qualify_forecasting_loop(
        capacity_decision=_capacity(),
        budget_decision=_budget(),
        demand_backtest=demand,
        capacity_backtest=capacity_forecast,
        cost_backtest=other_cost,
        anomaly_decision=anomaly,
    )

    assert decision.accepted is False
    assert "forecast-policy-digest-mismatch" in decision.reasons
    assert "anomaly-cost-backtest-digest-mismatch" in decision.reasons


def test_rejected_dist06_decision_cannot_be_promotion_evidence() -> None:
    policy = _policy()
    demand, capacity_forecast, cost = _backtests(policy)
    anomaly = classify_cost_anomaly(
        cost_backtest=cost,
        policy=policy,
        observed_cost=cost.forecast[0].value,
    )
    decision = qualify_forecasting_loop(
        capacity_decision=_capacity(
            accepted=False,
            reasons=("capacity-regressed",),
        ),
        budget_decision=_budget(),
        demand_backtest=demand,
        capacity_backtest=capacity_forecast,
        cost_backtest=cost,
        anomaly_decision=anomaly,
    )

    assert decision.accepted is False
    with pytest.raises(
        ForecastingError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()

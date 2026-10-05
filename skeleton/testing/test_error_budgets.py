from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.error_budget_policy import (
    BudgetDecision,
    BurnRate,
    ErrorBudget,
    ErrorBudgetPolicyError,
    calculate_burn_rate,
    calculate_error_budget,
    evaluate_budget_decision,
)
from skeleton.ai.runtime.observability.slo import SLI, SLO, SLOWindow


def _slo(target: float = 0.99) -> SLO:
    return SLO(
        slo_id="assistant.availability",
        service_id="assistant",
        sli_name="successful_requests",
        target=target,
        window=SLOWindow(window_id="w1", start_ns=100, end_ns=1_000),
    )


def _sli(*, good: int, total: int, excluded: int = 0) -> SLI:
    return SLI(
        observation_id=f"obs-{good}-{total}-{excluded}",
        slo_id="assistant.availability",
        good_events=good,
        total_events=total,
        excluded_events=excluded,
        observed_start_ns=100,
        observed_end_ns=900,
    )


def test_error_budget_uses_authoritative_eligible_population() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=98, total=100, excluded=1),
    )

    assert budget.eligible_events == 99
    assert budget.bad_events == 1
    assert budget.allowed_bad_ppm == 10_000
    assert budget.observed_bad_ppm == 10_102
    assert budget.remaining_bad_ppm == 0
    assert budget.exhausted is True
    assert len(budget.digest) == 64


def test_error_budget_is_conservative_at_fractional_ppm_boundaries() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.999),
        sli=_sli(good=999, total=1_000),
    )

    assert budget.allowed_bad_ppm == 1_000
    assert budget.observed_bad_ppm == 1_000
    assert budget.exhausted is False


def test_burn_rate_is_scaled_deterministically() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=98, total=100),
    )
    rate = calculate_burn_rate(budget)

    assert rate.unbounded is False
    assert rate.burn_multiple_ppm == 2_000_000
    assert rate.budget_digest == budget.digest
    assert len(rate.digest) == 64


def test_zero_error_allowance_uses_explicit_unbounded_state() -> None:
    clean = calculate_error_budget(
        slo=_slo(1.0),
        sli=_sli(good=100, total=100),
    )
    clean_rate = calculate_burn_rate(clean)
    assert clean_rate.unbounded is False
    assert clean_rate.burn_multiple_ppm == 0

    bad = calculate_error_budget(
        slo=_slo(1.0),
        sli=_sli(good=99, total=100),
    )
    bad_rate = calculate_burn_rate(bad)
    assert bad_rate.unbounded is True
    assert bad_rate.burn_multiple_ppm is None


def test_budget_decision_never_waives_failed_safety_gate() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=100, total=100),
    )
    rate = calculate_burn_rate(budget)

    decision = evaluate_budget_decision(
        budget=budget,
        burn_rate=rate,
        safety_gate_passed=False,
        reliability_gate_passed=True,
    )

    assert decision.status == "blocked"
    assert decision.blocking_reasons == ("safety-gate-failed",)
    assert decision.safety_override is False
    assert decision.reliability_override is False
    assert decision.promotion_authority is False


def test_budget_decision_never_waives_failed_reliability_gate() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=100, total=100),
    )
    rate = calculate_burn_rate(budget)

    decision = evaluate_budget_decision(
        budget=budget,
        burn_rate=rate,
        safety_gate_passed=True,
        reliability_gate_passed=False,
    )

    assert decision.status == "blocked"
    assert decision.blocking_reasons == ("reliability-gate-failed",)


def test_budget_exhaustion_is_reported_even_when_independent_gates_pass() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=95, total=100),
    )
    rate = calculate_burn_rate(budget)

    decision = evaluate_budget_decision(
        budget=budget,
        burn_rate=rate,
        safety_gate_passed=True,
        reliability_gate_passed=True,
    )

    assert decision.status == "exhausted"
    assert decision.blocking_reasons == ("error-budget-exhausted",)


def test_healthy_budget_is_evidence_only() -> None:
    budget = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=100, total=100),
    )
    rate = calculate_burn_rate(budget)
    decision = evaluate_budget_decision(
        budget=budget,
        burn_rate=rate,
        safety_gate_passed=True,
        reliability_gate_passed=True,
    )

    assert decision.status == "healthy"
    assert decision.blocking_reasons == ()
    assert decision.promotion_authority is False
    assert not hasattr(decision, "release_allowed")


def test_budget_decision_rejects_burn_rate_from_different_budget() -> None:
    first = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=100, total=100),
    )
    second = calculate_error_budget(
        slo=_slo(0.99),
        sli=_sli(good=98, total=100),
    )

    with pytest.raises(ErrorBudgetPolicyError, match="different budget"):
        evaluate_budget_decision(
            budget=first,
            burn_rate=calculate_burn_rate(second),
            safety_gate_passed=True,
            reliability_gate_passed=True,
        )


def test_error_budget_contract_rejects_forged_remaining_state() -> None:
    with pytest.raises(ErrorBudgetPolicyError, match="remaining budget"):
        ErrorBudget(
            slo_digest="a" * 64,
            sli_digest="b" * 64,
            eligible_events=100,
            bad_events=1,
            allowed_bad_ppm=10_000,
            observed_bad_ppm=10_000,
            remaining_bad_ppm=9_999,
            exhausted=False,
        )


def test_burn_rate_rejects_ambiguous_unbounded_representation() -> None:
    with pytest.raises(ErrorBudgetPolicyError, match="null multiple"):
        BurnRate(
            budget_digest="a" * 64,
            burn_multiple_ppm=1,
            unbounded=True,
        )


def test_budget_decision_cannot_claim_override_or_authority() -> None:
    common = dict(
        budget_digest="a" * 64,
        burn_rate_digest="b" * 64,
        status="healthy",
        blocking_reasons=(),
        safety_gate_passed=True,
        reliability_gate_passed=True,
    )

    with pytest.raises(ErrorBudgetPolicyError, match="override safety"):
        BudgetDecision(**common, safety_override=True)
    with pytest.raises(ErrorBudgetPolicyError, match="override reliability"):
        BudgetDecision(**common, reliability_override=True)
    with pytest.raises(ErrorBudgetPolicyError, match="promotion authority"):
        BudgetDecision(**common, promotion_authority=True)


def test_budget_decision_rejects_forged_status_or_reasons() -> None:
    common = dict(
        budget_digest="a" * 64,
        burn_rate_digest="b" * 64,
        safety_gate_passed=True,
        reliability_gate_passed=True,
        budget_exhausted=False,
    )

    with pytest.raises(
        ErrorBudgetPolicyError,
        match="status does not match",
    ):
        BudgetDecision(
            **common,
            status="exhausted",
            blocking_reasons=(),
        )

    with pytest.raises(
        ErrorBudgetPolicyError,
        match="blocking reasons do not match",
    ):
        BudgetDecision(
            **common,
            status="healthy",
            blocking_reasons=("error-budget-exhausted",),
        )


def test_budget_decision_rejects_hidden_failed_gate() -> None:
    with pytest.raises(
        ErrorBudgetPolicyError,
        match="blocking reasons do not match",
    ):
        BudgetDecision(
            budget_digest="a" * 64,
            burn_rate_digest="b" * 64,
            status="blocked",
            blocking_reasons=(),
            safety_gate_passed=False,
            reliability_gate_passed=True,
            budget_exhausted=False,
        )

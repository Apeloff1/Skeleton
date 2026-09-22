from __future__ import annotations

import math

import pytest

from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    AdmissionStatus,
    ResourceBudget,
    RuntimePressure,
    UsageEstimate,
    evaluate_admission,
    require_admission,
)


def _request(
    *,
    budget: ResourceBudget | None = None,
    estimate: UsageEstimate | None = None,
    pressure: RuntimePressure | None = None,
    deadline: float | None = None,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id="op-1",
        tenant_id="tenant-1",
        capability="model-inference",
        budget=budget or ResourceBudget(),
        estimate=estimate or UsageEstimate(input_tokens=100, output_tokens=50),
        pressure=pressure or RuntimePressure(),
        deadline_monotonic=deadline,
    )


def test_within_budget_is_admitted_with_deterministic_receipt() -> None:
    first = require_admission(_request(), now_monotonic=10.0)
    second = require_admission(_request(), now_monotonic=10.0)

    assert first.status is AdmissionStatus.ADMIT
    assert first.admitted is True
    assert first.reason_code == "within_budget"
    assert first.decision_id == second.decision_id
    assert first.decision_id.startswith("adm-")
    assert first.remaining["input_tokens"] == 199_900


@pytest.mark.parametrize(
    ("estimate", "reason"),
    [
        (UsageEstimate(input_tokens=200_001), "input_token_budget_exceeded"),
        (UsageEstimate(output_tokens=16_385), "output_token_budget_exceeded"),
        (UsageEstimate(cost_usd=10.01), "cost_budget_exceeded"),
        (UsageEstimate(wall_seconds=120.01), "wall_time_budget_exceeded"),
        (UsageEstimate(provider_attempts=4), "provider_attempt_budget_exceeded"),
        (UsageEstimate(tool_calls=33), "tool_call_budget_exceeded"),
        (
            UsageEstimate(artifact_bytes=100 * 1024 * 1024 + 1),
            "artifact_budget_exceeded",
        ),
    ],
)
def test_resource_budget_excess_rejects_before_allocation(
    estimate: UsageEstimate,
    reason: str,
) -> None:
    decision = evaluate_admission(_request(estimate=estimate))

    assert decision.status is AdmissionStatus.REJECT
    assert decision.reason_code == reason
    with pytest.raises(AdmissionError, match=reason):
        require_admission(_request(estimate=estimate))


def test_concurrency_saturation_defers_instead_of_overloading() -> None:
    decision = evaluate_admission(
        _request(pressure=RuntimePressure(active_operations=32))
    )

    assert decision.status is AdmissionStatus.DEFER
    assert decision.reason_code == "concurrency_saturated"


def test_queue_saturation_rejects_new_work() -> None:
    decision = evaluate_admission(
        _request(pressure=RuntimePressure(queue_depth=1_000))
    )

    assert decision.status is AdmissionStatus.REJECT
    assert decision.reason_code == "queue_saturated"


def test_expired_or_impossible_deadline_rejects() -> None:
    expired = evaluate_admission(_request(deadline=10.0), now_monotonic=10.0)
    impossible = evaluate_admission(
        _request(
            deadline=15.0,
            estimate=UsageEstimate(wall_seconds=6.0),
        ),
        now_monotonic=10.0,
    )

    assert expired.reason_code == "deadline_expired"
    assert impossible.reason_code == "estimate_exceeds_deadline"


@pytest.mark.parametrize(
    "budget",
    [
        lambda: ResourceBudget(max_input_tokens=-1),
        lambda: ResourceBudget(max_cost_usd=math.nan),
        lambda: ResourceBudget(max_wall_seconds=0),
        lambda: ResourceBudget(max_provider_attempts=0),
        lambda: ResourceBudget(max_concurrency=0),
    ],
)
def test_invalid_budgets_fail_closed(budget) -> None:
    with pytest.raises(AdmissionError):
        budget()


@pytest.mark.parametrize(
    "estimate",
    [
        lambda: UsageEstimate(input_tokens=-1),
        lambda: UsageEstimate(cost_usd=math.inf),
        lambda: UsageEstimate(provider_attempts=0),
    ],
)
def test_invalid_estimates_fail_closed(estimate) -> None:
    with pytest.raises(AdmissionError):
        estimate()


def test_invalid_request_identity_and_priority_fail_closed() -> None:
    with pytest.raises(AdmissionError, match="operation_id"):
        AdmissionRequest(
            operation_id="",
            tenant_id="tenant",
            capability="model-inference",
            budget=ResourceBudget(),
            estimate=UsageEstimate(),
        )

    with pytest.raises(AdmissionError, match="priority"):
        AdmissionRequest(
            operation_id="op",
            tenant_id="tenant",
            capability="model-inference",
            budget=ResourceBudget(),
            estimate=UsageEstimate(),
            priority=101,
        )


def test_receipt_exposes_budget_state_but_not_payload() -> None:
    decision = require_admission(_request())

    payload = decision.as_dict()
    assert payload["operation_id"] == "op-1"
    assert payload["tenant_id"] == "tenant-1"
    assert "prompt" not in str(payload)
    assert "secret" not in str(payload)

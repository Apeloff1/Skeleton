from __future__ import annotations

import hashlib

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.distributed.mesh.capacity_qualification import (
    CapacityDisposition,
    CapacityQualificationDecision,
)
from skeleton.reliability.retry_admission import (
    AdmissionDecision,
    AdmissionKind,
    AdmissionRequest,
    PriorOutcome,
    RetryAdmissionError,
    RetryBudgetPolicy,
    RetryBudgetSnapshot,
    ServiceLevelState,
    consume_admission,
    evaluate_admission,
    initial_retry_budget,
)


def policy(**overrides) -> RetryBudgetPolicy:
    values = {
        "budget_id": "connector-default",
        "max_retries_per_operation": 2,
        "max_retry_tokens": 5,
        "max_retry_fraction": 0.5,
        "min_error_budget_remaining": 0.20,
        "max_error_budget_burn_rate": 2.0,
        "allow_retry_when_degraded": False,
        "allow_new_when_saturated": False,
    }
    values.update(overrides)
    return RetryBudgetPolicy(**values)


def slo(**overrides) -> ServiceLevelState:
    values = {
        "service_id": "connector.github",
        "window_id": "window-1",
        "error_budget_remaining": 0.80,
        "error_budget_burn_rate": 0.5,
        "observed_at": 100.0,
        "max_age_s": 60.0,
    }
    values.update(overrides)
    return ServiceLevelState(**values)


def capacity(
    disposition: CapacityDisposition = CapacityDisposition.HEALTHY,
    *,
    accepted: bool = True,
) -> CapacityQualificationDecision:
    reasons = () if accepted else ("fixture-rejected",)
    return CapacityQualificationDecision(
        accepted=accepted,
        reasons=reasons,
        disposition=disposition,
        profile_digest="1" * 64,
        autoscaling_decision_digest="2" * 64,
        observation_digest="3" * 64,
        queue_utilization=0.2,
        cost_reconciliation_error_usd=0.0,
    )


def new_request(service_id: str = "connector.github") -> AdmissionRequest:
    return AdmissionRequest(
        operation_id="op-1",
        service_id=service_id,
        kind=AdmissionKind.NEW,
        attempt=1,
        prior_outcome=PriorOutcome.NOT_ATTEMPTED,
        external_effect=False,
    )


def retry_request(
    *,
    attempt: int = 2,
    prior_outcome: PriorOutcome = PriorOutcome.KNOWN_FAILURE,
    external_effect: bool = False,
    idempotency: str | None = None,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id="op-1",
        service_id="connector.github",
        kind=AdmissionKind.RETRY,
        attempt=attempt,
        prior_outcome=prior_outcome,
        external_effect=external_effect,
        idempotency_key_digest=idempotency,
    )


def initial(p: RetryBudgetPolicy | None = None) -> RetryBudgetSnapshot:
    selected = p or policy()
    return initial_retry_budget(
        policy=selected,
        service_id="connector.github",
        window_id="window-1",
    )


def test_healthy_new_request_is_admitted_and_accounted() -> None:
    p = policy()
    before = initial(p)
    request = new_request()

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=before,
        capacity=capacity(),
        request=request,
        observed_at=110.0,
    )
    after = consume_admission(
        snapshot=before,
        request=request,
        decision=decision,
    )

    assert decision.admitted is True
    assert decision.reasons == ()
    assert after.admitted_requests == 1
    assert after.admitted_retries == 0
    assert after.retry_tokens_used == 0
    assert after.sequence == 1


def test_known_failure_retry_consumes_one_shared_retry_token() -> None:
    p = policy()
    start = initial(p)
    first_request = new_request()
    first_decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=start,
        capacity=capacity(),
        request=first_request,
        observed_at=110.0,
    )
    after_first = consume_admission(
        snapshot=start,
        request=first_request,
        decision=first_decision,
    )
    retry = retry_request()

    retry_decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=after_first,
        capacity=capacity(),
        request=retry,
        observed_at=111.0,
    )
    after_retry = consume_admission(
        snapshot=after_first,
        request=retry,
        decision=retry_decision,
    )

    assert retry_decision.admitted is True
    assert retry_decision.projected_retry_fraction == 0.5
    assert after_retry.admitted_requests == 2
    assert after_retry.admitted_retries == 1
    assert after_retry.retry_tokens_used == 1


def test_unknown_outcome_requires_reconciliation_before_retry() -> None:
    p = policy()
    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=RetryBudgetSnapshot(
            policy_digest=p.policy_digest,
            service_id="connector.github",
            window_id="window-1",
            admitted_requests=2,
            admitted_retries=0,
            retry_tokens_used=0,
        ),
        capacity=capacity(),
        request=retry_request(prior_outcome=PriorOutcome.UNKNOWN),
        observed_at=110.0,
    )

    assert decision.admitted is False
    assert "prior-outcome-unknown-reconciliation-required" in decision.reasons


def test_external_effect_retry_requires_idempotency_key() -> None:
    p = policy(max_retry_fraction=1.0)
    snapshot = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=1,
        admitted_retries=0,
        retry_tokens_used=0,
    )

    denied = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(),
        request=retry_request(external_effect=True),
        observed_at=110.0,
    )
    allowed = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(),
        request=retry_request(
            external_effect=True,
            idempotency="a" * 64,
        ),
        observed_at=110.0,
    )

    assert "external-effect-retry-requires-idempotency" in denied.reasons
    assert allowed.admitted is True


def test_per_operation_retry_limit_is_enforced() -> None:
    p = policy(max_retries_per_operation=2, max_retry_fraction=1.0)
    snapshot = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=3,
        admitted_retries=1,
        retry_tokens_used=1,
    )

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(),
        request=retry_request(attempt=4),
        observed_at=110.0,
    )

    assert decision.admitted is False
    assert "operation-retry-limit-exceeded" in decision.reasons


def test_retry_token_budget_is_shared_across_operations_and_connectors() -> None:
    p = policy(max_retry_tokens=2, max_retry_fraction=1.0)
    exhausted = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=4,
        admitted_retries=2,
        retry_tokens_used=2,
    )

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=exhausted,
        capacity=capacity(),
        request=retry_request(),
        observed_at=110.0,
    )

    assert "retry-token-budget-exhausted" in decision.reasons


def test_retry_fraction_budget_prevents_retry_storms() -> None:
    p = policy(max_retry_fraction=0.25)
    snapshot = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=2,
        admitted_retries=0,
        retry_tokens_used=0,
    )

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(),
        request=retry_request(),
        observed_at=110.0,
    )

    assert decision.projected_retry_fraction == pytest.approx(1 / 3)
    assert "retry-fraction-budget-exceeded" in decision.reasons


@pytest.mark.parametrize(
    "kind,expected",
    [
        (AdmissionKind.NEW, "error-budget-admission-closed"),
        (AdmissionKind.RETRY, "error-budget-retry-closed"),
    ],
)
def test_error_budget_closes_admission(kind: AdmissionKind, expected: str) -> None:
    p = policy()
    request = new_request() if kind is AdmissionKind.NEW else retry_request()
    snapshot = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=2,
        admitted_retries=0,
        retry_tokens_used=0,
    )

    decision = evaluate_admission(
        policy=p,
        slo=slo(error_budget_remaining=0.19),
        retry_budget=snapshot,
        capacity=capacity(),
        request=request,
        observed_at=110.0,
    )

    assert decision.admitted is False
    assert expected in decision.reasons


def test_error_budget_burn_rate_closes_admission() -> None:
    p = policy(max_error_budget_burn_rate=2.0)

    decision = evaluate_admission(
        policy=p,
        slo=slo(error_budget_burn_rate=2.01),
        retry_budget=initial(p),
        capacity=capacity(),
        request=new_request(),
        observed_at=110.0,
    )

    assert "error-budget-burn-rate-exceeded" in decision.reasons


def test_stale_slo_evidence_fails_closed() -> None:
    p = policy()

    decision = evaluate_admission(
        policy=p,
        slo=slo(observed_at=10.0, max_age_s=20.0),
        retry_budget=initial(p),
        capacity=capacity(),
        request=new_request(),
        observed_at=31.0,
    )

    assert "slo-observation-stale" in decision.reasons


def test_rejected_capacity_evidence_fails_closed() -> None:
    p = policy()

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=initial(p),
        capacity=capacity(accepted=False),
        request=new_request(),
        observed_at=110.0,
    )

    assert "capacity-qualification-rejected" in decision.reasons


def test_degraded_capacity_denies_retry_by_default() -> None:
    p = policy(max_retry_fraction=1.0)
    snapshot = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=1,
        admitted_retries=0,
        retry_tokens_used=0,
    )

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(CapacityDisposition.DEGRADED),
        request=retry_request(),
        observed_at=110.0,
    )

    assert "capacity-degraded-retry-denied" in decision.reasons


def test_degraded_retry_can_be_explicitly_enabled() -> None:
    p = policy(allow_retry_when_degraded=True, max_retry_fraction=1.0)
    snapshot = RetryBudgetSnapshot(
        policy_digest=p.policy_digest,
        service_id="connector.github",
        window_id="window-1",
        admitted_requests=1,
        admitted_retries=0,
        retry_tokens_used=0,
    )

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(CapacityDisposition.DEGRADED),
        request=retry_request(),
        observed_at=110.0,
    )

    assert decision.admitted is True


def test_saturation_denies_retry_and_new_work_by_default() -> None:
    p = policy(max_retry_fraction=1.0)
    new_decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=initial(p),
        capacity=capacity(CapacityDisposition.SATURATED),
        request=new_request(),
        observed_at=110.0,
    )
    retry_decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=RetryBudgetSnapshot(
            policy_digest=p.policy_digest,
            service_id="connector.github",
            window_id="window-1",
            admitted_requests=1,
            admitted_retries=0,
            retry_tokens_used=0,
        ),
        capacity=capacity(CapacityDisposition.SATURATED),
        request=retry_request(),
        observed_at=110.0,
    )

    assert "capacity-saturated-admission-denied" in new_decision.reasons
    assert "capacity-saturated-retry-denied" in retry_decision.reasons


def test_saturated_new_work_requires_explicit_policy_opt_in() -> None:
    p = policy(allow_new_when_saturated=True)

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=initial(p),
        capacity=capacity(CapacityDisposition.SATURATED),
        request=new_request(),
        observed_at=110.0,
    )

    assert decision.admitted is True


def test_service_and_window_identity_are_bound() -> None:
    p = policy()
    wrong_service = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=initial(p),
        capacity=capacity(),
        request=new_request("connector.slack"),
        observed_at=110.0,
    )
    wrong_window = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=RetryBudgetSnapshot(
            policy_digest=p.policy_digest,
            service_id="connector.github",
            window_id="window-old",
            admitted_requests=0,
            admitted_retries=0,
            retry_tokens_used=0,
        ),
        capacity=capacity(),
        request=new_request(),
        observed_at=110.0,
    )

    assert "request-slo-service-mismatch" in wrong_service.reasons
    assert "retry-slo-window-mismatch" in wrong_window.reasons


def test_retry_policy_digest_mismatch_fails_closed() -> None:
    p = policy()
    other = policy(max_retry_tokens=9)
    snapshot = initial(other)

    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=snapshot,
        capacity=capacity(),
        request=new_request(),
        observed_at=110.0,
    )

    assert "retry-policy-digest-mismatch" in decision.reasons


def test_consumption_rejects_stale_decision() -> None:
    p = policy()
    before = initial(p)
    request = new_request()
    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=before,
        capacity=capacity(),
        request=request,
        observed_at=110.0,
    )
    changed = RetryBudgetSnapshot(
        policy_digest=before.policy_digest,
        service_id=before.service_id,
        window_id=before.window_id,
        admitted_requests=1,
        admitted_retries=0,
        retry_tokens_used=0,
        sequence=1,
    )

    with pytest.raises(RetryAdmissionError, match="stale"):
        consume_admission(
            snapshot=changed,
            request=request,
            decision=decision,
        )


def test_rejected_admission_cannot_consume_budget() -> None:
    p = policy()
    request = new_request()
    decision = evaluate_admission(
        policy=p,
        slo=slo(error_budget_remaining=0.0),
        retry_budget=initial(p),
        capacity=capacity(),
        request=request,
        observed_at=110.0,
    )

    with pytest.raises(RetryAdmissionError, match="rejected admission"):
        consume_admission(
            snapshot=initial(p),
            request=request,
            decision=decision,
        )


def test_policy_slo_snapshot_request_and_decision_use_canonical_bytes() -> None:
    p = policy()
    s = slo()
    snapshot = initial(p)
    request = new_request()
    decision = evaluate_admission(
        policy=p,
        slo=s,
        retry_budget=snapshot,
        capacity=capacity(),
        request=request,
        observed_at=110.0,
    )

    assert p.policy_digest == hashlib.sha256(
        canonical_json_bytes(p.payload())
    ).hexdigest()
    assert s.digest == hashlib.sha256(canonical_json_bytes(s.payload())).hexdigest()
    assert snapshot.digest == hashlib.sha256(
        canonical_json_bytes(snapshot.payload())
    ).hexdigest()
    assert request.digest == hashlib.sha256(
        canonical_json_bytes(request.payload())
    ).hexdigest()
    assert decision.decision_digest == hashlib.sha256(
        canonical_json_bytes(decision.payload())
    ).hexdigest()


def test_admission_decision_cannot_be_forged_into_execution_authority() -> None:
    p = policy()
    decision = evaluate_admission(
        policy=p,
        slo=slo(),
        retry_budget=initial(p),
        capacity=capacity(),
        request=new_request(),
        observed_at=110.0,
    )

    with pytest.raises(RetryAdmissionError, match="scope escalation"):
        AdmissionDecision(
            admitted=decision.admitted,
            reasons=decision.reasons,
            request_digest=decision.request_digest,
            policy_digest=decision.policy_digest,
            slo_digest=decision.slo_digest,
            retry_snapshot_digest=decision.retry_snapshot_digest,
            capacity_decision_digest=decision.capacity_decision_digest,
            capacity_disposition=decision.capacity_disposition,
            projected_retry_fraction=decision.projected_retry_fraction,
            retry_tokens_remaining=decision.retry_tokens_remaining,
            authority_scope="execute-request",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_retries_per_operation": 0},
        {"max_retry_tokens": 0},
        {"max_retry_fraction": 1.1},
        {"min_error_budget_remaining": -0.1},
        {"max_error_budget_burn_rate": -1.0},
    ],
)
def test_invalid_retry_policy_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(RetryAdmissionError):
        policy(**kwargs)


def test_reliability_retry_admission_source_and_ai_mirror_are_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/reliability/retry_admission.py"
    mirror = root / "skeleton/ai/runtime/reliability/retry_admission.py"
    assert source.read_bytes() == mirror.read_bytes()

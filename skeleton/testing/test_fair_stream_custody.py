"""Simulated source-backed authenticated fair-stream custody tests."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.ai.model_runtime.fair_stream_custody import (
    AuthenticatedFairStreamCustody, sign_execution_result,
)
from skeleton.ai.model_runtime.fair_stream_queue import (
    MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase

C = b"c" * 32
E = b"e" * 32
SESSION = "a" * 32
RESULT = "b" * 64


def make():
    return AuthenticatedFairStreamCustody(
        custody_key=C, execution_key=E, session_id=SESSION,
    )


def request():
    return StreamRequest("request", "tenant", InferencePhase.PREFILL, 50, 4)


def budget():
    return MeasuredStreamBudget(4096, 1024, 20, 2, 0, False, "simulated")


def test_checkpoint_restore_requires_generation_and_digest():
    owner = make()
    _, state = owner.transition(expected_generation=0, action="submit", request=request())
    restored = AuthenticatedFairStreamCustody.restore(
        state, custody_key=C, execution_key=E, expected_generation=1,
        expected_digest=state["digest"],
    )
    assert restored.export() == state
    with pytest.raises(ValueError, match="generation"):
        AuthenticatedFairStreamCustody.restore(
            state, custody_key=C, execution_key=E, expected_generation=0,
            expected_digest=state["digest"],
        )


def test_pending_crash_restore_fences_reexecution():
    owner = make()
    owner.transition(expected_generation=0, action="submit", request=request())
    plan, state = owner.transition(expected_generation=1, action="plan", budget=budget())
    recovered = AuthenticatedFairStreamCustody.restore(
        state, custody_key=C, execution_key=E, expected_generation=2,
        expected_digest=state["digest"],
    )
    assert recovered.pending_ids == (plan.leases[0].lease_id,)
    with pytest.raises(ValueError, match="pending"):
        recovered.transition(expected_generation=2, action="plan", budget=budget())


def test_signed_execution_receipt_is_bound_to_pending_lease():
    owner = make()
    owner.transition(expected_generation=0, action="submit", request=request())
    plan, state = owner.transition(expected_generation=1, action="plan", budget=budget())
    receipt = sign_execution_result(
        execution_key=E, session_id=SESSION, generation=2,
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=plan.leases[0].lease_id, consumed_tokens=20,
        result_digest=RESULT,
    )
    _, next_state = owner.transition(
        expected_generation=2, action="acknowledge", receipt=receipt,
    )
    assert next_state["checkpoint"]["requests"][0]["remaining_tokens"] == 30
    assert not owner.pending_ids
    with pytest.raises(ValueError, match="stale"):
        owner.transition(expected_generation=3, action="acknowledge", receipt=receipt)


def test_untrusted_receipt_and_tampered_checkpoint_fail_closed():
    owner = make()
    owner.transition(expected_generation=0, action="submit", request=request())
    plan, state = owner.transition(expected_generation=1, action="plan", budget=budget())
    forged = sign_execution_result(
        execution_key=b"x" * 32, session_id=SESSION, generation=2,
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=plan.leases[0].lease_id, consumed_tokens=1,
        result_digest=RESULT,
    )
    with pytest.raises(ValueError, match="unauthenticated"):
        owner.transition(expected_generation=2, action="acknowledge", receipt=forged)
    assert owner.export() == state
    tampered = deepcopy(state)
    tampered["checkpoint"]["requests"][0]["remaining_tokens"] = 100
    with pytest.raises(ValueError, match="authentication"):
        AuthenticatedFairStreamCustody.restore(
            tampered, custody_key=C, execution_key=E,
            expected_generation=2, expected_digest=state["digest"],
        )


def test_duplicate_submission_does_not_mutate_generation():
    owner = make()
    owner.transition(expected_generation=0, action="submit", request=request())
    state = owner.export()
    with pytest.raises(ValueError, match="duplicate"):
        owner.transition(expected_generation=1, action="submit", request=request())
    assert owner.export() == state


def test_thermal_hold_never_issues_lease():
    owner = make()
    owner.transition(expected_generation=0, action="submit", request=request())
    hold = MeasuredStreamBudget(4096, 1024, 20, 2, 0, True, "simulated")
    plan, _ = owner.transition(expected_generation=1, action="plan", budget=hold)
    assert not plan.leases


def test_independent_keys_required():
    with pytest.raises(ValueError, match="independent"):
        AuthenticatedFairStreamCustody(
            custody_key=C, execution_key=C, session_id=SESSION,
        )

def test_constructor_detaches_caller_owned_scheduler():
    from skeleton.ai.model_runtime.fair_stream_queue import FairStreamScheduler

    scheduler = FairStreamScheduler()
    scheduler.submit(request())
    owner = AuthenticatedFairStreamCustody(
        custody_key=C, execution_key=E, session_id=SESSION, scheduler=scheduler,
    )
    before = owner.export()
    scheduler.cancel("request")
    assert owner.export() == before


def test_final_envelope_budget_failure_is_atomic(monkeypatch):
    from skeleton.ai.model_runtime import fair_stream_custody as module

    owner = make()
    before = owner.export()
    original = module._canonical

    def limited(value, *args, **kwargs):
        if isinstance(value, dict) and value.get("generation") == 1 and "mac" in value:
            raise ValueError("custody byte budget exceeded")
        return original(value, *args, **kwargs)

    monkeypatch.setattr(module, "_canonical", limited)
    with pytest.raises(ValueError, match="byte budget"):
        owner.transition(expected_generation=0, action="submit", request=request())
    assert owner.generation == 0
    assert owner.export() == before


@pytest.mark.parametrize("kwargs", [
    {"action": "submit", "request": request(), "budget": budget()},
    {"action": "plan", "budget": budget(), "tenant_id": "tenant"},
    {"action": "cancel", "request_id": "request", "receipt": {}},
])
def test_unused_action_arguments_are_never_silently_accepted(kwargs):
    owner = make()
    before = owner.export()
    with pytest.raises(ValueError, match="irrelevant"):
        owner.transition(expected_generation=0, **kwargs)
    assert owner.export() == before


def test_validly_signed_boolean_generation_is_not_custody_authority():
    from skeleton.ai.model_runtime import fair_stream_custody as module

    owner = make()
    owner.transition(expected_generation=0, action="submit", request=request())
    plan, state = owner.transition(expected_generation=1, action="plan", budget=budget())
    receipt = sign_execution_result(
        execution_key=E, session_id=SESSION, generation=2,
        checkpoint_digest=state["checkpoint_digest"], lease_id=plan.leases[0].lease_id,
        consumed_tokens=1, result_digest=RESULT,
    )
    receipt["generation"] = True
    receipt["mac"] = module._sign(E, {k: v for k, v in receipt.items() if k != "mac"})
    with pytest.raises(ValueError, match="generation"):
        owner.transition(expected_generation=2, action="acknowledge", receipt=receipt)
    assert owner.export() == state


@pytest.mark.parametrize("identity", ["bad\x00id", "\ud800", "x" * 129])
def test_cancellation_receipt_rejects_noncanonical_request_identity(identity):
    from skeleton.ai.model_runtime.fair_stream_custody import sign_unstarted_cancellation

    with pytest.raises(ValueError, match="request identity"):
        sign_unstarted_cancellation(
            execution_key=E, session_id=SESSION, generation=2,
            checkpoint_digest="b" * 64, lease_id="d" * 64, request_id=identity,
        )

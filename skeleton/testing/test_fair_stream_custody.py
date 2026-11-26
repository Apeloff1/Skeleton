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

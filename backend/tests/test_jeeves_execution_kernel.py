import threading
import time

import pytest

from core.jeeves_execution_kernel import (
    AdmissionRejected,
    BudgetExceeded,
    CancellationToken,
    CapabilityRejected,
    CapabilitySpec,
    DegradationRung,
    ExecutionBudget,
    ExecutionCancelled,
    JeevesRuntime,
    Priority,
    PriorityAdmissionGate,
    RuntimeGovernor,
)


def test_priority_parser_and_budget_are_fail_closed():
    assert Priority.parse("high") is Priority.INTERACTIVE
    assert Priority.parse("bulk") is Priority.BACKGROUND
    budget = ExecutionBudget(max_steps=1)
    budget.check(consume_step=True)
    with pytest.raises(BudgetExceeded):
        budget.check(consume_step=True)


def test_cancellation_token_is_idempotent_and_raises_reason():
    token = CancellationToken()
    assert token.cancel("operator stop") is True
    assert token.cancel("ignored") is False
    with pytest.raises(ExecutionCancelled, match="operator stop"):
        token.raise_if_cancelled()


def test_queue_is_bounded():
    gate = PriorityAdmissionGate(capacity=1, queue_capacity=0)
    permit = gate.acquire()
    try:
        with pytest.raises(AdmissionRejected, match="queue full"):
            gate.acquire(timeout=0.01)
    finally:
        permit.release()


def test_priority_waiter_precedes_background_waiter():
    gate = PriorityAdmissionGate(capacity=1, queue_capacity=4, poll_interval=0.005)
    first = gate.acquire()
    order = []
    lock = threading.Lock()

    def waiter(name, priority):
        permit = gate.acquire(priority, timeout=1)
        try:
            with lock:
                order.append(name)
            time.sleep(0.01)
        finally:
            permit.release()

    low = threading.Thread(target=waiter, args=("low", Priority.BACKGROUND))
    high = threading.Thread(target=waiter, args=("high", Priority.INTERACTIVE))
    low.start()
    time.sleep(0.02)
    high.start()
    time.sleep(0.02)
    first.release()
    low.join(1)
    high.join(1)
    assert order == ["high", "low"]


def test_waiting_admission_honors_cancellation():
    gate = PriorityAdmissionGate(capacity=1, queue_capacity=2, poll_interval=0.005)
    first = gate.acquire()
    token = CancellationToken()
    seen = []

    def waiter():
        try:
            gate.acquire(cancellation=token, timeout=1)
        except ExecutionCancelled:
            seen.append("cancelled")

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.02)
    token.cancel("superseded")
    thread.join(1)
    first.release()
    assert seen == ["cancelled"]
    assert gate.snapshot()["cancelled_while_waiting"] == 1


def test_governor_escalates_and_protects_background_and_writes():
    governor = RuntimeGovernor(
        min_samples=2, escalate_at=0.25, recover_at=0.05, window_seconds=30
    )
    assert governor.observe(False) is DegradationRung.NORMAL
    assert governor.observe(False) is DegradationRung.REDUCED_CACHING
    governor.observe(False)
    assert governor.rung is DegradationRung.SHED_BACKGROUND
    assert governor.permits(Priority.BACKGROUND) is False
    governor.observe(False)
    governor.observe(False)
    assert governor.rung is DegradationRung.EMERGENCY_READ_ONLY
    assert governor.permits(Priority.INTERACTIVE, mutates=True) is False
    assert governor.permits(Priority.CONTROL, mutates=True) is True


def test_capability_contract_enforces_approval_and_records_evidence():
    runtime = JeevesRuntime(capacity=1, queue_capacity=1)
    runtime.capabilities.register(
        CapabilitySpec(
            "world.mutate",
            lambda ctx, value: {"value": value},
            mutates=True,
            approval_required=True,
            tags=frozenset({"world", "mutation"}),
        )
    )
    with runtime.execution(max_steps=2) as ctx:
        with pytest.raises(CapabilityRejected, match="requires approval"):
            ctx.invoke(
                runtime.capabilities,
                runtime.governor,
                "world.mutate",
                kwargs={"value": 1},
            )
        result = ctx.invoke(
            runtime.capabilities,
            runtime.governor,
            "world.mutate",
            approved=True,
            kwargs={"value": 2},
        )
        assert result == {"value": 2}
        kinds = [row["kind"] for row in ctx.evidence()]
        assert "capability.start" in kinds
        assert "capability.finish" in kinds


def test_runtime_releases_capacity_after_failure():
    runtime = JeevesRuntime(capacity=1, queue_capacity=1)
    with pytest.raises(RuntimeError):
        with runtime.execution() as ctx:
            ctx.record("before.fail")
            raise RuntimeError("boom")
    snap = runtime.snapshot()
    assert snap["admission"]["active"] == 0
    assert snap["governor"]["samples"] == 1

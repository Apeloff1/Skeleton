"""Deterministic simulated CPU tests; NOT real-device qualification."""
from __future__ import annotations

import sqlite3
import pytest

from skeleton.ai.model_runtime.fair_stream_dispatch import (
    DispatchDeferred, DispatchUncertain, GuardedFairStreamDispatch,
)
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
from skeleton.ai.model_runtime.fair_stream_queue import (
    MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession
from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase

C, E, SESSION = b"c" * 32, b"e" * 32, "a" * 32


class SimulatedExternalCAS:
    """External CAS test double; no persistent anti-rollback guarantee."""
    def __init__(self):
        self.value = None

    def initialize(self, *, generation, digest):
        if self.value is not None:
            raise ValueError("already initialized")
        self.value = generation, digest

    def read(self):
        if self.value is None:
            raise ValueError("missing anchor")
        return self.value

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.value != (expected_generation, expected_digest):
            raise ValueError("CAS conflict")
        self.value = generation, digest


class SimulatedCommittedOwner:
    """Simulates a backend that durably commits before signing a receipt."""
    def __init__(self, *, execution_key=E, fail=False):
        self.execution_key = execution_key
        self.fail = fail
        self.calls = 0

    def execute_and_commit(self, permit, state):
        self.calls += 1
        if self.fail:
            raise OSError("simulated crash after unknown execution boundary")
        return sign_execution_result(
            execution_key=self.execution_key,
            session_id=SESSION,
            generation=state["generation"],
            checkpoint_digest=state["checkpoint_digest"],
            lease_id=permit.lease_id,
            consumed_tokens=permit.tokens,
            result_digest="b" * 64,
        )


def budget(*, slots=4, tokens=40, pressure=0, thermal=False):
    return MeasuredStreamBudget(
        4096, 1024, tokens, slots, pressure, thermal, "os_probe",
    )


def install_probe(monkeypatch, samples):
    iterator = iter(samples)
    def sample(self, *, token_budget, storage_path):
        result = next(iterator)
        if isinstance(result, Exception):
            raise result
        evidence = {
            "measurement": "os_probe",
            "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
        }
        return result, evidence
    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)


def make(owner=None):
    store = DurableFairStreamStore(
        sqlite3.connect(":memory:"), custody_key=C, execution_key=E,
        session_id=SESSION,
    )
    session = DurableFairStreamSession.bootstrap(store, SimulatedExternalCAS())
    return GuardedFairStreamDispatch(
        session, LiveStreamBudgetSampler(),
        owner or SimulatedCommittedOwner(), storage_path=".",
    )


def request(name="r1"):
    return StreamRequest(name, "tenant", InferencePhase.PREFILL, 40, 4)


def test_end_to_end_single_flight_and_signed_durable_result(monkeypatch):
    install_probe(monkeypatch, [budget(), budget()])
    owner = SimulatedCommittedOwner()
    guard = make(owner)
    guard.submit(request())
    permits, observation = guard.plan_live(token_budget=40)
    assert len(permits) == 1
    assert observation.effective_slots == 1
    assert not observation.gpu_device_qualified
    assert guard.execute_once(permits[0])["generation"] == 3
    assert owner.calls == 1
    assert not guard.uncertain


def test_fresh_thermal_hold_blocks_execution_without_backend_call(monkeypatch):
    install_probe(monkeypatch, [budget(), budget(thermal=True)])
    owner = SimulatedCommittedOwner()
    guard = make(owner)
    guard.submit(request())
    permits, _ = guard.plan_live(token_budget=40)
    with pytest.raises(DispatchDeferred, match="fresh pressure"):
        guard.execute_once(permits[0])
    assert owner.calls == 0
    assert not guard.uncertain


def test_backend_crash_fences_reexecution(monkeypatch):
    install_probe(monkeypatch, [budget(), budget()])
    owner = SimulatedCommittedOwner(fail=True)
    guard = make(owner)
    guard.submit(request())
    permits, _ = guard.plan_live(token_budget=40)
    with pytest.raises(DispatchUncertain, match="do not re-execute"):
        guard.execute_once(permits[0])
    with pytest.raises(DispatchUncertain, match="reconciliation"):
        guard.execute_once(permits[0])
    assert owner.calls == 1


def test_forged_receipt_quarantines(monkeypatch):
    install_probe(monkeypatch, [budget(), budget()])
    owner = SimulatedCommittedOwner(execution_key=b"x" * 32)
    guard = make(owner)
    guard.submit(request())
    permits, _ = guard.plan_live(token_budget=40)
    with pytest.raises(DispatchUncertain, match="not durably reconciled"):
        guard.execute_once(permits[0])
    assert guard.uncertain
    assert owner.calls == 1


def test_operator_budget_never_used_as_dispatch_provenance(monkeypatch):
    install_probe(monkeypatch, [MeasuredStreamBudget(
        4096, 1024, 40, 4, 0, False, "operator",
    )])
    guard = make()
    guard.submit(request())
    with pytest.raises(DispatchDeferred, match="provenance"):
        guard.plan_live(token_budget=40)


def test_unavailable_os_probe_denies_without_mutation(monkeypatch):
    install_probe(monkeypatch, [OSError("no sensor")])
    guard = make()
    guard.submit(request())
    with pytest.raises(DispatchDeferred, match="measurement"):
        guard.plan_live(token_budget=40)
    assert not guard.uncertain


def test_unissued_permit_never_executes(monkeypatch):
    install_probe(monkeypatch, [budget()])
    owner = SimulatedCommittedOwner()
    guard = make(owner)
    guard.submit(request())
    permits, _ = guard.plan_live(token_budget=40)
    from dataclasses import replace
    forged = replace(permits[0], tokens=permits[0].tokens + 1)
    with pytest.raises(DispatchUncertain, match="stale or unissued"):
        guard.execute_once(forged)
    assert owner.calls == 0


def test_zero_slot_hold_never_mints_permit(monkeypatch):
    install_probe(monkeypatch, [budget(pressure=980000)])
    guard = make()
    guard.submit(request())
    with pytest.raises(DispatchDeferred, match="pressure"):
        guard.plan_live(token_budget=40)


def test_strict_positive_bounded_budget_before_sampling(monkeypatch):
    install_probe(monkeypatch, [])
    guard = make()
    for invalid in (0, -1, True, 1 << 30):
        with pytest.raises(ValueError, match="bounded positive"):
            guard.plan_live(token_budget=invalid)


def test_pending_lease_refuses_second_plan(monkeypatch):
    install_probe(monkeypatch, [budget()])
    guard = make()
    guard.submit(request())
    permits, _ = guard.plan_live(token_budget=40)
    assert permits
    with pytest.raises(DispatchUncertain, match="pending"):
        guard.plan_live(token_budget=40)

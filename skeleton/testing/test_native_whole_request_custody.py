"""Whole-request native custody and pre-execution pressure recovery."""
import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred, DispatchUncertain
from skeleton.ai.model_runtime.fair_stream_execution_journal import FairStreamExecutionJournal, JournaledExecutionOwner
from skeleton.ai.model_runtime.fair_stream_queue import FairStreamScheduler, MeasuredStreamBudget, StreamRequest
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase
from skeleton.testing.test_fair_stream_dispatch import E, SESSION, install_probe, make, budget


class TerminalBackend:
    def __init__(self):
        self.calls = 0

    def run_and_commit(self, permit, state):
        self.calls += 1
        return 1, "b" * 64  # early EOS; actual usage is not the full reservation


def req(name="r1", tokens=200):
    return StreamRequest(name, "tenant", InferencePhase.PREFILL, tokens, 4)


def test_whole_request_plans_without_splitting_or_starving_smaller_requests():
    queue = FairStreamScheduler(quantum=128)
    queue.submit(req())
    queue.submit(req("small", 10))
    low = MeasuredStreamBudget(4096, 1024, 128, 1)
    result = queue.plan(low, whole_request=True)
    assert [lease.request_id for lease in result.leases] == ["small"]
    queue.acknowledge(result.leases[0].lease_id, consumed_tokens=1, terminal=True)
    assert queue.request_ids == ("r1",)
    full = queue.plan(MeasuredStreamBudget(4096, 1024, 200, 1), whole_request=True)
    assert full.leases[0].tokens == 200


def test_terminal_ack_cannot_retire_a_partial_slice():
    queue = FairStreamScheduler()
    queue.submit(req())
    lease = queue.plan(MeasuredStreamBudget(4096, 1024, 200, 1)).leases[0]
    with pytest.raises(ValueError, match="whole-request"):
        queue.acknowledge(lease.lease_id, consumed_tokens=1, terminal=True)
    assert queue.pending_ids == (lease.lease_id,)


def test_terminal_journal_receipt_recovery_retires_early_eos(monkeypatch):
    journal = FairStreamExecutionJournal(sqlite3.connect(":memory:"), session_id=SESSION, execution_key=E)
    backend = TerminalBackend()
    guard = make(JournaledExecutionOwner(journal, backend, whole_request=True))
    guard.submit(req())
    install_probe(monkeypatch, [budget(tokens=300, pressure=100_000), budget(tokens=300, pressure=100_000)])
    permits, _ = guard.plan_live(token_budget=300)
    assert permits[0].tokens == 200
    state = guard.execute_once(permits[0])
    receipt = journal.recover_committed_receipt(permits[0])
    assert receipt["terminal"] is True and receipt["consumed_tokens"] == 1
    assert state["checkpoint"]["requests"] == []
    assert backend.calls == 1


def test_pre_execution_pressure_deferral_resumes_same_permit(monkeypatch):
    journal = FairStreamExecutionJournal(sqlite3.connect(":memory:"), session_id=SESSION, execution_key=E)
    backend = TerminalBackend()
    guard = make(JournaledExecutionOwner(journal, backend, whole_request=True))
    guard.submit(req())
    install_probe(monkeypatch, [budget(tokens=300), budget(tokens=300, thermal=True), budget(tokens=300)])
    permits, _ = guard.plan_live(token_budget=300)
    with pytest.raises(DispatchDeferred):
        guard.execute_once(permits[0])
    assert backend.calls == 0
    assert guard.resume_or_plan_live(token_budget=300)[0] == permits
    state = guard.execute_once(permits[0])
    assert state["checkpoint"]["requests"] == [] and backend.calls == 1


def test_tampered_terminal_flag_is_not_authenticated(monkeypatch):
    class ForgedOwner:
        whole_request = True

        def execute_and_commit(self, permit, state):
            receipt = sign_execution_result(
                execution_key=E, session_id=SESSION, generation=permit.generation,
                checkpoint_digest=permit.checkpoint_digest, lease_id=permit.lease_id,
                consumed_tokens=1, result_digest="b" * 64, terminal=True,
            )
            receipt["terminal"] = False
            return receipt

    guard = make(ForgedOwner())
    guard.submit(req())
    install_probe(monkeypatch, [budget(tokens=300), budget(tokens=300)])
    permits, _ = guard.plan_live(token_budget=300)
    with pytest.raises(DispatchUncertain):
        guard.execute_once(permits[0])

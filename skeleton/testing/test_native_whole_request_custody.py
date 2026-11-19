"""Authenticated whole-request policy and bounded native execution recovery."""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
from skeleton.ai.model_runtime.fair_stream_dispatch import (
    DispatchDeferred, DispatchUncertain, GuardedFairStreamDispatch,
)
from skeleton.ai.model_runtime.fair_stream_execution_journal import (
    FairStreamExecutionJournal, JournaledExecutionOwner,
)
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import (
    FairStreamScheduler, MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession
from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase
from skeleton.testing.test_fair_stream_dispatch import (
    C, E, SESSION, SimulatedExternalCAS, install_probe, budget,
)


def req(name="r1", tokens=200, *, whole=True):
    return StreamRequest(
        name, "tenant", InferencePhase.PREFILL, tokens, 4,
        authorization_digest="a" * 64 if whole else None,
    )


class EarlyEOSBackend:
    def __init__(self):
        self.calls = 0

    def run_and_commit(self, permit, state):
        self.calls += 1
        return 1, "b" * 64


def make_whole(owner):
    store = DurableFairStreamStore(
        sqlite3.connect(":memory:"), custody_key=C, execution_key=E,
        session_id=SESSION, whole_request=True,
    )
    session = DurableFairStreamSession.bootstrap(store, SimulatedExternalCAS())
    return GuardedFairStreamDispatch(
        session, LiveStreamBudgetSampler(), owner,
        storage_path=".", whole_request=True,
    )


def test_whole_request_does_not_split_or_starve_smaller_request():
    queue = FairStreamScheduler(quantum=128, whole_request=True)
    queue.submit(req())
    queue.submit(req("small", 10))
    low = MeasuredStreamBudget(4096, 1024, 128, 1)
    result = queue.plan(low)
    assert [lease.request_id for lease in result.leases] == ["small"]
    queue.acknowledge(result.leases[0].lease_id, consumed_tokens=1)
    assert queue.request_ids == ("r1",)
    restored = FairStreamScheduler.restore(queue.checkpoint())
    assert restored.whole_request
    full = restored.plan(MeasuredStreamBudget(4096, 1024, 200, 1))
    assert full.leases[0].tokens == 200


def test_partial_scheduler_cannot_override_authenticated_completion_policy():
    queue = FairStreamScheduler()
    queue.submit(req(whole=False))
    lease = queue.plan(MeasuredStreamBudget(4096, 1024, 200, 1)).leases[0]
    before = queue.checkpoint()
    with pytest.raises(ValueError, match="execution policy"):
        queue.acknowledge(lease.lease_id, consumed_tokens=1, whole_request=True)
    assert queue.checkpoint() == before
    queue.acknowledge(lease.lease_id, consumed_tokens=1)
    assert queue.checkpoint()["requests"][0]["remaining_tokens"] == 199


def test_journal_receipt_retains_actual_eos_usage(monkeypatch):
    journal = FairStreamExecutionJournal(sqlite3.connect(":memory:"), session_id=SESSION, execution_key=E)
    backend = EarlyEOSBackend()
    guard = make_whole(JournaledExecutionOwner(journal, backend))
    guard.submit(req())
    install_probe(monkeypatch, [budget(tokens=300, pressure=100_000)] * 2)
    permits, _ = guard.plan_live(token_budget=300)
    assert permits[0].tokens == 200
    state = guard.execute_once(permits[0])
    receipt = journal.recover_committed_receipt(permits[0])
    assert receipt["consumed_tokens"] == 1
    assert state["checkpoint"]["requests"] == []
    assert backend.calls == 1


def test_pre_execution_deferral_preserves_original_permit(monkeypatch):
    journal = FairStreamExecutionJournal(sqlite3.connect(":memory:"), session_id=SESSION, execution_key=E)
    backend = EarlyEOSBackend()
    guard = make_whole(JournaledExecutionOwner(journal, backend))
    guard.submit(req())
    install_probe(monkeypatch, [budget(tokens=300), budget(tokens=300, thermal=True), budget(tokens=300)])
    permits, _ = guard.plan_live(token_budget=300)
    with pytest.raises(DispatchDeferred):
        guard.execute_once(permits[0])
    assert backend.calls == 0
    permit, state, _ = guard.dispatch_next(token_budget=300)
    assert permit == permits[0]
    assert state["checkpoint"]["requests"] == []
    assert backend.calls == 1


def test_tampered_consumed_count_is_not_authenticated(monkeypatch):
    class ForgedOwner:
        def execute_and_commit(self, permit, state):
            receipt = sign_execution_result(
                execution_key=E, session_id=SESSION, generation=permit.generation,
                checkpoint_digest=permit.checkpoint_digest, lease_id=permit.lease_id,
                consumed_tokens=1, result_digest="b" * 64,
            )
            receipt["consumed_tokens"] = 2
            return receipt

    guard = make_whole(ForgedOwner())
    guard.submit(req())
    install_probe(monkeypatch, [budget(tokens=300), budget(tokens=300)])
    permits, _ = guard.plan_live(token_budget=300)
    with pytest.raises(DispatchUncertain):
        guard.execute_once(permits[0])
    assert guard.uncertain

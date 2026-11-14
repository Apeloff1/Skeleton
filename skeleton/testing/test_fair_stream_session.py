"""Simulated durable dispatch boundary tests; no GPU/device qualification."""
from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_session import (
    CustodyQuarantined, DurableFairStreamSession,
)
from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore
from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
from skeleton.ai.model_runtime.fair_stream_queue import (
    MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase

C = b"c" * 32
E = b"e" * 32
SESSION = "a" * 32


class SimulatedIndependentWatermark:
    """Test-only external CAS stand-in, not a production durability claim."""
    def __init__(self):
        self.state = None
        self.fail_advance = False

    def initialize(self, *, generation, digest):
        if self.state is not None:
            raise ValueError("watermark already exists")
        self.state = (generation, digest)

    def read(self):
        if self.state is None:
            raise ValueError("watermark missing")
        return self.state

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.fail_advance:
            raise OSError("simulated independent anchor outage")
        if self.state != (expected_generation, expected_digest):
            raise ValueError("watermark CAS conflict")
        self.state = (generation, digest)


def store(connection=None):
    return DurableFairStreamStore(
        connection or sqlite3.connect(":memory:"),
        custody_key=C, execution_key=E, session_id=SESSION,
    )


def request():
    return StreamRequest("r1", "tenant", InferencePhase.PREFILL, 40, 4)


def budget(*, measurement="os_probe", thermal_hold=False):
    return MeasuredStreamBudget(
        4096, 1024, 20, 1, 0, thermal_hold, measurement,
    )


def test_commit_then_anchor_before_any_dispatch_permit():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    state = session.submit(request())
    assert anchor.state == (state["generation"], state["digest"])
    permits, state = session.plan(budget())
    assert len(permits) == 1
    assert permits[0].generation == state["generation"]
    assert permits[0].checkpoint_digest == state["checkpoint_digest"]
    assert permits[0].device_qualified is False
    assert anchor.state == (state["generation"], state["digest"])


def test_simulated_or_operator_budget_never_authorizes_dispatch():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    session.submit(request())
    state = session.verify()
    for measurement in ("operator", "simulated"):
        with pytest.raises(ValueError, match="live OS"):
            session.plan(budget(measurement=measurement))
    assert session.verify() == state


def test_measured_thermal_hold_issues_no_permit():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    session.submit(request())
    permits, state = session.plan(budget(thermal_hold=True))
    assert permits == ()
    assert session.pending_ids() == ()
    assert state["generation"] == 2


def test_anchor_failure_quarantines_even_if_sqlite_commit_succeeded():
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    state = session.verify()
    anchor.fail_advance = True
    with pytest.raises(CustodyQuarantined, match="reconciliation"):
        session.submit(request())
    assert session.quarantined
    with pytest.raises(CustodyQuarantined, match="quarantined"):
        session.verify()
    with pytest.raises(CustodyQuarantined, match="diverges"):
        DurableFairStreamSession(db, anchor)
    assert anchor.state == (state["generation"], state["digest"])


def test_pending_lease_survives_restart_without_reexecution(tmp_path):
    path = tmp_path / "trusted-by-caller.db"
    conn = sqlite3.connect(path)
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(conn), anchor)
    session.submit(request())
    permits, state = session.plan(budget())
    conn.close()
    reopened = DurableFairStreamSession(store(sqlite3.connect(path)), anchor)
    assert reopened.pending_ids() == (permits[0].lease_id,)
    with pytest.raises(CustodyQuarantined):
        reopened.plan(budget())
    # Reopen again: only a trusted execution-owner result can retire the lease.
    reopened = DurableFairStreamSession(store(sqlite3.connect(path)), anchor)
    receipt = sign_execution_result(
        execution_key=E, session_id=SESSION, generation=state["generation"],
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=permits[0].lease_id, consumed_tokens=20,
        result_digest="f" * 64,
    )
    next_state = reopened.acknowledge(receipt)
    assert next_state["generation"] == 3
    assert reopened.pending_ids() == ()


def test_wrong_execution_receipt_quarantines_without_mutating_sqlite():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    session.submit(request())
    permits, state = session.plan(budget())
    forged = sign_execution_result(
        execution_key=b"x" * 32, session_id=SESSION,
        generation=state["generation"],
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=permits[0].lease_id, consumed_tokens=20,
        result_digest="f" * 64,
    )
    with pytest.raises(CustodyQuarantined):
        session.acknowledge(forged)
    assert anchor.state == (state["generation"], state["digest"])


def test_rollback_of_sqlite_cannot_be_reconciled_with_external_anchor(tmp_path):
    path = tmp_path / "rollback.db"
    conn = sqlite3.connect(path)
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(conn), anchor)
    initial = session.verify()
    session.submit(request())
    conn.execute(
        "UPDATE local_fair_stream_custody SET generation = ?, digest = ?, payload = ?",
        (0, initial["digest"], __import__("json").dumps(
            initial, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")),
    )
    conn.commit()
    with pytest.raises(CustodyQuarantined, match="diverges"):
        DurableFairStreamSession(store(conn), anchor)


def test_multiple_requests_issue_one_durable_permit_and_next_receipt_remains_valid():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    session.submit(request())
    session.submit(replace(request(), request_id="r2", tenant_id="other"))
    live = replace(budget(), stream_slots=8, token_budget=160)
    completed = set()
    for _ in range(2):
        permits, state = session.plan(live, whole_request=True)
        assert len(permits) == 1
        permit = permits[0]
        completed.add(permit.request_id)
        receipt = sign_execution_result(
            execution_key=E, session_id=SESSION, generation=state["generation"],
            checkpoint_digest=state["checkpoint_digest"], lease_id=permit.lease_id,
            consumed_tokens=permit.tokens, result_digest="f" * 64, terminal=True,
        )
        session.acknowledge(receipt)
    assert completed == {"r1", "r2"}
    assert session.verify()["checkpoint"]["requests"] == []


@pytest.mark.parametrize("operation", ["submit", "cancel"])
def test_pending_lease_cannot_be_invalidated_by_unrelated_transition(operation):
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    session.submit(request())
    session.submit(replace(request(), request_id="r2"))
    permits, state = session.plan(budget())
    with pytest.raises(CustodyQuarantined):
        if operation == "submit":
            session.submit(replace(request(), request_id="r3"))
        else:
            deferred_id = "r2" if permits[0].request_id == "r1" else "r1"
            session.cancel(deferred_id)
    assert DurableFairStreamSession(db, anchor).verify() == state


def test_unconfirmed_anchor_advance_never_returns_permit():
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    session.submit(request())
    old = anchor.read()
    anchor.advance = lambda **kwargs: None
    with pytest.raises(CustodyQuarantined, match="reconciliation"):
        session.plan(budget())
    assert anchor.read() == old
    assert session.quarantined
    with pytest.raises(CustodyQuarantined):
        DurableFairStreamSession(db, anchor)


def test_anchor_acknowledgement_with_corrupted_sqlite_successor_is_quarantined():
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    session.submit(request())
    advance = anchor.advance

    def corrupt(**kwargs):
        advance(**kwargs)
        db._connection.execute("UPDATE local_fair_stream_custody SET payload=?", (b"{}",))
        db._connection.commit()

    anchor.advance = corrupt
    with pytest.raises(CustodyQuarantined, match="reconciliation"):
        session.plan(budget())
    assert session.quarantined
    assert not db._connection.in_transaction


def test_anchor_changes_during_snapshot_read_prevent_verified_state(monkeypatch):
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    load = db.load

    def racing_load(**kwargs):
        owner = load(**kwargs)
        anchor.state = (anchor.state[0] + 1, "f" * 64)
        return owner

    monkeypatch.setattr(db, "load", racing_load)
    with pytest.raises(CustodyQuarantined, match="diverges"):
        session.verify()
    assert session.quarantined
    assert not db._connection.in_transaction

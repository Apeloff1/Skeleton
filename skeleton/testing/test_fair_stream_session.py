"""Simulated durable dispatch boundary tests; no GPU/device qualification."""
from __future__ import annotations

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

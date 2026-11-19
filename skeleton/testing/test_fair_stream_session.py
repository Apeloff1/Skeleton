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

def test_whole_request_policy_authenticated_across_restart_and_early_eos(tmp_path):
    path = tmp_path / "whole-policy.sqlite3"
    anchor = SimulatedIndependentWatermark()

    def open_store(connection, whole_request):
        return DurableFairStreamStore(
            connection, custody_key=C, execution_key=E,
            session_id=SESSION, whole_request=whole_request,
        )

    with sqlite3.connect(path) as connection:
        session = DurableFairStreamSession.bootstrap(open_store(connection, True), anchor)
        session.submit(StreamRequest("native", "tenant", InferencePhase.PREFILL, 4, 4,
                                     authorization_digest="f" * 64))
        prior = session.verify()
        assert prior["checkpoint"]["execution_policy"] == "native-whole-request-v2"
        with pytest.raises(ValueError, match="execution policy"):
            session.plan(budget(), whole_request=False)
        assert session.verify() == prior
        permits, state = session.plan(budget())
        assert len(permits) == 1 and permits[0].tokens == 4
        permit = permits[0]
    with sqlite3.connect(path) as connection:
        with pytest.raises(CustodyQuarantined):
            DurableFairStreamSession(open_store(connection, False), anchor)
    with sqlite3.connect(path) as connection:
        restored = DurableFairStreamSession(open_store(connection, True), anchor)
        assert restored.verify() == state
        receipt = sign_execution_result(
            execution_key=E, session_id=SESSION, generation=permit.generation,
            checkpoint_digest=permit.checkpoint_digest, lease_id=permit.lease_id,
            consumed_tokens=1, result_digest="f" * 64,
        )
        with pytest.raises(ValueError, match="execution policy"):
            restored.acknowledge(receipt, whole_request=False)
        assert restored.verify() == state
        done = restored.acknowledge(receipt)
        assert done["checkpoint"]["requests"] == []
        assert done["checkpoint"]["pending"] == []


def test_legacy_checkpoint_cannot_silently_upgrade_execution_policy(tmp_path):
    path = tmp_path / "legacy-policy.sqlite3"
    anchor = SimulatedIndependentWatermark()
    with sqlite3.connect(path) as connection:
        original = DurableFairStreamSession.bootstrap(store(connection), anchor)
        before = original.verify()
        assert before["checkpoint"]["schema"].endswith(".v1")
        assert "execution_policy" not in before["checkpoint"]
        with pytest.raises(ValueError, match="execution policy"):
            original.plan(budget(), whole_request=True)
        assert original.verify() == before
    with sqlite3.connect(path) as connection:
        with pytest.raises(CustodyQuarantined):
            DurableFairStreamSession(DurableFairStreamStore(
                connection, custody_key=C, execution_key=E, session_id=SESSION,
                whole_request=True,
            ), anchor)
    with sqlite3.connect(path) as connection:
        assert DurableFairStreamSession(store(connection), anchor).verify() == before

@pytest.mark.parametrize("operation", ["verify", "pending_ids"])
def test_anchor_change_during_store_load_quarantines_observation(monkeypatch, operation):
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    original = db.load

    def moved(**kwargs):
        owner = original(**kwargs)
        anchor.state = (999, "f" * 64)
        return owner

    monkeypatch.setattr(db, "load", moved)
    with pytest.raises(CustodyQuarantined):
        getattr(session, operation)()
    assert session.quarantined


def test_anchor_acknowledgement_cannot_hide_corrupted_successor(monkeypatch):
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    session.submit(request())
    original = anchor.advance

    def corrupt(**kwargs):
        original(**kwargs)
        db._connection.execute(
            "UPDATE local_fair_stream_custody SET payload=?", (b"{}",),
        )
        db._connection.commit()

    monkeypatch.setattr(anchor, "advance", corrupt)
    with pytest.raises(CustodyQuarantined, match="reconciliation"):
        session.plan(budget())
    assert session.quarantined


def test_noncanonical_anchor_container_is_denied(monkeypatch):
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    original = anchor.read
    monkeypatch.setattr(anchor, "read", lambda: list(original()))
    with pytest.raises(CustodyQuarantined, match="high-watermark"):
        session.verify()

@pytest.mark.parametrize("nested", ["verify", "pending", "submit"])
def test_anchor_reader_reentry_quarantines_without_mutating_queue(monkeypatch, nested):
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    before = anchor.state
    original = anchor.read

    def read():
        with pytest.raises(CustodyQuarantined, match="recursive custody"):
            if nested == "verify":
                session.verify()
            elif nested == "pending":
                session.pending_ids()
            else:
                session.submit(request())
        return original()

    monkeypatch.setattr(anchor, "read", read)
    with pytest.raises(CustodyQuarantined):
        session.submit(request())
    assert session.quarantined
    assert anchor.state == before
    assert db.load(expected_generation=before[0], expected_digest=before[1]).export()["checkpoint"]["requests"] == []


def test_reentrant_anchor_advance_never_emits_permits(monkeypatch):
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    session.submit(request())
    advance = anchor.advance

    def callback(**kwargs):
        advance(**kwargs)
        with pytest.raises(CustodyQuarantined, match="recursive custody"):
            session.plan(budget())

    monkeypatch.setattr(anchor, "advance", callback)
    with pytest.raises(CustodyQuarantined, match="reconciliation"):
        session.plan(budget())
    assert session.quarantined
    reopened = DurableFairStreamSession(db, anchor)
    assert len(reopened.pending_ids()) == 1


def test_invalid_anchor_adapter_cannot_initialize_database():
    db = store()
    with pytest.raises(ValueError, match="high-watermark"):
        DurableFairStreamSession.bootstrap(db, object())
    assert db._connection.execute("SELECT COUNT(*) FROM local_fair_stream_custody").fetchone() == (0,)


def test_expected_anchor_generation_requires_canonical_integer():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    before = session.verify()
    with pytest.raises(ValueError, match="queue changed"):
        session.submit(request(), expected_anchor=(False, before["digest"]))
    assert session.verify() == before

"""Deterministic SQLite transaction and recovery tests (simulated CPU only)."""
from __future__ import annotations

from copy import deepcopy
import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore
from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
from skeleton.ai.model_runtime.fair_stream_queue import (
    MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase

C = b"c" * 32
E = b"e" * 32
SESSION = "a" * 32


def make(conn=None):
    conn = conn or sqlite3.connect(":memory:")
    return DurableFairStreamStore(
        conn, custody_key=C, execution_key=E, session_id=SESSION,
    )


def req():
    return StreamRequest("r1", "tenant-a", InferencePhase.PREFILL, 40, 4)


def budget():
    return MeasuredStreamBudget(4096, 1024, 20, 1, 0, False, "simulated")


def test_initialize_once_and_no_implicit_reset():
    store = make()
    first = store.initialize()
    assert first["generation"] == 0
    assert store.load(
        expected_generation=0, expected_digest=first["digest"],
    ).export() == first
    with pytest.raises(ValueError, match="already initialized"):
        store.initialize()
    assert store.load(
        expected_generation=0, expected_digest=first["digest"],
    ).export() == first


def test_restart_reconciles_pending_without_reexecution(tmp_path):
    path = tmp_path / "trusted-by-caller.db"
    conn = sqlite3.connect(path)
    store = make(conn)
    state = store.initialize()
    _, state = store.transition(
        expected_generation=0, expected_digest=state["digest"],
        action="submit", request=req(),
    )
    plan, state = store.transition(
        expected_generation=1, expected_digest=state["digest"],
        action="plan", budget=budget(),
    )
    assert len(plan.leases) == 1
    conn.close()
    reopened = make(sqlite3.connect(path))
    owner = reopened.load(
        expected_generation=2, expected_digest=state["digest"],
    )
    assert owner.pending_ids == (plan.leases[0].lease_id,)
    with pytest.raises(ValueError, match="pending"):
        reopened.transition(
            expected_generation=2, expected_digest=state["digest"],
            action="plan", budget=budget(),
        )
    assert reopened.load(
        expected_generation=2, expected_digest=state["digest"],
    ).export() == state
    receipt = sign_execution_result(
        execution_key=E, session_id=SESSION, generation=2,
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=plan.leases[0].lease_id, consumed_tokens=20,
        result_digest="b" * 64,
    )
    _, final = reopened.transition(
        expected_generation=2, expected_digest=state["digest"],
        action="acknowledge", receipt=receipt,
    )
    assert final["generation"] == 3
    assert not reopened.load(
        expected_generation=3, expected_digest=final["digest"],
    ).pending_ids


def test_generation_and_digest_cas_fence_stale_workers():
    store = make()
    initial = store.initialize()
    _, next_state = store.transition(
        expected_generation=0, expected_digest=initial["digest"],
        action="submit", request=req(),
    )
    with pytest.raises(ValueError, match="high-watermark"):
        store.transition(
            expected_generation=0, expected_digest=initial["digest"],
            action="submit", request=req(),
        )
    with pytest.raises(ValueError, match="high-watermark"):
        store.load(
            expected_generation=1, expected_digest=initial["digest"],
        )
    assert store.load(
        expected_generation=1, expected_digest=next_state["digest"],
    ).export() == next_state


def test_invalid_transition_is_rolled_back():
    store = make()
    state = store.initialize()
    with pytest.raises(ValueError, match="typed stream request"):
        store.transition(
            expected_generation=0, expected_digest=state["digest"],
            action="submit", request=None,
        )
    assert store.load(
        expected_generation=0, expected_digest=state["digest"],
    ).export() == state


def test_rejected_receipt_cannot_advance_persisted_state():
    store = make()
    state = store.initialize()
    _, state = store.transition(
        expected_generation=0, expected_digest=state["digest"],
        action="submit", request=req(),
    )
    plan, state = store.transition(
        expected_generation=1, expected_digest=state["digest"],
        action="plan", budget=budget(),
    )
    forged = sign_execution_result(
        execution_key=b"z" * 32, session_id=SESSION, generation=2,
        checkpoint_digest=state["checkpoint_digest"],
        lease_id=plan.leases[0].lease_id, consumed_tokens=1,
        result_digest="f" * 64,
    )
    with pytest.raises(ValueError, match="unauthenticated"):
        store.transition(
            expected_generation=2, expected_digest=state["digest"],
            action="acknowledge", receipt=forged,
        )
    assert store.load(
        expected_generation=2, expected_digest=state["digest"],
    ).export() == state


def test_tampered_database_blob_rejected_with_trusted_watermark():
    conn = sqlite3.connect(":memory:")
    store = make(conn)
    state = store.initialize()
    conn.execute(
        "UPDATE local_fair_stream_custody SET payload = ? WHERE session_id = ?",
        (b'{"schema":"forged"}', SESSION),
    )
    conn.commit()
    with pytest.raises(ValueError):
        store.load(expected_generation=0, expected_digest=state["digest"])


def test_external_watermark_detects_database_rollback(tmp_path):
    path = tmp_path / "rollback.db"
    conn = sqlite3.connect(path)
    store = make(conn)
    old = store.initialize()
    _, current = store.transition(
        expected_generation=0, expected_digest=old["digest"],
        action="submit", request=req(),
    )
    conn.close()
    # A full database rollback is NOT detectable from that database alone.
    # Trusted external generation+digest is mandatory for the next load.
    old_conn = sqlite3.connect(path)
    old_conn.execute(
        "UPDATE local_fair_stream_custody SET generation = ?, digest = ?, payload = ?",
        (0, old["digest"], __import__("json").dumps(
            old, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")),
    )
    old_conn.commit()
    reopened = make(old_conn)
    with pytest.raises(ValueError, match="high-watermark"):
        reopened.load(
            expected_generation=1, expected_digest=current["digest"],
        )


def test_concurrent_connection_cas_serialization(tmp_path):
    path = tmp_path / "cas.db"
    first = make(sqlite3.connect(path))
    state = first.initialize()
    second = make(sqlite3.connect(path))
    _, next_state = first.transition(
        expected_generation=0, expected_digest=state["digest"],
        action="submit", request=req(),
    )
    with pytest.raises(ValueError, match="high-watermark"):
        second.transition(
            expected_generation=0, expected_digest=state["digest"],
            action="submit", request=req(),
        )
    assert second.load(
        expected_generation=1, expected_digest=next_state["digest"],
    ).export() == next_state


def test_reject_active_transaction_and_key_alias():
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN")
    with pytest.raises(ValueError, match="active transaction"):
        make(conn)
    conn.rollback()
    with pytest.raises(ValueError, match="independent"):
        DurableFairStreamStore(
            conn, custody_key=C, execution_key=C, session_id=SESSION,
        )

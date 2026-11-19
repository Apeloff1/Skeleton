"""Custody schema regressions: no live model, no hardware qualification."""
import sqlite3

import pytest

from skeleton.ai.model_runtime.sqlite_custody_schema import CustodySchemaError, assert_custody_schema
from skeleton.testing.test_fair_stream_session import store, SimulatedIndependentWatermark, request
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession, CustodyQuarantined
from skeleton.testing.test_fair_stream_execution_journal import journal, permit
from skeleton.testing.test_fair_stream_result_access import setup, grant, permit as read_permit


def test_scheduler_rejects_trigger_before_anchor_or_state_mutation():
    db = store()
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    prior = anchor.read()
    db._connection.execute(
        "CREATE TRIGGER corrupt_custody AFTER UPDATE ON local_fair_stream_custody "
        "BEGIN DELETE FROM local_fair_stream_custody; END"
    )
    with pytest.raises(CustodyQuarantined):
        session.submit(request())
    assert anchor.read() == prior
    assert db._connection.execute("SELECT generation FROM local_fair_stream_custody").fetchone()[0] == 0


def test_journal_rejects_replaced_replay_index():
    db = journal(sqlite3.connect(":memory:"))
    db._connection.execute("DROP INDEX local_fair_stream_execution_request_identity")
    db._connection.execute(
        "CREATE INDEX local_fair_stream_execution_request_identity "
        "ON local_fair_stream_execution_journal(session_id,request_id)"
    )
    with pytest.raises(CustodySchemaError, match="replay index"):
        db.begin(permit())
    assert db._connection.execute("SELECT COUNT(*) FROM local_fair_stream_execution_journal").fetchone()[0] == 0


def test_temp_shadow_and_generated_columns_are_denied():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ledger(id TEXT PRIMARY KEY NOT NULL, value TEXT) WITHOUT ROWID")
    kwargs = dict(table="ledger", columns=("id", "value"), primary_key="id")
    assert_custody_schema(conn, **kwargs)
    conn.execute("CREATE TEMP TABLE ledger(id TEXT, value TEXT)")
    with pytest.raises(CustodySchemaError, match="shadow"):
        assert_custody_schema(conn, **kwargs)
    conn.execute("DROP TABLE temp.ledger")
    conn.execute("ALTER TABLE ledger ADD COLUMN extra TEXT GENERATED ALWAYS AS (value) VIRTUAL")
    with pytest.raises(CustodySchemaError, match="shape"):
        assert_custody_schema(conn, **kwargs)


def test_grant_trigger_cannot_erase_consumed_nonce(setup):
    from skeleton.ai.model_runtime.fair_stream_result_access import ResultReadDenied
    connection = setup["grant_handle"].connection
    connection.execute(
        "CREATE TRIGGER erase_nonce AFTER INSERT ON local_fair_stream_result_read_grants "
        "BEGIN DELETE FROM local_fair_stream_result_read_grants WHERE nonce=NEW.nonce; END"
    )
    with pytest.raises(ResultReadDenied, match="schema"):
        setup["reader"].read_once(read_permit(), operator_grant=grant(setup))
    assert connection.execute("SELECT COUNT(*) FROM local_fair_stream_result_read_grants").fetchone()[0] == 0


def test_schema_guard_does_not_materialize_unused_temp_database():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ledger(id TEXT PRIMARY KEY NOT NULL, value TEXT) WITHOUT ROWID")
    before = conn.execute("PRAGMA database_list").fetchall()
    assert_custody_schema(conn, table="ledger", columns=("id", "value"), primary_key="id")
    assert conn.execute("PRAGMA database_list").fetchall() == before
    conn.close()

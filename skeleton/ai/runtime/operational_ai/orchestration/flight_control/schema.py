"""Schema-bound durable queue without mixing it with model-history DDL."""
from __future__ import annotations
from .contracts import FlightConflict

SCHEMA_VERSION='1'
DDL=(
 """CREATE TABLE IF NOT EXISTS ai_flight_jobs (
    job_id TEXT PRIMARY KEY,
    principal TEXT NOT NULL REFERENCES principals(principal),
    session TEXT NOT NULL REFERENCES sessions(session),
    request_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    prompt BLOB NOT NULL,
    seed INTEGER NOT NULL,
    temperature REAL NOT NULL,
    priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 9),
    state TEXT NOT NULL CHECK(state IN ('queued','claimed','running','completed','held','cancelled')),
    worker TEXT,
    owner_fence INTEGER NOT NULL DEFAULT 0 CHECK(owner_fence>=0),
    lease_boot TEXT,
    lease_until_ns INTEGER,
    created_ns INTEGER NOT NULL,
    updated_ns INTEGER NOT NULL,
    started_ns INTEGER,
    finished_ns INTEGER,
    receipt_json BLOB,
    receipt_sha256 TEXT,
    hold_reason TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
    UNIQUE(session,request_id),
    CHECK ((state IN ('claimed','running') AND worker IS NOT NULL AND lease_boot IS NOT NULL AND lease_until_ns IS NOT NULL)
           OR state NOT IN ('claimed','running')),
    CHECK ((state='completed' AND receipt_json IS NOT NULL AND receipt_sha256 IS NOT NULL)
           OR state!='completed')
 )""",
 """CREATE TABLE IF NOT EXISTS ai_flight_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES ai_flight_jobs(job_id),
    ordinal INTEGER NOT NULL,
    kind TEXT NOT NULL,
    prior_digest TEXT NOT NULL,
    event_digest TEXT NOT NULL,
    event_json BLOB NOT NULL,
    UNIQUE(job_id,ordinal)
 )""",
 """CREATE INDEX IF NOT EXISTS ai_flight_admission_idx
    ON ai_flight_jobs(state,priority,created_ns)""",
 """CREATE INDEX IF NOT EXISTS ai_flight_expiry_idx
    ON ai_flight_jobs(state,lease_boot,lease_until_ns)""",
 """CREATE INDEX IF NOT EXISTS ai_flight_principal_idx
    ON ai_flight_jobs(principal,state)""",
)


def install(db)->None:
    with db.transaction() as conn:
        old=conn.execute("SELECT value FROM controls WHERE control='flight_schema'").fetchone()
        if old is not None and old[0]!=SCHEMA_VERSION:
            raise FlightConflict('unsupported flight-control schema')
        for ddl in DDL:conn.execute(ddl)
        if old is None:
            conn.execute("INSERT INTO controls(control,value) VALUES ('flight_schema',?)",
                         (SCHEMA_VERSION,))
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise FlightConflict('flight-control foreign-key violation')

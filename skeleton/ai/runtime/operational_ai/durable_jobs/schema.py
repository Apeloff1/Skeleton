"""Versioned SQLite schema; destructive or unreviewed migrations are refused."""
from __future__ import annotations
import sqlite3
from .errors import deny

VERSION = 1
STATES = ("pending","running","completed","failed","held","cancelled","cancel_requested")


def ensure_schema(db: sqlite3.Connection) -> None:
    current = db.execute("PRAGMA user_version").fetchone()[0]
    if current not in (0,VERSION):
        deny("schema-version-unsupported")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_durable_jobs(
        job_id TEXT PRIMARY KEY,
        tenant TEXT NOT NULL,
        user_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        request_id TEXT NOT NULL,
        model_sha TEXT NOT NULL,
        tokenizer_sha TEXT NOT NULL,
        payload_json BLOB NOT NULL,
        spec_sha TEXT NOT NULL,
        created_ms INTEGER NOT NULL,
        expires_ms INTEGER NOT NULL,
        next_eligible_ms INTEGER NOT NULL,
        priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 3),
        state TEXT NOT NULL CHECK(state IN (
          'pending','running','completed','failed','held','cancelled','cancel_requested'
        )),
        attempt INTEGER NOT NULL DEFAULT 0,
        lease_token_sha TEXT,
        worker_id TEXT,
        lease_expires_ms INTEGER,
        terminal_sha TEXT,
        result_json BLOB,
        failure_code TEXT,
        updated_ms INTEGER NOT NULL,
        UNIQUE(tenant,user_id,session_id,request_id)
    )""")
    db.execute("""CREATE INDEX IF NOT EXISTS ai_durable_jobs_pending_idx
       ON ai_durable_jobs(state,next_eligible_ms,priority,created_ms)""")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_job_deps(
       job_id TEXT NOT NULL REFERENCES ai_durable_jobs(job_id) ON DELETE RESTRICT,
       dependency_id TEXT NOT NULL REFERENCES ai_durable_jobs(job_id) ON DELETE RESTRICT,
       PRIMARY KEY(job_id,dependency_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_job_audit(
       seq INTEGER PRIMARY KEY AUTOINCREMENT,
       job_id TEXT NOT NULL,
       kind TEXT NOT NULL,
       event_json BLOB NOT NULL,
       previous_sha TEXT NOT NULL,
       event_sha TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_job_state(
       singleton INTEGER PRIMARY KEY CHECK(singleton=1),
       audit_sha TEXT NOT NULL,
       rr_tenant TEXT NOT NULL
    )""")
    db.execute("""INSERT OR IGNORE INTO ai_job_state(singleton,audit_sha,rr_tenant)
       VALUES(1,?,?)""",("0"*64,""))
    db.execute("PRAGMA user_version="+str(VERSION))

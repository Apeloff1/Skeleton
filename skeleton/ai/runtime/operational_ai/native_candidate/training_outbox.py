"""Durable local intent fence for candidate publication and ambiguous retries."""
from __future__ import annotations
import sqlite3
from threading import RLock
from .strict import identity, sha
from .errors import deny


class CandidateOutbox:
    def __init__(self, db: sqlite3.Connection):
        if not isinstance(db, sqlite3.Connection):
            deny("outbox-db")
        self.db = db
        self.lock = RLock()
        db.execute("""CREATE TABLE IF NOT EXISTS native_candidate_outbox(
            run_id TEXT PRIMARY KEY, artifact_sha TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('prepared','published','held')),
            receipt_sha TEXT)""")

    def prepare(self, run_id: str, artifact_sha: str) -> str:
        identity(run_id, "run")
        sha(artifact_sha, "artifact")
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT artifact_sha,state FROM native_candidate_outbox WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                if row is not None:
                    if row[0] != artifact_sha:
                        deny("outbox-conflicting-run")
                    self.db.execute("COMMIT")
                    return row[1]
                self.db.execute(
                    "INSERT INTO native_candidate_outbox VALUES(?,?,?,NULL)",
                    (run_id, artifact_sha, "prepared"),
                )
                self.db.execute("COMMIT")
                return "prepared"
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def finish(self, run_id: str, artifact_sha: str, receipt_sha: str) -> str:
        identity(run_id, "run")
        sha(artifact_sha, "artifact")
        sha(receipt_sha, "receipt")
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT artifact_sha,state,receipt_sha FROM native_candidate_outbox WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                if row is None or row[0] != artifact_sha:
                    deny("outbox-no-preparation")
                if row[1] == "published":
                    if row[2] != receipt_sha:
                        deny("outbox-terminal-conflict")
                    self.db.execute("COMMIT")
                    return "replayed"
                if row[1] != "prepared":
                    deny("outbox-held")
                self.db.execute(
                    "UPDATE native_candidate_outbox SET state='published',receipt_sha=? WHERE run_id=?",
                    (receipt_sha, run_id),
                )
                self.db.execute("COMMIT")
                return "published"
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def pending(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT run_id,artifact_sha FROM native_candidate_outbox WHERE state='prepared' ORDER BY run_id"
        ).fetchall()
        if len(rows) > 4096:
            deny("outbox-overflow")
        return [{"run_id": run, "artifact_sha": artifact} for run, artifact in rows]

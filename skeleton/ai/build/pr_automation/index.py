"""Durable, idempotent and tamper-evident PR automation event index."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .core import Evaluation, PRSnapshot


GENESIS_HASH = "0" * 64


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class EventIndex:
    """SQLite event log with hash chaining and action idempotency claims."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    delivery_id TEXT,
                    repository TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    head_sha TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    snapshot_fingerprint TEXT NOT NULL,
                    policy_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_delivery
                    ON events(delivery_id)
                    WHERE delivery_id IS NOT NULL AND delivery_id != '';
                CREATE INDEX IF NOT EXISTS idx_events_pr
                    ON events(repository, pr_number, sequence);
                CREATE TABLE IF NOT EXISTS latest (
                    repository TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    head_sha TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(repository, pr_number)
                );
                CREATE TABLE IF NOT EXISTS action_claims (
                    idempotency_key TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    expected_head_sha TEXT NOT NULL,
                    action_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def make_event_id(
        snapshot: PRSnapshot,
        evaluation: Evaluation,
        event_type: str,
    ) -> str:
        material = {
            "repository": snapshot.repository,
            "number": snapshot.number,
            "head_sha": snapshot.head_sha,
            "snapshot": evaluation.snapshot_fingerprint,
            "policy": evaluation.policy_fingerprint,
            "decision": evaluation.decision.value,
            "reasons": evaluation.reasons,
            "event_type": event_type,
        }
        return hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()

    def append(
        self,
        *,
        snapshot: PRSnapshot,
        evaluation: Evaluation,
        event_type: str,
        delivery_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        event_id = self.make_event_id(snapshot, evaluation, event_type)
        payload = {
            "snapshot": asdict(snapshot),
            "evaluation": asdict(evaluation),
            "extra": extra or {},
        }
        created_at = _utcnow()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute(
                "SELECT 1 FROM events WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
            if duplicate:
                conn.rollback()
                return False

            previous = conn.execute(
                """
                SELECT record_hash FROM events
                WHERE repository = ? AND pr_number = ?
                ORDER BY sequence DESC LIMIT 1
                """,
                (snapshot.repository, snapshot.number),
            ).fetchone()
            previous_hash = previous["record_hash"] if previous else GENESIS_HASH
            payload_json = _canonical(payload)
            record_material = _canonical(
                {
                    "event_id": event_id,
                    "delivery_id": delivery_id or "",
                    "repository": snapshot.repository,
                    "pr_number": snapshot.number,
                    "head_sha": snapshot.head_sha,
                    "event_type": event_type,
                    "decision": evaluation.decision.value,
                    "snapshot_fingerprint": evaluation.snapshot_fingerprint,
                    "policy_fingerprint": evaluation.policy_fingerprint,
                    "payload_json": payload_json,
                    "previous_hash": previous_hash,
                    "created_at": created_at,
                }
            )
            record_hash = hashlib.sha256(record_material.encode("utf-8")).hexdigest()

            conn.execute(
                """
                INSERT INTO events(
                    event_id, delivery_id, repository, pr_number, head_sha,
                    event_type, decision, snapshot_fingerprint, policy_fingerprint,
                    payload_json, previous_hash, record_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    delivery_id,
                    snapshot.repository,
                    snapshot.number,
                    snapshot.head_sha,
                    event_type,
                    evaluation.decision.value,
                    evaluation.snapshot_fingerprint,
                    evaluation.policy_fingerprint,
                    payload_json,
                    previous_hash,
                    record_hash,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO latest(
                    repository, pr_number, head_sha, decision, event_id,
                    record_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository, pr_number) DO UPDATE SET
                    head_sha = excluded.head_sha,
                    decision = excluded.decision,
                    event_id = excluded.event_id,
                    record_hash = excluded.record_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    snapshot.repository,
                    snapshot.number,
                    snapshot.head_sha,
                    evaluation.decision.value,
                    event_id,
                    record_hash,
                    created_at,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            conn.rollback()
            return False
        finally:
            conn.close()

    def claim_action(
        self,
        *,
        idempotency_key: str,
        repository: str,
        pr_number: int,
        expected_head_sha: str,
        action_kind: str,
        stale_after_seconds: int = 900,
    ) -> bool:
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM action_claims WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row:
                if row["status"] in {"succeeded", "uncertain"}:
                    conn.rollback()
                    return False
                if row["status"] == "inflight":
                    updated = datetime.fromisoformat(row["updated_at"])
                    if now - updated < timedelta(seconds=stale_after_seconds):
                        conn.rollback()
                        return False
                attempts = int(row["attempts"]) + 1
                conn.execute(
                    """
                    UPDATE action_claims
                    SET status = 'inflight', attempts = ?, error = NULL,
                        started_at = ?, updated_at = ?
                    WHERE idempotency_key = ?
                    """,
                    (attempts, now.isoformat(), now.isoformat(), idempotency_key),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO action_claims(
                        idempotency_key, repository, pr_number, expected_head_sha,
                        action_kind, status, attempts, error, started_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'inflight', 1, NULL, ?, ?)
                    """,
                    (
                        idempotency_key,
                        repository,
                        pr_number,
                        expected_head_sha,
                        action_kind,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            conn.commit()
            return True
        finally:
            conn.close()

    def finish_action(
        self,
        idempotency_key: str,
        *,
        success: bool,
        error: str | None = None,
        uncertain: bool = False,
    ) -> None:
        if success and uncertain:
            raise ValueError("successful action cannot have uncertain outcome")
        status = "succeeded" if success else ("uncertain" if uncertain else "failed")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE action_claims
                SET status = ?, error = ?, updated_at = ?
                WHERE idempotency_key = ?
                """,
                (
                    status,
                    None if success else (error or "unknown error")[:2000],
                    _utcnow(),
                    idempotency_key,
                ),
            )

    def iter_events(
        self,
        repository: str | None = None,
        pr_number: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        query = "SELECT * FROM events"
        clauses: list[str] = []
        params: list[Any] = []
        if repository is not None:
            clauses.append("repository = ?")
            params.append(repository)
        if pr_number is not None:
            clauses.append("pr_number = ?")
            params.append(pr_number)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY sequence"
        with self._connect() as conn:
            for row in conn.execute(query, params):
                yield dict(row)

    def verify_chain(self, repository: str, pr_number: int) -> bool:
        previous_hash = GENESIS_HASH
        for row in self.iter_events(repository, pr_number):
            if row["previous_hash"] != previous_hash:
                return False
            record_material = _canonical(
                {
                    "event_id": row["event_id"],
                    "delivery_id": row["delivery_id"] or "",
                    "repository": row["repository"],
                    "pr_number": row["pr_number"],
                    "head_sha": row["head_sha"],
                    "event_type": row["event_type"],
                    "decision": row["decision"],
                    "snapshot_fingerprint": row["snapshot_fingerprint"],
                    "policy_fingerprint": row["policy_fingerprint"],
                    "payload_json": row["payload_json"],
                    "previous_hash": row["previous_hash"],
                    "created_at": row["created_at"],
                }
            )
            expected = hashlib.sha256(record_material.encode("utf-8")).hexdigest()
            if expected != row["record_hash"]:
                return False
            previous_hash = row["record_hash"]
        return True

    def export_jsonl(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            for row in self.iter_events():
                fh.write(_canonical(row) + "\n")

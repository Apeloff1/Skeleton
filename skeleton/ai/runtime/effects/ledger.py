"""Durable tamper-evident SQLite ledger for AI effect transactions."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import sqlite3
import threading
from typing import Any, Iterator, Mapping

from .contracts import canonical_json, digest_json, ensure_aware, format_instant, parse_instant, utc_now


class EffectLedgerError(RuntimeError):
    pass


class IdempotencyConflict(EffectLedgerError):
    pass


class LeaseConflict(EffectLedgerError):
    pass


class SQLiteEffectLedger:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_schema()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS effect_transactions(
                transaction_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                core_execution_id TEXT NOT NULL,
                core_evidence_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lease_owner TEXT,
                lease_expires_at TEXT,
                event_count INTEGER NOT NULL DEFAULT 0,
                head_digest TEXT
            );
            CREATE TABLE IF NOT EXISTS effect_proposals(
                proposal_digest TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL REFERENCES effect_transactions(transaction_id) ON DELETE CASCADE,
                tenant_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                state TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                authorization_json TEXT,
                execution_json TEXT,
                verification_json TEXT,
                UNIQUE(tenant_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_effect_proposals_tx ON effect_proposals(transaction_id);
            CREATE TABLE IF NOT EXISTS effect_events(
                transaction_id TEXT NOT NULL REFERENCES effect_transactions(transaction_id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                previous_digest TEXT,
                event_digest TEXT NOT NULL,
                PRIMARY KEY(transaction_id, sequence)
            );
            """
        )

    def begin_transaction(
        self, *, transaction_id: str, tenant_id: str, operation_id: str,
        core_execution_id: str, core_evidence_digest: str, state: str = "created",
    ) -> bool:
        now = format_instant(utc_now())
        with self._tx() as conn:
            row = conn.execute(
                "SELECT tenant_id, operation_id, core_execution_id, core_evidence_digest FROM effect_transactions WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            if row is not None:
                expected = (tenant_id, operation_id, core_execution_id, core_evidence_digest)
                actual = tuple(row)
                if actual != expected:
                    raise EffectLedgerError("transaction identity collision")
                return False
            conn.execute(
                "INSERT INTO effect_transactions(transaction_id,tenant_id,operation_id,core_execution_id,core_evidence_digest,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (transaction_id, tenant_id, operation_id, core_execution_id, core_evidence_digest, state, now, now),
            )
        self.append_event(transaction_id, "transaction.created", {
            "tenant_id": tenant_id, "operation_id": operation_id,
            "core_execution_id": core_execution_id, "core_evidence_digest": core_evidence_digest,
        })
        return True

    def transaction_state(self, transaction_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT state FROM effect_transactions WHERE transaction_id=?", (transaction_id,)
        ).fetchone()
        return None if row is None else str(row[0])

    def set_transaction_state(self, transaction_id: str, state: str, *, reason: str = "") -> None:
        now = format_instant(utc_now())
        with self._tx() as conn:
            changed = conn.execute(
                "UPDATE effect_transactions SET state=?,updated_at=? WHERE transaction_id=?",
                (state, now, transaction_id),
            ).rowcount
            if changed != 1:
                raise EffectLedgerError("unknown transaction")
        self.append_event(transaction_id, "transaction.state", {"state": state, "reason": reason})

    def record_proposal(self, transaction_id: str, proposal: Any) -> bool:
        proposal_json = canonical_json(proposal.as_dict())
        with self._tx() as conn:
            duplicate = conn.execute(
                "SELECT proposal_digest,transaction_id,proposal_json FROM effect_proposals WHERE tenant_id=? AND idempotency_key=?",
                (proposal.tenant_id, proposal.idempotency_key),
            ).fetchone()
            if duplicate is not None:
                if duplicate[0] != proposal.digest or duplicate[2] != proposal_json:
                    raise IdempotencyConflict("idempotency key reused for different effect")
                return False
            conn.execute(
                "INSERT INTO effect_proposals(proposal_digest,transaction_id,tenant_id,proposal_id,idempotency_key,state,proposal_json) VALUES(?,?,?,?,?,?,?)",
                (proposal.digest, transaction_id, proposal.tenant_id, proposal.proposal_id, proposal.idempotency_key, "proposed", proposal_json),
            )
        self.append_event(transaction_id, "proposal.recorded", {
            "proposal_id": proposal.proposal_id, "proposal_digest": proposal.digest,
            "idempotency_key": proposal.idempotency_key, "kind": proposal.kind,
        })
        return True

    def update_proposal(
        self, transaction_id: str, proposal_digest: str, *, state: str,
        authorization: Mapping[str, Any] | None = None,
        execution: Mapping[str, Any] | None = None,
        verification: Mapping[str, Any] | None = None,
        event_type: str = "proposal.state", event_payload: Mapping[str, Any] | None = None,
    ) -> None:
        sets = ["state=?"]
        values: list[Any] = [state]
        if authorization is not None:
            sets.append("authorization_json=?")
            values.append(canonical_json(authorization))
        if execution is not None:
            sets.append("execution_json=?")
            values.append(canonical_json(execution))
        if verification is not None:
            sets.append("verification_json=?")
            values.append(canonical_json(verification))
        values.extend([proposal_digest, transaction_id])
        with self._tx() as conn:
            changed = conn.execute(
                f"UPDATE effect_proposals SET {','.join(sets)} WHERE proposal_digest=? AND transaction_id=?",
                tuple(values),
            ).rowcount
            if changed != 1:
                raise EffectLedgerError("unknown proposal")
        payload = {"proposal_digest": proposal_digest, "state": state}
        if event_payload:
            payload.update(dict(event_payload))
        self.append_event(transaction_id, event_type, payload)

    def append_event(self, transaction_id: str, event_type: str, payload: Mapping[str, Any]) -> str:
        created = format_instant(utc_now())
        payload_json = canonical_json(payload)
        with self._tx() as conn:
            row = conn.execute(
                "SELECT event_count,head_digest FROM effect_transactions WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown transaction")
            sequence = int(row[0]) + 1
            previous = row[1]
            event_digest = digest_json({
                "transaction_id": transaction_id, "sequence": sequence,
                "event_type": event_type, "payload": json.loads(payload_json),
                "created_at": created, "previous_digest": previous,
            })
            conn.execute(
                "INSERT INTO effect_events(transaction_id,sequence,event_type,payload_json,created_at,previous_digest,event_digest) VALUES(?,?,?,?,?,?,?)",
                (transaction_id, sequence, event_type, payload_json, created, previous, event_digest),
            )
            conn.execute(
                "UPDATE effect_transactions SET event_count=?,head_digest=?,updated_at=? WHERE transaction_id=?",
                (sequence, event_digest, created, transaction_id),
            )
        return event_digest

    def claim(self, transaction_id: str, owner: str, *, ttl: timedelta = timedelta(minutes=2), now: datetime | None = None) -> None:
        instant = ensure_aware(now or utc_now(), "now")
        expires = instant + ttl
        with self._tx() as conn:
            row = conn.execute(
                "SELECT lease_owner,lease_expires_at FROM effect_transactions WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown transaction")
            current_owner, current_expiry = row
            if current_owner and current_expiry and parse_instant(current_expiry) > instant and current_owner != owner:
                raise LeaseConflict("transaction is leased by another worker")
            conn.execute(
                "UPDATE effect_transactions SET lease_owner=?,lease_expires_at=? WHERE transaction_id=?",
                (owner, format_instant(expires), transaction_id),
            )
        self.append_event(transaction_id, "transaction.claimed", {"owner": owner, "expires_at": format_instant(expires)})

    def release(self, transaction_id: str, owner: str) -> None:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT lease_owner FROM effect_transactions WHERE transaction_id=?", (transaction_id,)
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown transaction")
            if row[0] not in {None, owner}:
                raise LeaseConflict("cannot release another worker's lease")
            conn.execute(
                "UPDATE effect_transactions SET lease_owner=NULL,lease_expires_at=NULL WHERE transaction_id=?",
                (transaction_id,),
            )

    def verify_chain(self, transaction_id: str) -> str | None:
        rows = self._conn.execute(
            "SELECT sequence,event_type,payload_json,created_at,previous_digest,event_digest FROM effect_events WHERE transaction_id=? ORDER BY sequence",
            (transaction_id,),
        ).fetchall()
        previous: str | None = None
        for expected_sequence, row in enumerate(rows, start=1):
            if row[0] != expected_sequence or row[4] != previous:
                raise EffectLedgerError("event chain sequence/parent mismatch")
            calculated = digest_json({
                "transaction_id": transaction_id, "sequence": row[0], "event_type": row[1],
                "payload": json.loads(row[2]), "created_at": row[3], "previous_digest": row[4],
            })
            if calculated != row[5]:
                raise EffectLedgerError("event digest mismatch")
            previous = row[5]
        head = self._conn.execute(
            "SELECT head_digest,event_count FROM effect_transactions WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()
        if head is None:
            raise EffectLedgerError("unknown transaction")
        if head[0] != previous or int(head[1]) != len(rows):
            raise EffectLedgerError("transaction head diverges from event chain")
        return previous

    def snapshot(self, transaction_id: str) -> dict[str, Any]:
        tx = self._conn.execute("SELECT * FROM effect_transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
        if tx is None:
            raise EffectLedgerError("unknown transaction")
        proposals = self._conn.execute(
            "SELECT * FROM effect_proposals WHERE transaction_id=? ORDER BY rowid", (transaction_id,)
        ).fetchall()
        events = self._conn.execute(
            "SELECT * FROM effect_events WHERE transaction_id=? ORDER BY sequence", (transaction_id,)
        ).fetchall()
        def decode(row: sqlite3.Row) -> dict[str, Any]:
            data = dict(row)
            for key in list(data):
                if key.endswith("_json") and data[key] is not None:
                    data[key] = json.loads(data[key])
            return data
        return {"transaction": dict(tx), "proposals": [decode(p) for p in proposals], "events": [decode(e) for e in events]}

"""Durable outbox; no side effects run automatically or through model text."""
import sqlite3
from ..contracts.canonical import dumps, loads, digest
from ..contracts.errors import ContractError, ConflictError
from ..contracts.identity import identifier

class Outbox:

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS pf_outbox(id TEXT PRIMARY KEY,operation TEXT NOT NULL,payload BLOB NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('pending','acknowledged')))")

    def enqueue(self, uid: str, operation: str, payload: dict) -> bool:
        identifier(uid)
        identifier(operation)
        raw = dumps(payload)
        seal = digest(payload)
        row = self.db.execute('SELECT operation,payload,digest FROM pf_outbox WHERE id=?', (uid,)).fetchone()
        if row:
            if row != (operation, raw, seal):
                raise ConflictError('outbox id conflict')
            return False
        self.db.execute('INSERT INTO pf_outbox VALUES(?,?,?,?,?)', (uid, operation, raw, seal, 'pending'))
        return True

    def pending(self, limit: int=100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ContractError('invalid outbox page')
        rows = self.db.execute("SELECT id,operation,payload,digest FROM pf_outbox WHERE status='pending' ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [{'id': id, 'operation': op, 'payload': loads(payload), 'sha256': seal} for id, op, payload, seal in rows]

    def acknowledge(self, uid: str, sha256: str) -> bool:
        identifier(uid)
        cur = self.db.execute("UPDATE pf_outbox SET status='acknowledged' WHERE id=? AND digest=? AND status='pending'", (uid, sha256))
        return cur.rowcount == 1

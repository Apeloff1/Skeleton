"""Exactly-once local intake for idempotent external response receipts."""
import sqlite3
from ..contracts.errors import ConflictError
from ..contracts.canonical import dumps, digest
from ..contracts.identity import identifier

class Inbox:

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS pf_inbox(id TEXT PRIMARY KEY,hash TEXT NOT NULL,content BLOB NOT NULL)')

    def accept(self, uid: str, response: dict) -> bool:
        identifier(uid)
        raw = dumps(response)
        seal = digest(response)
        row = self.db.execute('SELECT hash,content FROM pf_inbox WHERE id=?', (uid,)).fetchone()
        if row:
            if row != (seal, raw):
                raise ConflictError('idempotency response collision')
            return False
        self.db.execute('INSERT INTO pf_inbox VALUES(?,?,?)', (uid, seal, raw))
        return True

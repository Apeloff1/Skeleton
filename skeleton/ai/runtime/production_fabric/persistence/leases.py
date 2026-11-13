"""Lease fencing: ownership changes require a new monotonically increasing term."""
import sqlite3
from ..contracts.identity import identifier
from ..contracts.errors import ContractError, ConflictError

class LeaseStore:

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS pf_leases(resource TEXT PRIMARY KEY,owner TEXT NOT NULL,term INTEGER NOT NULL,deadline INTEGER NOT NULL)')

    def acquire(self, resource: str, owner: str, now: int, ttl: int) -> int:
        identifier(resource)
        identifier(owner)
        if type(now) is not int or type(ttl) is not int or now < 0 or (not 1 <= ttl <= 1000000):
            raise ContractError('invalid logical lease time')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT owner,term,deadline FROM pf_leases WHERE resource=?', (resource,)).fetchone()
            if row and row[2] > now and (row[0] != owner):
                raise ConflictError('lease held by another owner')
            term = row[1] + 1 if row else 1
            self.db.execute('INSERT INTO pf_leases VALUES(?,?,?,?) ON CONFLICT(resource) DO UPDATE SET owner=excluded.owner,term=excluded.term,deadline=excluded.deadline', (resource, owner, term, now + ttl))
            self.db.execute('COMMIT')
            return term
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def require(self, resource: str, owner: str, term: int, now: int) -> bool:
        row = self.db.execute('SELECT owner,term,deadline FROM pf_leases WHERE resource=?', (resource,)).fetchone()
        if not row or row[0] != owner or row[1] != term or (row[2] <= now):
            raise ConflictError('stale or expired fencing token')
        return True

"""Durable replay fence for bounded nonce reuse rejection."""
from ..contracts.errors import ContractError, AuthorizationError
from ..contracts.identity import identifier

class ReplayFence:

    def __init__(self, db):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS pf_nonces(namespace TEXT NOT NULL,nonce TEXT NOT NULL,deadline INTEGER NOT NULL,PRIMARY KEY(namespace,nonce))')

    def consume(self, namespace: str, nonce: str, now: int, ttl: int) -> bool:
        identifier(namespace)
        identifier(nonce)
        if type(now) is not int or type(ttl) is not int or now < 0 or (not 1 <= ttl <= 1000000):
            raise ContractError('invalid replay expiry')
        self.db.execute('DELETE FROM pf_nonces WHERE deadline<=?', (now,))
        try:
            self.db.execute('INSERT INTO pf_nonces VALUES(?,?,?)', (namespace, nonce, now + ttl))
        except Exception as exc:
            import sqlite3
            if isinstance(exc, sqlite3.IntegrityError):
                raise AuthorizationError('nonce replay detected') from exc
            raise
        return True

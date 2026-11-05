"""Atomic change groups on a standalone SQLite connection."""
from contextlib import contextmanager
import sqlite3
from ..contracts.errors import ContractError

@contextmanager
def transaction(db: sqlite3.Connection):
    if db.in_transaction:
        raise ContractError('nested transaction would silently weaken atomicity')
    db.execute('BEGIN IMMEDIATE')
    try:
        yield db
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise

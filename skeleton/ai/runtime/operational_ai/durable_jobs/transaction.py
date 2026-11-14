"""Bounded single-writer SQLite transaction helper for concurrent job operations."""
from __future__ import annotations
from contextlib import contextmanager
from threading import RLock
import sqlite3
from typing import Iterator
from .errors import deny


class TransactionGate:
    def __init__(self, db:sqlite3.Connection):
        self.db=db
        self._lock=RLock()
        self._poisoned=False

    @contextmanager
    def exclusive(self)->Iterator[sqlite3.Connection]:
        with self._lock:
            if self._poisoned:
                deny("transaction-unavailable")
            try:
                self.db.execute("BEGIN IMMEDIATE")
            except sqlite3.Error:
                deny("transaction-admission")
            try:
                yield self.db
                self.db.execute("COMMIT")
            except BaseException:
                # COMMIT can fail (busy reader, deferred constraint or I/O).
                # A failed commit must not strand the connection in a write
                # transaction or allow the next operation to inherit its work.
                if self.db.in_transaction:
                    try:
                        self.db.execute("ROLLBACK")
                    except sqlite3.Error:
                        # This connection has lost transaction custody. Do
                        # not let any later caller reuse its uncertain state.
                        self._poisoned = True
                        deny("transaction-rollback")
                raise

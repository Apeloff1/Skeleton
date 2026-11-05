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

    @contextmanager
    def exclusive(self)->Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
            except sqlite3.Error:
                deny("transaction-admission")
            try:
                yield self.db
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            else:
                self.db.execute("COMMIT")

"""Private, authenticated, restart-safe local worker result custody.

Results are inert JSON data, never executable commands. The work journal and
this store are separate transaction owners; a result may survive a crash
before journal settlement. Reconciliation requires independently authorized
review; a claimed job is never automatically restarted. MACs are not a
substitute for private file permissions or an external rollback anchor.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
import sqlite3
import threading
from typing import Any

from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle
from skeleton.frontier.payloads import json_snapshot

_TABLE = "frontier_worker_results_v1"
_FIELDS = ("scope", "work_id", "input_digest", "succeeded", "body", "receipt", "mac")
_MAX_BODY = 2 << 20
_MAX_ROWS = 16384
_MAX_TOTAL = 128 << 20


class ResultConflict(RuntimeError):
    """A work identity already has a different result or input."""


class ResultIntegrityError(RuntimeError):
    """Result custody cannot authenticate the stored record."""


class ResultCapacity(RuntimeError):
    """A bounded result store cannot admit another record."""


def _hex(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("lowercase SHA-256 required")
    return value


def _scope(value: object) -> str:
    if (type(value) is not str or not value or value != value.strip() or len(value) > 128
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("bounded result scope required")
    return value


def encode_result(value: Any, *, max_bytes: int = _MAX_BODY) -> bytes:
    raw = json.dumps(json_snapshot(value, max_bytes=max_bytes), sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(raw) > max_bytes:
        raise ValueError("encoded result exceeds budget")
    return raw


def input_digest(value: Any) -> str:
    return sha256(b"frontier.worker-input.v1\0" + encode_result(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkerResult:
    work_id: str
    input_digest: str
    succeeded: bool
    output: Any
    receipt_digest: str


class WorkerResultStore:
    """Owner/connection-bound immutable result ledger with exact replay."""

    def __init__(self, connection: sqlite3.Connection, *, scope: str, key: bytes,
                 max_rows: int = 4096, max_bytes: int = 64 << 20,
                 private_handle: PrivateSQLiteHandle | None = None, initialize: bool = True):
        if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
            raise ValueError("exclusive idle SQLite connection required")
        if type(key) is not bytes or len(key) != 32:
            raise ValueError("independent result custody key required")
        if type(max_rows) is not int or not 1 <= max_rows <= _MAX_ROWS:
            raise ValueError("invalid result row ceiling")
        if type(max_bytes) is not int or not 4096 <= max_bytes <= _MAX_TOTAL:
            raise ValueError("invalid result byte ceiling")
        if type(initialize) is not bool:
            raise ValueError("explicit initialization required")
        if private_handle is not None:
            if type(private_handle) is not PrivateSQLiteHandle or private_handle.connection is not connection:
                raise ValueError("private handle must bind exact connection")
            private_handle.assert_current()
        self._db, self._scope, self._key = connection, _scope(scope), key
        self._handle = private_handle
        self._max_rows, self._max_bytes = max_rows, max_bytes
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._closed = False
        with self._tx(check=False):
            if initialize:
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                    "scope TEXT NOT NULL, work_id TEXT NOT NULL, input_digest TEXT NOT NULL,"
                    "succeeded INTEGER NOT NULL CHECK(succeeded IN (0,1)), body BLOB NOT NULL,"
                    "receipt TEXT NOT NULL, mac TEXT NOT NULL,"
                    "PRIMARY KEY(scope,work_id)) WITHOUT ROWID"
                )
            self._schema()
            self._capacity()

    @property
    def scope(self) -> str:
        return self._scope

    def _owner(self):
        if self._closed or os.getpid() != self._pid or threading.get_ident() != self._thread:
            raise RuntimeError("result store owner changed or closed")
        if self._handle is not None:
            self._handle.assert_current()
        if self._db.in_transaction:
            raise RuntimeError("exclusive result transaction authority required")

    def _schema(self):
        rows = self._db.execute(f"PRAGMA table_info({_TABLE})").fetchall()
        if (tuple(r[1] for r in rows) != _FIELDS or
                tuple(r[2].upper() for r in rows) != ("TEXT","TEXT","TEXT","INTEGER","BLOB","TEXT","TEXT") or
                tuple(r[3] for r in rows) != (1,) * 7 or
                tuple(r[5] for r in rows) != (1,2,0,0,0,0,0)):
            raise ResultIntegrityError("unexpected result schema")
        if self._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                            (_TABLE,)).fetchone():
            raise ResultIntegrityError("result triggers forbidden")

    @contextmanager
    def _tx(self, *, check=True):
        self._owner()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if self._handle is not None:
                self._handle.assert_current()
            if check:
                self._schema()
            yield
            if self._handle is not None:
                self._handle.assert_current()
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _capacity(self, rows=0, size=0):
        count, total = self._db.execute(
            f"SELECT COUNT(*), COALESCE(SUM(length(body)+1024),0) FROM {_TABLE}"
        ).fetchone()
        if count + rows > self._max_rows or total + size > self._max_bytes:
            raise ResultCapacity("result custody capacity exhausted")

    def _receipt(self, scope, wid, digest, succeeded, body):
        return sha256(b"frontier.worker-result.v1\0" + encode_result([
            scope, wid, digest, succeeded, sha256(body).hexdigest()
        ])).hexdigest()

    def _mac(self, receipt):
        return hmac.new(self._key, b"frontier.worker-result.mac.v1\0" + bytes.fromhex(receipt),
                        sha256).hexdigest()

    def _read(self, wid):
        wid = _hex(wid)
        if self._db.execute(
            f"SELECT 1 FROM {_TABLE} WHERE scope=? AND work_id=? AND "
            "(length(body)>? OR length(input_digest)<>64 OR length(receipt)<>64 OR length(mac)<>64)",
            (self._scope, wid, _MAX_BODY),
        ).fetchone():
            raise ResultIntegrityError("oversized result record")
        row = self._db.execute(
            f"SELECT {','.join(_FIELDS)} FROM {_TABLE} WHERE scope=? AND work_id=?",
            (self._scope, wid),
        ).fetchone()
        if row is None:
            return None
        try:
            scope, stored, digest, succeeded, body, receipt, mac = row
            if scope != self._scope or stored != wid or type(succeeded) is not int or succeeded not in (0,1):
                raise ValueError("invalid result identity")
            _hex(digest)
            if type(body) is not bytes or not 0 < len(body) <= _MAX_BODY:
                raise ValueError("invalid body")
            expected = self._receipt(scope, wid, digest, succeeded, body)
            if not hmac.compare_digest(_hex(receipt), expected) or not hmac.compare_digest(_hex(mac), self._mac(expected)):
                raise ValueError("result authentication failed")
            output = json.loads(body)
            if encode_result(output) != body:
                raise ValueError("noncanonical result")
            return WorkerResult(wid, digest, bool(succeeded), output, receipt)
        except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
            raise ResultIntegrityError("invalid authenticated result record") from exc

    def load(self, work_id: str) -> WorkerResult | None:
        with self._tx():
            return self._read(work_id)

    def publish(self, work_id: str, *, digest: str, succeeded: bool, output: Any) -> WorkerResult:
        wid, digest = _hex(work_id), _hex(digest)
        if type(succeeded) is not bool:
            raise ValueError("explicit result outcome required")
        body = encode_result(output)
        receipt = self._receipt(self._scope, wid, digest, int(succeeded), body)
        with self._tx():
            previous = self._read(wid)
            if previous is not None:
                if previous.receipt_digest != receipt:
                    raise ResultConflict("work result already committed differently")
                return previous
            self._capacity(1, len(body)+1024)
            self._db.execute(f"INSERT INTO {_TABLE} VALUES (?,?,?,?,?,?,?)",
                             (self._scope, wid, digest, int(succeeded), body, receipt, self._mac(receipt)))
            return WorkerResult(wid, digest, succeeded, json.loads(body), receipt)

    def close(self):
        self._owner()
        self._closed = True

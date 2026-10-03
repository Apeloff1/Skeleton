"""Tenant-scoped records whose writes emit outbox events atomically.

``RecordStore`` shares one SQLite connection with its ``Outbox`` so every
create/update/delete and its ``record.*`` event commit in one transaction.
Updates use optimistic concurrency via ``expected_version``.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from skeleton.persistence.pack_h.codecs import canonical_json
from skeleton.persistence.pack_h.migrations import RECORD_MIGRATIONS, connect, migrate
from skeleton.persistence.pack_h.outbox import DomainEvent, Outbox

_ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")
_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_BODY_BYTES = 64 * 1024


class RecordError(RuntimeError):
    pass


class RecordNotFound(RecordError):
    pass


class RecordConflict(RecordError):
    def __init__(self, message: str, *, current_version: int) -> None:
        super().__init__(message)
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class Record:
    tenant_id: str
    record_id: str
    kind: str
    body: Dict[str, Any]
    version: int
    created_at: float
    updated_at: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "record_id": self.record_id,
            "kind": self.kind,
            "body": self.body,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _check(value: str, pattern: "re.Pattern[str]", field: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise RecordError(f"invalid {field}")
    return value


def _body(body: Mapping[str, Any]) -> str:
    if not isinstance(body, Mapping):
        raise RecordError("body must be an object")
    encoded = canonical_json(dict(body))
    if len(encoded.encode()) > MAX_BODY_BYTES:
        raise RecordError("body too large")
    return encoded


class RecordStore:
    AGGREGATE = "pack_h.record"

    def __init__(self, path: str = ":memory:", *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._conn = connect(path)
        self.outbox = Outbox(conn=self._conn, clock=clock)
        self._lock: threading.RLock = self.outbox.lock
        with self._lock:
            migrate(self._conn, "records", RECORD_MIGRATIONS)

    def _row(self, tenant_id: str, record_id: str, *, include_deleted: bool = False) -> Optional[tuple]:
        sql = ("SELECT tenant_id, record_id, kind, body_json, version, created_at, updated_at, deleted_at "
               "FROM pack_h_records WHERE tenant_id = ? AND record_id = ?")
        row = self._conn.execute(sql, (tenant_id, record_id)).fetchone()
        if row is None or (row[7] is not None and not include_deleted):
            return None
        return row

    @staticmethod
    def _record(row: tuple) -> Record:
        return Record(row[0], row[1], row[2], json.loads(row[3]), int(row[4]), float(row[5]), float(row[6]))

    def _event(self, rec: Record, event_type: str, extra: Optional[Dict[str, Any]] = None) -> DomainEvent:
        payload: Dict[str, Any] = {"tenant_id": rec.tenant_id, "record_id": rec.record_id, "kind": rec.kind,
                                   "version": rec.version}
        payload.update(extra or {})
        return DomainEvent(self.AGGREGATE, f"{rec.tenant_id}/{rec.record_id}", event_type, payload,
                           headers={"tenant_id": rec.tenant_id})

    def _tx(self, fn: Callable[[], Any]) -> Any:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                out = fn()
                self._conn.execute("COMMIT")
                return out
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def create(self, tenant_id: str, kind: str, body: Mapping[str, Any], *,
               record_id: Optional[str] = None) -> Record:
        _check(tenant_id, _ID_RE, "tenant_id")
        _check(kind, _KIND_RE, "kind")
        rid = _check(record_id or uuid.uuid4().hex, _ID_RE, "record_id")
        encoded = _body(body)

        def op() -> Record:
            existing = self._row(tenant_id, rid, include_deleted=True)
            if existing is not None:
                raise RecordConflict("record already exists", current_version=int(existing[4]))
            now = self._clock()
            self._conn.execute(
                "INSERT INTO pack_h_records (tenant_id, record_id, kind, body_json, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (tenant_id, rid, kind, encoded, now, now),
            )
            rec = Record(tenant_id, rid, kind, json.loads(encoded), 1, now, now)
            self.outbox.append(self._event(rec, "record.created"))
            return rec

        return self._tx(op)

    def get(self, tenant_id: str, record_id: str) -> Record:
        with self._lock:
            row = self._row(tenant_id, record_id)
        if row is None:
            raise RecordNotFound(record_id)
        return self._record(row)

    def list(self, tenant_id: str, *, kind: Optional[str] = None, limit: int = 100) -> List[Record]:
        limit = max(1, min(int(limit), 500))
        sql = ("SELECT tenant_id, record_id, kind, body_json, version, created_at, updated_at, deleted_at "
               "FROM pack_h_records WHERE tenant_id = ? AND deleted_at IS NULL")
        args: List[Any] = [tenant_id]
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY updated_at DESC, record_id LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [self._record(r) for r in rows]

    def update(self, tenant_id: str, record_id: str, body: Mapping[str, Any], *,
               expected_version: Optional[int] = None) -> Record:
        encoded = _body(body)

        def op() -> Record:
            row = self._row(tenant_id, record_id)
            if row is None:
                raise RecordNotFound(record_id)
            current = int(row[4])
            if expected_version is not None and expected_version != current:
                raise RecordConflict("version mismatch", current_version=current)
            now = self._clock()
            self._conn.execute(
                "UPDATE pack_h_records SET body_json = ?, version = ?, updated_at = ? "
                "WHERE tenant_id = ? AND record_id = ?",
                (encoded, current + 1, now, tenant_id, record_id),
            )
            rec = Record(tenant_id, record_id, row[2], json.loads(encoded), current + 1, float(row[5]), now)
            self.outbox.append(self._event(rec, "record.updated"))
            return rec

        return self._tx(op)

    def delete(self, tenant_id: str, record_id: str, *, expected_version: Optional[int] = None) -> Record:
        def op() -> Record:
            row = self._row(tenant_id, record_id)
            if row is None:
                raise RecordNotFound(record_id)
            current = int(row[4])
            if expected_version is not None and expected_version != current:
                raise RecordConflict("version mismatch", current_version=current)
            now = self._clock()
            self._conn.execute(
                "UPDATE pack_h_records SET deleted_at = ?, version = ?, updated_at = ? "
                "WHERE tenant_id = ? AND record_id = ?",
                (now, current + 1, now, tenant_id, record_id),
            )
            rec = Record(tenant_id, record_id, row[2], json.loads(row[3]), current + 1, float(row[5]), now)
            self.outbox.append(self._event(rec, "record.deleted"))
            return rec

        return self._tx(op)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

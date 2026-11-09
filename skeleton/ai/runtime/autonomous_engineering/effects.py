"""Durable P3 side-effect ledger, idempotency fence and saga compensation model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Iterable, Sequence


class EffectLedgerError(RuntimeError):
    pass


def _id(value: str, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _sha(value: str, field: str) -> str:
    text = _id(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _timestamp(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class EffectRecord:
    sequence_no: int
    effect_id: str
    operation_id: str
    effect_kind: str
    resource_ref: str
    idempotency_key: str
    request_digest: str
    compensable: bool
    status: str
    attempt_count: int
    applied_receipt_digest: str | None
    compensation_digest: str | None
    error_code: str | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if self.status not in {"reserved", "applied", "failed", "compensated"}:
            raise ValueError("unsupported effect status")
        if self.sequence_no < 1 or self.attempt_count < 1:
            raise ValueError("sequence/attempt counters must be positive")
        for field in (
            "effect_id",
            "operation_id",
            "effect_kind",
            "resource_ref",
            "idempotency_key",
        ):
            _id(getattr(self, field), field)
        _sha(self.request_digest, "request_digest")
        if self.applied_receipt_digest is not None:
            _sha(self.applied_receipt_digest, "applied_receipt_digest")
        if self.compensation_digest is not None:
            _sha(self.compensation_digest, "compensation_digest")


class EffectLedger:
    """SQLite-backed effect state with exact idempotency and compensation fences."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.exists() and self.path.is_symlink():
            raise EffectLedgerError("effect ledger path must not be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS effects (
                    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    effect_id TEXT NOT NULL UNIQUE,
                    operation_id TEXT NOT NULL,
                    effect_kind TEXT NOT NULL,
                    resource_ref TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    compensable INTEGER NOT NULL CHECK (compensable IN (0,1)),
                    status TEXT NOT NULL CHECK (status IN ('reserved','applied','failed','compensated')),
                    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
                    applied_receipt_digest TEXT,
                    compensation_digest TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS effects_operation_idx "
                "ON effects(operation_id, sequence_no)"
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> EffectRecord:
        return EffectRecord(
            sequence_no=int(row["sequence_no"]),
            effect_id=str(row["effect_id"]),
            operation_id=str(row["operation_id"]),
            effect_kind=str(row["effect_kind"]),
            resource_ref=str(row["resource_ref"]),
            idempotency_key=str(row["idempotency_key"]),
            request_digest=str(row["request_digest"]),
            compensable=bool(row["compensable"]),
            status=str(row["status"]),
            attempt_count=int(row["attempt_count"]),
            applied_receipt_digest=row["applied_receipt_digest"],
            compensation_digest=row["compensation_digest"],
            error_code=row["error_code"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def get(self, effect_id: str) -> EffectRecord | None:
        key = _id(effect_id, "effect_id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id = ?",
                (key,),
            ).fetchone()
        return None if row is None else self._record(row)

    def reserve(
        self,
        *,
        effect_id: str,
        operation_id: str,
        effect_kind: str,
        resource_ref: str,
        idempotency_key: str,
        request_digest: str,
        compensable: bool,
        now: datetime,
    ) -> EffectRecord:
        eid = _id(effect_id, "effect_id")
        op = _id(operation_id, "operation_id")
        kind = _id(effect_kind, "effect_kind")
        resource = _id(resource_ref, "resource_ref", maximum=1024)
        idem = _id(idempotency_key, "idempotency_key")
        digest = _sha(request_digest, "request_digest")
        if not isinstance(compensable, bool):
            raise TypeError("compensable must be boolean")
        stamp = _timestamp(now, "now")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM effects WHERE idempotency_key = ? OR effect_id = ? "
                "ORDER BY sequence_no LIMIT 1",
                (idem, eid),
            ).fetchone()
            if row is not None:
                existing = self._record(row)
                identity = (
                    existing.effect_id == eid
                    and existing.operation_id == op
                    and existing.effect_kind == kind
                    and existing.resource_ref == resource
                    and existing.idempotency_key == idem
                    and existing.request_digest == digest
                    and existing.compensable is compensable
                )
                if not identity:
                    raise EffectLedgerError(
                        "idempotency/effect identity reused for different side effect"
                    )
                return existing
            conn.execute(
                """
                INSERT INTO effects(
                    effect_id, operation_id, effect_kind, resource_ref,
                    idempotency_key, request_digest, compensable, status,
                    attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved', 1, ?, ?)
                """,
                (eid, op, kind, resource, idem, digest, int(compensable), stamp, stamp),
            )
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id = ?",
                (eid,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("effect reservation disappeared")
            return self._record(row)

    def mark_applied(
        self,
        effect_id: str,
        *,
        receipt_digest: str,
        now: datetime,
    ) -> EffectRecord:
        eid = _id(effect_id, "effect_id")
        receipt = _sha(receipt_digest, "receipt_digest")
        stamp = _timestamp(now, "now")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id = ?",
                (eid,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown effect")
            current = self._record(row)
            if current.status == "applied":
                if current.applied_receipt_digest != receipt:
                    raise EffectLedgerError("applied effect receipt identity conflict")
                return current
            if current.status != "reserved":
                raise EffectLedgerError(
                    f"cannot apply effect from status {current.status}"
                )
            conn.execute(
                "UPDATE effects SET status='applied', applied_receipt_digest=?, "
                "error_code=NULL, updated_at=? WHERE effect_id=?",
                (receipt, stamp, eid),
            )
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            return self._record(row)

    def mark_failed(
        self,
        effect_id: str,
        *,
        error_code: str,
        now: datetime,
    ) -> EffectRecord:
        eid = _id(effect_id, "effect_id")
        code = _id(error_code, "error_code")
        stamp = _timestamp(now, "now")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown effect")
            current = self._record(row)
            if current.status == "failed" and current.error_code == code:
                return current
            if current.status != "reserved":
                raise EffectLedgerError(
                    f"cannot fail effect from status {current.status}"
                )
            conn.execute(
                "UPDATE effects SET status='failed', error_code=?, updated_at=? "
                "WHERE effect_id=?",
                (code, stamp, eid),
            )
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            return self._record(row)

    def retry(
        self,
        effect_id: str,
        *,
        max_attempts: int,
        now: datetime,
    ) -> EffectRecord:
        eid = _id(effect_id, "effect_id")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 32
        ):
            raise ValueError("max_attempts must be integer in [1,32]")
        stamp = _timestamp(now, "now")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown effect")
            current = self._record(row)
            if current.status != "failed":
                raise EffectLedgerError("only failed effects may be retried")
            if current.attempt_count >= max_attempts:
                raise EffectLedgerError("effect retry budget exhausted")
            conn.execute(
                "UPDATE effects SET status='reserved', attempt_count=attempt_count+1, "
                "error_code=NULL, updated_at=? WHERE effect_id=?",
                (stamp, eid),
            )
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            return self._record(row)

    def mark_compensated(
        self,
        effect_id: str,
        *,
        compensation_digest: str,
        now: datetime,
    ) -> EffectRecord:
        eid = _id(effect_id, "effect_id")
        digest = _sha(compensation_digest, "compensation_digest")
        stamp = _timestamp(now, "now")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            if row is None:
                raise EffectLedgerError("unknown effect")
            current = self._record(row)
            if not current.compensable:
                raise EffectLedgerError("effect is not compensable")
            if current.status == "compensated":
                if current.compensation_digest != digest:
                    raise EffectLedgerError("compensation identity conflict")
                return current
            if current.status != "applied":
                raise EffectLedgerError(
                    f"cannot compensate effect from status {current.status}"
                )
            conn.execute(
                "UPDATE effects SET status='compensated', compensation_digest=?, "
                "updated_at=? WHERE effect_id=?",
                (digest, stamp, eid),
            )
            row = conn.execute(
                "SELECT * FROM effects WHERE effect_id=?",
                (eid,),
            ).fetchone()
            return self._record(row)

    def operation(self, operation_id: str) -> tuple[EffectRecord, ...]:
        op = _id(operation_id, "operation_id")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM effects WHERE operation_id=? ORDER BY sequence_no",
                (op,),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def compensation_candidates(self, operation_id: str) -> tuple[EffectRecord, ...]:
        rows = self.operation(operation_id)
        return tuple(
            row
            for row in reversed(rows)
            if row.status == "applied" and row.compensable
        )


@dataclass(frozen=True, slots=True)
class SagaStep:
    step_id: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _id(self.step_id, "step_id"))
        deps = tuple(sorted({_id(item, "depends_on") for item in self.depends_on}))
        if self.step_id in deps:
            raise ValueError("saga step cannot depend on itself")
        object.__setattr__(self, "depends_on", deps)


@dataclass(frozen=True, slots=True)
class SagaDefinition:
    saga_id: str
    steps: tuple[SagaStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "saga_id", _id(self.saga_id, "saga_id"))
        if not self.steps:
            raise ValueError("saga requires at least one step")
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("saga step ids must be unique")
        by = set(ids)
        for step in self.steps:
            missing = set(step.depends_on) - by
            if missing:
                raise ValueError(f"saga step {step.step_id} has unknown dependencies")
        self.topological_order()

    def topological_order(self) -> tuple[str, ...]:
        by = {step.step_id: step for step in self.steps}
        indegree = {key: 0 for key in by}
        children = {key: set() for key in by}
        for step in self.steps:
            for dep in step.depends_on:
                indegree[step.step_id] += 1
                children[dep].add(step.step_id)
        ready = sorted(key for key, value in indegree.items() if value == 0)
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in sorted(children[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        if len(order) != len(by):
            raise ValueError("saga dependency cycle")
        return tuple(order)

    def ready(self, completed: Iterable[str]) -> tuple[str, ...]:
        done = {_id(item, "completed_step") for item in completed}
        by = {step.step_id: step for step in self.steps}
        if not done <= set(by):
            raise ValueError("completed set contains unknown saga step")
        return tuple(
            step_id
            for step_id in self.topological_order()
            if step_id not in done and set(by[step_id].depends_on) <= done
        )

    def compensation_order(self, applied: Iterable[str]) -> tuple[str, ...]:
        applied_set = {_id(item, "applied_step") for item in applied}
        order = self.topological_order()
        if not applied_set <= set(order):
            raise ValueError("applied set contains unknown saga step")
        return tuple(step_id for step_id in reversed(order) if step_id in applied_set)


__all__ = [
    "EffectLedger",
    "EffectLedgerError",
    "EffectRecord",
    "SagaDefinition",
    "SagaStep",
]

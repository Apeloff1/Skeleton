"""Durable non-idempotent side-effect compensation for hostile gap G015.

The existing tool saga runtime is the execution engine.  This module supplies a
lower-level durable authority contract for effects that cannot be made
idempotent: before an effect may be committed it must have either a concrete
compensation contract or an explicit manual-reconciliation plan.

The ledger never executes the effect or compensation itself.  It owns the
truth required to recover safely after a crash:
* intent identity and request digest are immutable;
* a committed external receipt can be recorded exactly once;
* compensation claims use monotonically increasing fencing generations;
* only the current claim may close compensation;
* manual-only effects cannot be falsely marked compensated;
* every non-terminal committed effect is queryable as in-doubt work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Iterable


_SCHEMA = "skeleton.non_idempotent_effect_compensation.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_INT = (1 << 63) - 1


class EffectCompensationError(RuntimeError):
    """Base compensation-authority failure."""


class EffectCompensationConflict(EffectCompensationError):
    """Caller state conflicts with durable compensation state."""


class EffectCompensationCorruption(EffectCompensationError):
    """Persisted compensation state is invalid."""


class RecoveryMode(str, Enum):
    AUTOMATIC_COMPENSATION = "automatic_compensation"
    MANUAL_RECONCILIATION = "manual_reconciliation"


class EffectState(str, Enum):
    PREPARED = "prepared"
    COMMITTED = "committed"
    COMPENSATION_REQUIRED = "compensation_required"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    MANUAL_REQUIRED = "manual_required"
    MANUAL_RESOLVED = "manual_resolved"


_TERMINAL = frozenset({EffectState.COMPENSATED, EffectState.MANUAL_RESOLVED})


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EffectCompensationError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise EffectCompensationError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EffectCompensationError(f"{field} contains control characters")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise EffectCompensationError(f"{field} must be canonical lowercase SHA-256")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= _MAX_INT:
        raise EffectCompensationError(
            f"{field} must be an integer in [{minimum}, {_MAX_INT}]"
        )
    return value


def _now(value: int | None) -> int:
    return _integer(time.time_ns() if value is None else value, "now_ns", minimum=1)


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EffectCompensationError("effect identity must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class EffectIntent:
    tenant_id: str
    operation_id: str
    effect_id: str
    action: str
    request_digest: str
    recovery_mode: RecoveryMode
    compensation_action: str | None = None
    compensation_request_digest: str | None = None
    manual_reconciliation_reason: str | None = None

    def __post_init__(self) -> None:
        for field in ("tenant_id", "operation_id", "effect_id", "action"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self, "request_digest", _digest(self.request_digest, "request_digest")
        )
        try:
            mode = RecoveryMode(self.recovery_mode)
        except ValueError as exc:
            raise EffectCompensationError("invalid recovery_mode") from exc
        object.__setattr__(self, "recovery_mode", mode)
        if mode is RecoveryMode.AUTOMATIC_COMPENSATION:
            if self.compensation_action is None or self.compensation_request_digest is None:
                raise EffectCompensationError(
                    "automatic compensation requires action and request digest"
                )
            object.__setattr__(
                self,
                "compensation_action",
                _text(self.compensation_action, "compensation_action"),
            )
            object.__setattr__(
                self,
                "compensation_request_digest",
                _digest(
                    self.compensation_request_digest,
                    "compensation_request_digest",
                ),
            )
            if self.manual_reconciliation_reason is not None:
                raise EffectCompensationError(
                    "automatic compensation cannot carry manual reconciliation reason"
                )
        else:
            if self.compensation_action is not None or self.compensation_request_digest is not None:
                raise EffectCompensationError(
                    "manual reconciliation cannot declare automatic compensation"
                )
            if self.manual_reconciliation_reason is None:
                raise EffectCompensationError(
                    "manual reconciliation requires an explicit reason"
                )
            object.__setattr__(
                self,
                "manual_reconciliation_reason",
                _text(
                    self.manual_reconciliation_reason,
                    "manual_reconciliation_reason",
                    maximum=1024,
                ),
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema": _SCHEMA,
                "tenant_id": self.tenant_id,
                "operation_id": self.operation_id,
                "effect_id": self.effect_id,
                "action": self.action,
                "request_digest": self.request_digest,
                "recovery_mode": self.recovery_mode.value,
                "compensation_action": self.compensation_action,
                "compensation_request_digest": self.compensation_request_digest,
                "manual_reconciliation_reason": self.manual_reconciliation_reason,
            }
        )


@dataclass(frozen=True, slots=True)
class EffectRecord:
    intent: EffectIntent
    state: EffectState
    forward_receipt_digest: str | None
    compensation_receipt_digest: str | None
    resolution_receipt_digest: str | None
    claim_generation: int
    claim_owner: str | None
    created_at_ns: int
    updated_at_ns: int

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema": _SCHEMA,
                "intent_digest": self.intent.digest,
                "state": self.state.value,
                "forward_receipt_digest": self.forward_receipt_digest,
                "compensation_receipt_digest": self.compensation_receipt_digest,
                "resolution_receipt_digest": self.resolution_receipt_digest,
                "claim_generation": self.claim_generation,
                "claim_owner": self.claim_owner,
                "created_at_ns": self.created_at_ns,
                "updated_at_ns": self.updated_at_ns,
            }
        )


class SQLiteEffectCompensationLedger:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(
            str(path), check_same_thread=False, isolation_level=None, timeout=5.0
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS effect_compensation (
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    effect_id TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    intent_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    forward_receipt_digest TEXT,
                    compensation_receipt_digest TEXT,
                    resolution_receipt_digest TEXT,
                    claim_generation INTEGER NOT NULL,
                    claim_owner TEXT,
                    created_at_ns INTEGER NOT NULL,
                    updated_at_ns INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id, operation_id, effect_id)
                );
                """
            )

    @staticmethod
    def _intent_json(intent: EffectIntent) -> str:
        return json.dumps(
            {
                "tenant_id": intent.tenant_id,
                "operation_id": intent.operation_id,
                "effect_id": intent.effect_id,
                "action": intent.action,
                "request_digest": intent.request_digest,
                "recovery_mode": intent.recovery_mode.value,
                "compensation_action": intent.compensation_action,
                "compensation_request_digest": intent.compensation_request_digest,
                "manual_reconciliation_reason": intent.manual_reconciliation_reason,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _parse_intent(raw: str) -> EffectIntent:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EffectCompensationCorruption("persisted intent JSON is invalid") from exc
        if not isinstance(data, dict):
            raise EffectCompensationCorruption("persisted intent must be an object")
        try:
            return EffectIntent(**data)
        except (TypeError, EffectCompensationError) as exc:
            raise EffectCompensationCorruption("persisted intent is invalid") from exc

    def _decode(self, row: sqlite3.Row) -> EffectRecord:
        intent = self._parse_intent(str(row["intent_json"]))
        if intent.digest != row["intent_digest"]:
            raise EffectCompensationCorruption("intent digest mismatch")
        try:
            state = EffectState(row["state"])
        except ValueError as exc:
            raise EffectCompensationCorruption("invalid persisted effect state") from exc
        for field in (
            "forward_receipt_digest",
            "compensation_receipt_digest",
            "resolution_receipt_digest",
        ):
            if row[field] is not None:
                try:
                    _digest(row[field], field)
                except EffectCompensationError as exc:
                    raise EffectCompensationCorruption(str(exc)) from exc
        claim_owner = row["claim_owner"]
        if claim_owner is not None:
            try:
                claim_owner = _text(claim_owner, "claim_owner")
            except EffectCompensationError as exc:
                raise EffectCompensationCorruption(str(exc)) from exc
        return EffectRecord(
            intent=intent,
            state=state,
            forward_receipt_digest=row["forward_receipt_digest"],
            compensation_receipt_digest=row["compensation_receipt_digest"],
            resolution_receipt_digest=row["resolution_receipt_digest"],
            claim_generation=int(row["claim_generation"]),
            claim_owner=claim_owner,
            created_at_ns=int(row["created_at_ns"]),
            updated_at_ns=int(row["updated_at_ns"]),
        )

    def prepare(self, intent: EffectIntent, *, now_ns: int | None = None) -> EffectRecord:
        if not isinstance(intent, EffectIntent):
            raise TypeError("intent must be EffectIntent")
        now = _now(now_ns)
        raw = self._intent_json(intent)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM effect_compensation
                    WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                    """,
                    (intent.tenant_id, intent.operation_id, intent.effect_id),
                ).fetchone()
                if row is not None:
                    existing = self._decode(row)
                    if existing.intent.digest != intent.digest:
                        raise EffectCompensationConflict(
                            "effect identity reused with different immutable intent"
                        )
                    self._connection.execute("COMMIT")
                    return existing
                self._connection.execute(
                    """
                    INSERT INTO effect_compensation(
                        tenant_id, operation_id, effect_id, intent_json,
                        intent_digest, state, claim_generation, created_at_ns,
                        updated_at_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        intent.tenant_id,
                        intent.operation_id,
                        intent.effect_id,
                        raw,
                        intent.digest,
                        EffectState.PREPARED.value,
                        now,
                        now,
                    ),
                )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return self.get(
            tenant_id=intent.tenant_id,
            operation_id=intent.operation_id,
            effect_id=intent.effect_id,
        )

    def get(self, *, tenant_id: str, operation_id: str, effect_id: str) -> EffectRecord:
        tenant = _text(tenant_id, "tenant_id")
        operation = _text(operation_id, "operation_id")
        effect = _text(effect_id, "effect_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM effect_compensation
                WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                """,
                (tenant, operation, effect),
            ).fetchone()
        if row is None:
            raise EffectCompensationError("unknown effect intent")
        return self._decode(row)

    def mark_committed(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        effect_id: str,
        forward_receipt_digest: str,
        now_ns: int | None = None,
    ) -> EffectRecord:
        receipt = _digest(forward_receipt_digest, "forward_receipt_digest")
        now = _now(now_ns)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(
                    tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id
                )
                if current.state is EffectState.COMMITTED and current.forward_receipt_digest == receipt:
                    self._connection.execute("COMMIT")
                    return current
                if current.state is not EffectState.PREPARED:
                    raise EffectCompensationConflict(
                        f"effect cannot commit from state {current.state.value}"
                    )
                self._connection.execute(
                    """
                    UPDATE effect_compensation
                    SET state = ?, forward_receipt_digest = ?, updated_at_ns = ?
                    WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                    """,
                    (
                        EffectState.COMMITTED.value,
                        receipt,
                        now,
                        current.intent.tenant_id,
                        current.intent.operation_id,
                        current.intent.effect_id,
                    ),
                )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)

    def require_recovery(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        effect_id: str,
        now_ns: int | None = None,
    ) -> EffectRecord:
        now = _now(now_ns)
        with self._lock:
            current = self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)
            if current.state in {EffectState.COMPENSATION_REQUIRED, EffectState.MANUAL_REQUIRED}:
                return current
            if current.state is not EffectState.COMMITTED:
                raise EffectCompensationConflict(
                    f"recovery can only be required after commit, not {current.state.value}"
                )
            target = (
                EffectState.COMPENSATION_REQUIRED
                if current.intent.recovery_mode is RecoveryMode.AUTOMATIC_COMPENSATION
                else EffectState.MANUAL_REQUIRED
            )
            self._connection.execute(
                """
                UPDATE effect_compensation SET state = ?, updated_at_ns = ?
                WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                """,
                (target.value, now, tenant_id, operation_id, effect_id),
            )
        return self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)

    def claim_compensation(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        effect_id: str,
        owner_id: str,
        expected_claim_generation: int,
        now_ns: int | None = None,
    ) -> EffectRecord:
        owner = _text(owner_id, "owner_id")
        expected = _integer(expected_claim_generation, "expected_claim_generation")
        now = _now(now_ns)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)
                if current.intent.recovery_mode is not RecoveryMode.AUTOMATIC_COMPENSATION:
                    raise EffectCompensationConflict("manual-only effect cannot be auto-compensated")
                if current.state not in {EffectState.COMPENSATION_REQUIRED, EffectState.COMPENSATING}:
                    raise EffectCompensationConflict(
                        f"effect cannot be claimed from state {current.state.value}"
                    )
                if current.claim_generation != expected:
                    raise EffectCompensationConflict("stale compensation claim generation")
                if current.claim_generation >= _MAX_INT:
                    raise EffectCompensationError("compensation claim generation exhausted")
                generation = current.claim_generation + 1
                self._connection.execute(
                    """
                    UPDATE effect_compensation
                    SET state = ?, claim_generation = ?, claim_owner = ?, updated_at_ns = ?
                    WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                    """,
                    (
                        EffectState.COMPENSATING.value,
                        generation,
                        owner,
                        now,
                        tenant_id,
                        operation_id,
                        effect_id,
                    ),
                )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)

    def mark_compensated(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        effect_id: str,
        owner_id: str,
        claim_generation: int,
        compensation_receipt_digest: str,
        now_ns: int | None = None,
    ) -> EffectRecord:
        owner = _text(owner_id, "owner_id")
        generation = _integer(claim_generation, "claim_generation", minimum=1)
        receipt = _digest(compensation_receipt_digest, "compensation_receipt_digest")
        now = _now(now_ns)
        with self._lock:
            current = self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)
            if current.state is EffectState.COMPENSATED:
                if current.compensation_receipt_digest == receipt:
                    return current
                raise EffectCompensationConflict("compensation already closed by another receipt")
            if current.state is not EffectState.COMPENSATING:
                raise EffectCompensationConflict("effect is not currently compensating")
            if current.claim_owner != owner or current.claim_generation != generation:
                raise EffectCompensationConflict("stale or foreign compensation claim")
            self._connection.execute(
                """
                UPDATE effect_compensation
                SET state = ?, compensation_receipt_digest = ?, claim_owner = NULL,
                    updated_at_ns = ?
                WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                """,
                (
                    EffectState.COMPENSATED.value,
                    receipt,
                    now,
                    tenant_id,
                    operation_id,
                    effect_id,
                ),
            )
        return self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)

    def mark_manual_resolved(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        effect_id: str,
        resolution_receipt_digest: str,
        now_ns: int | None = None,
    ) -> EffectRecord:
        receipt = _digest(resolution_receipt_digest, "resolution_receipt_digest")
        now = _now(now_ns)
        with self._lock:
            current = self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)
            if current.intent.recovery_mode is not RecoveryMode.MANUAL_RECONCILIATION:
                raise EffectCompensationConflict("automatic effect cannot use manual resolution")
            if current.state is EffectState.MANUAL_RESOLVED:
                if current.resolution_receipt_digest == receipt:
                    return current
                raise EffectCompensationConflict("manual effect already resolved differently")
            if current.state is not EffectState.MANUAL_REQUIRED:
                raise EffectCompensationConflict("manual resolution was not required")
            self._connection.execute(
                """
                UPDATE effect_compensation
                SET state = ?, resolution_receipt_digest = ?, updated_at_ns = ?
                WHERE tenant_id = ? AND operation_id = ? AND effect_id = ?
                """,
                (
                    EffectState.MANUAL_RESOLVED.value,
                    receipt,
                    now,
                    tenant_id,
                    operation_id,
                    effect_id,
                ),
            )
        return self.get(tenant_id=tenant_id, operation_id=operation_id, effect_id=effect_id)

    def in_doubt(self, *, tenant_id: str) -> tuple[EffectRecord, ...]:
        tenant = _text(tenant_id, "tenant_id")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM effect_compensation
                WHERE tenant_id = ? AND state IN (?, ?, ?, ?)
                ORDER BY operation_id, effect_id
                """,
                (
                    tenant,
                    EffectState.COMMITTED.value,
                    EffectState.COMPENSATION_REQUIRED.value,
                    EffectState.COMPENSATING.value,
                    EffectState.MANUAL_REQUIRED.value,
                ),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteEffectCompensationLedger":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

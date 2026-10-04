"""Durable non-idempotent side-effect compensation ledger for hostile gap G015.

The ledger never claims exactly-once semantics for an external system that does
not provide them. Instead it makes the dangerous crash windows explicit:

* a forward action is durably prepared before dispatch;
* after dispatch, missing outcome evidence is ambiguous and is never replayed;
* compensation is only eligible after a confirmed forward effect;
* compensation dispatch has the same ambiguity fence as forward dispatch;
* every transition is compare-and-swap fenced by a durable version;
* restart preserves state, evidence digests, and recovery disposition.

This is a reference coordination authority. Business-specific compensation
handlers live outside this module and must present canonical evidence receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INT64_MAX = (1 << 63) - 1

PREPARED = "prepared"
FORWARD_DISPATCHED = "forward_dispatched"
FORWARD_SUCCEEDED = "forward_succeeded"
FORWARD_NO_EFFECT = "forward_no_effect"
COMPENSATION_REQUIRED = "compensation_required"
COMPENSATION_DISPATCHED = "compensation_dispatched"
COMPENSATED = "compensated"
MANUAL_REVIEW = "manual_review"

TERMINAL_STATES = frozenset({FORWARD_NO_EFFECT, COMPENSATED, MANUAL_REVIEW})
ALL_STATES = frozenset(
    {
        PREPARED,
        FORWARD_DISPATCHED,
        FORWARD_SUCCEEDED,
        FORWARD_NO_EFFECT,
        COMPENSATION_REQUIRED,
        COMPENSATION_DISPATCHED,
        COMPENSATED,
        MANUAL_REVIEW,
    }
)


class CompensationError(RuntimeError):
    """Base compensation-ledger failure."""


class CompensationConflict(CompensationError):
    """The requested transition conflicts with durable state."""


class CompensationCorruption(CompensationError):
    """Persisted compensation state cannot be trusted."""


class AmbiguousExternalOutcome(CompensationError):
    """The external effect outcome must be reconciled, never replayed."""


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CompensationError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise CompensationError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise CompensationError(f"{field} contains control characters")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CompensationError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _INT64_MAX,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise CompensationError(
            f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


@dataclass(frozen=True, slots=True)
class CompensationRecord:
    namespace: str
    tenant_id: str
    operation_id: str
    request_digest: str
    forward_action: str
    compensation_action: str
    state: str
    version: int
    created_order: int
    updated_order: int
    forward_dispatch_digest: str | None
    forward_receipt_digest: str | None
    compensation_reason_digest: str | None
    compensation_dispatch_digest: str | None
    compensation_receipt_digest: str | None
    manual_review_digest: str | None

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "operation_id": self.operation_id,
            "request_digest": self.request_digest,
            "forward_action": self.forward_action,
            "compensation_action": self.compensation_action,
            "state": self.state,
            "version": self.version,
            "created_order": self.created_order,
            "updated_order": self.updated_order,
            "forward_dispatch_digest": self.forward_dispatch_digest,
            "forward_receipt_digest": self.forward_receipt_digest,
            "compensation_reason_digest": self.compensation_reason_digest,
            "compensation_dispatch_digest": self.compensation_dispatch_digest,
            "compensation_receipt_digest": self.compensation_receipt_digest,
            "manual_review_digest": self.manual_review_digest,
        }


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    record: CompensationRecord
    action: str
    auto_dispatch_safe: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "record": self.record.as_dict(),
            "action": self.action,
            "auto_dispatch_safe": self.auto_dispatch_safe,
        }


class SQLiteCompensationLedger:
    """Durable CAS-fenced compensation state machine."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "non_idempotent_compensation",
    ) -> None:
        self.namespace = _text(namespace, "namespace")
        self._connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS compensation_clock (
                    namespace TEXT PRIMARY KEY,
                    order_index INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS compensation_operation (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    forward_action TEXT NOT NULL,
                    compensation_action TEXT NOT NULL,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_order INTEGER NOT NULL,
                    updated_order INTEGER NOT NULL,
                    forward_dispatch_digest TEXT,
                    forward_receipt_digest TEXT,
                    compensation_reason_digest TEXT,
                    compensation_dispatch_digest TEXT,
                    compensation_receipt_digest TEXT,
                    manual_review_digest TEXT,
                    PRIMARY KEY(namespace, tenant_id, operation_id),
                    UNIQUE(namespace, updated_order)
                );
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO compensation_clock(namespace, order_index)
                VALUES (?, 0)
                """,
                (self.namespace,),
            )

    def prepare(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        request_digest: str,
        forward_action: str,
        compensation_action: str,
    ) -> CompensationRecord:
        tenant = _text(tenant_id, "tenant_id")
        operation = _text(operation_id, "operation_id")
        request = _digest(request_digest, "request_digest")
        forward = _text(forward_action, "forward_action")
        compensation = _text(compensation_action, "compensation_action")

        with self._lock:
            self._begin()
            try:
                existing = self._row(tenant, operation)
                if existing is not None:
                    record = self._from_row(existing)
                    if (
                        record.request_digest != request
                        or record.forward_action != forward
                        or record.compensation_action != compensation
                    ):
                        raise CompensationConflict(
                            "operation replay changed compensation identity"
                        )
                    self._commit()
                    return record
                order_index = self._next_order()
                self._connection.execute(
                    """
                    INSERT INTO compensation_operation(
                        namespace, tenant_id, operation_id, request_digest,
                        forward_action, compensation_action, state, version,
                        created_order, updated_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        self.namespace,
                        tenant,
                        operation,
                        request,
                        forward,
                        compensation,
                        PREPARED,
                        order_index,
                        order_index,
                    ),
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.require(tenant_id=tenant, operation_id=operation)

    def mark_forward_dispatched(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        dispatch_digest: str,
    ) -> CompensationRecord:
        return self._transition(
            tenant_id=tenant_id,
            operation_id=operation_id,
            expected_version=expected_version,
            expected_state=PREPARED,
            next_state=FORWARD_DISPATCHED,
            field="forward_dispatch_digest",
            digest=dispatch_digest,
        )

    def record_forward_success(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        receipt_digest: str,
    ) -> CompensationRecord:
        return self._transition(
            tenant_id=tenant_id,
            operation_id=operation_id,
            expected_version=expected_version,
            expected_state=FORWARD_DISPATCHED,
            next_state=FORWARD_SUCCEEDED,
            field="forward_receipt_digest",
            digest=receipt_digest,
        )

    def record_forward_no_effect(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        evidence_digest: str,
    ) -> CompensationRecord:
        """Close a dispatched forward action only with proof it caused no effect."""
        return self._transition(
            tenant_id=tenant_id,
            operation_id=operation_id,
            expected_version=expected_version,
            expected_state=FORWARD_DISPATCHED,
            next_state=FORWARD_NO_EFFECT,
            field="forward_receipt_digest",
            digest=evidence_digest,
        )

    def require_compensation(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        reason_digest: str,
    ) -> CompensationRecord:
        return self._transition(
            tenant_id=tenant_id,
            operation_id=operation_id,
            expected_version=expected_version,
            expected_state=FORWARD_SUCCEEDED,
            next_state=COMPENSATION_REQUIRED,
            field="compensation_reason_digest",
            digest=reason_digest,
        )

    def mark_compensation_dispatched(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        dispatch_digest: str,
    ) -> CompensationRecord:
        return self._transition(
            tenant_id=tenant_id,
            operation_id=operation_id,
            expected_version=expected_version,
            expected_state=COMPENSATION_REQUIRED,
            next_state=COMPENSATION_DISPATCHED,
            field="compensation_dispatch_digest",
            digest=dispatch_digest,
        )

    def record_compensated(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        receipt_digest: str,
    ) -> CompensationRecord:
        return self._transition(
            tenant_id=tenant_id,
            operation_id=operation_id,
            expected_version=expected_version,
            expected_state=COMPENSATION_DISPATCHED,
            next_state=COMPENSATED,
            field="compensation_receipt_digest",
            digest=receipt_digest,
        )

    def mark_manual_review(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        evidence_digest: str,
    ) -> CompensationRecord:
        tenant = _text(tenant_id, "tenant_id")
        operation = _text(operation_id, "operation_id")
        version = _integer(expected_version, "expected_version", minimum=1)
        evidence = _digest(evidence_digest, "evidence_digest")
        with self._lock:
            self._begin()
            try:
                row = self._row(tenant, operation)
                if row is None:
                    raise CompensationConflict("operation does not exist")
                current = self._from_row(row)
                if current.version != version:
                    raise CompensationConflict("operation version changed")
                if current.terminal:
                    raise CompensationConflict("terminal operation cannot move")
                updated = self._cas_update(
                    current=current,
                    next_state=MANUAL_REVIEW,
                    field="manual_review_digest",
                    digest=evidence,
                )
                self._commit()
                return updated
            except Exception:
                self._rollback()
                raise

    def require(
        self,
        *,
        tenant_id: str,
        operation_id: str,
    ) -> CompensationRecord:
        tenant = _text(tenant_id, "tenant_id")
        operation = _text(operation_id, "operation_id")
        with self._lock:
            row = self._row(tenant, operation)
        if row is None:
            raise CompensationConflict("operation does not exist")
        return self._from_row(row)

    def recovery_candidates(
        self,
        *,
        tenant_id: str | None = None,
    ) -> tuple[RecoveryCandidate, ...]:
        tenant = None if tenant_id is None else _text(tenant_id, "tenant_id")
        with self._lock:
            if tenant is None:
                rows = self._connection.execute(
                    """
                    SELECT * FROM compensation_operation
                    WHERE namespace = ?
                    ORDER BY updated_order ASC
                    """,
                    (self.namespace,),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM compensation_operation
                    WHERE namespace = ? AND tenant_id = ?
                    ORDER BY updated_order ASC
                    """,
                    (self.namespace, tenant),
                ).fetchall()
        candidates: list[RecoveryCandidate] = []
        for row in rows:
            record = self._from_row(row)
            if record.terminal:
                continue
            action, safe = self._recovery_action(record.state)
            candidates.append(RecoveryCandidate(record, action, safe))
        return tuple(candidates)

    def assert_safe_to_dispatch_forward(
        self,
        record: CompensationRecord,
    ) -> None:
        if record.state != PREPARED:
            if record.state == FORWARD_DISPATCHED:
                raise AmbiguousExternalOutcome(
                    "forward action was already dispatched; reconcile outcome"
                )
            raise CompensationConflict(
                f"forward dispatch is not legal from {record.state}"
            )

    def assert_safe_to_dispatch_compensation(
        self,
        record: CompensationRecord,
    ) -> None:
        if record.state != COMPENSATION_REQUIRED:
            if record.state == COMPENSATION_DISPATCHED:
                raise AmbiguousExternalOutcome(
                    "compensation was already dispatched; reconcile outcome"
                )
            raise CompensationConflict(
                f"compensation dispatch is not legal from {record.state}"
            )

    def card(self) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN state = ? THEN 1 ELSE 0 END) AS ambiguous_forward,
                       SUM(CASE WHEN state = ? THEN 1 ELSE 0 END) AS ambiguous_compensation
                FROM compensation_operation
                WHERE namespace = ?
                """,
                (FORWARD_DISPATCHED, COMPENSATION_DISPATCHED, self.namespace),
            ).fetchone()
        return {
            "kind": "non_idempotent_compensation_ledger",
            "gap": "G015",
            "law": "prepare-dispatch-reconcile-compensate-no-blind-replay",
            "operation_count": int(row["total"] or 0),
            "ambiguous_forward_count": int(row["ambiguous_forward"] or 0),
            "ambiguous_compensation_count": int(
                row["ambiguous_compensation"] or 0
            ),
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _transition(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        expected_version: int,
        expected_state: str,
        next_state: str,
        field: str,
        digest: str,
    ) -> CompensationRecord:
        tenant = _text(tenant_id, "tenant_id")
        operation = _text(operation_id, "operation_id")
        version = _integer(expected_version, "expected_version", minimum=1)
        evidence = _digest(digest, field)
        with self._lock:
            self._begin()
            try:
                row = self._row(tenant, operation)
                if row is None:
                    raise CompensationConflict("operation does not exist")
                current = self._from_row(row)
                if current.version != version:
                    raise CompensationConflict("operation version changed")
                if current.state != expected_state:
                    if (
                        current.state in {FORWARD_DISPATCHED, COMPENSATION_DISPATCHED}
                        and current.state != expected_state
                    ):
                        raise AmbiguousExternalOutcome(
                            "external dispatch state requires reconciliation"
                        )
                    raise CompensationConflict(
                        f"expected state {expected_state}, got {current.state}"
                    )
                updated = self._cas_update(
                    current=current,
                    next_state=next_state,
                    field=field,
                    digest=evidence,
                )
                self._commit()
                return updated
            except Exception:
                self._rollback()
                raise

    def _cas_update(
        self,
        *,
        current: CompensationRecord,
        next_state: str,
        field: str,
        digest: str,
    ) -> CompensationRecord:
        if next_state not in ALL_STATES:
            raise CompensationError("invalid next state")
        allowed_fields = {
            "forward_dispatch_digest",
            "forward_receipt_digest",
            "compensation_reason_digest",
            "compensation_dispatch_digest",
            "compensation_receipt_digest",
            "manual_review_digest",
        }
        if field not in allowed_fields:
            raise CompensationError("invalid evidence field")
        next_version = current.version + 1
        if next_version > _INT64_MAX:
            raise CompensationCorruption("operation version exhausted")
        order_index = self._next_order()
        cursor = self._connection.execute(
            f"""
            UPDATE compensation_operation
            SET state = ?, version = ?, updated_order = ?, {field} = ?
            WHERE namespace = ? AND tenant_id = ? AND operation_id = ?
              AND state = ? AND version = ?
            """,
            (
                next_state,
                next_version,
                order_index,
                digest,
                self.namespace,
                current.tenant_id,
                current.operation_id,
                current.state,
                current.version,
            ),
        )
        if cursor.rowcount != 1:
            raise CompensationConflict("transition lost compare-and-swap race")
        row = self._row(current.tenant_id, current.operation_id)
        if row is None:
            raise CompensationCorruption("updated operation disappeared")
        return self._from_row(row)

    def _next_order(self) -> int:
        row = self._connection.execute(
            """
            SELECT order_index FROM compensation_clock
            WHERE namespace = ?
            """,
            (self.namespace,),
        ).fetchone()
        if row is None:
            raise CompensationCorruption("compensation clock is missing")
        prior = _integer(
            row["order_index"], "persisted order_index", minimum=0
        )
        if prior >= _INT64_MAX:
            raise CompensationCorruption("compensation clock exhausted")
        next_order = prior + 1
        cursor = self._connection.execute(
            """
            UPDATE compensation_clock
            SET order_index = ?
            WHERE namespace = ? AND order_index = ?
            """,
            (next_order, self.namespace, prior),
        )
        if cursor.rowcount != 1:
            raise CompensationConflict("compensation clock lost race")
        return next_order

    def _row(self, tenant_id: str, operation_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM compensation_operation
            WHERE namespace = ? AND tenant_id = ? AND operation_id = ?
            """,
            (self.namespace, tenant_id, operation_id),
        ).fetchone()

    def _from_row(self, row: sqlite3.Row) -> CompensationRecord:
        try:
            state = _text(row["state"], "persisted state")
            if state not in ALL_STATES:
                raise CompensationError("persisted state is unknown")
            optional = {}
            for field in (
                "forward_dispatch_digest",
                "forward_receipt_digest",
                "compensation_reason_digest",
                "compensation_dispatch_digest",
                "compensation_receipt_digest",
                "manual_review_digest",
            ):
                value = row[field]
                optional[field] = (
                    None if value is None else _digest(value, f"persisted {field}")
                )
            record = CompensationRecord(
                namespace=self.namespace,
                tenant_id=_text(row["tenant_id"], "persisted tenant_id"),
                operation_id=_text(
                    row["operation_id"], "persisted operation_id"
                ),
                request_digest=_digest(
                    row["request_digest"], "persisted request_digest"
                ),
                forward_action=_text(
                    row["forward_action"], "persisted forward_action"
                ),
                compensation_action=_text(
                    row["compensation_action"],
                    "persisted compensation_action",
                ),
                state=state,
                version=_integer(
                    row["version"], "persisted version", minimum=1
                ),
                created_order=_integer(
                    row["created_order"],
                    "persisted created_order",
                    minimum=1,
                ),
                updated_order=_integer(
                    row["updated_order"],
                    "persisted updated_order",
                    minimum=1,
                ),
                **optional,
            )
        except CompensationError as exc:
            raise CompensationCorruption(
                "persisted compensation operation is invalid"
            ) from exc
        if record.updated_order < record.created_order:
            raise CompensationCorruption("operation order regressed")
        self._validate_state_evidence(record)
        return record

    def _validate_state_evidence(self, record: CompensationRecord) -> None:
        if record.state != PREPARED and record.forward_dispatch_digest is None:
            raise CompensationCorruption(
                "post-prepare state lacks forward dispatch evidence"
            )
        if record.state in {
            FORWARD_SUCCEEDED,
            COMPENSATION_REQUIRED,
            COMPENSATION_DISPATCHED,
            COMPENSATED,
        } and record.forward_receipt_digest is None:
            raise CompensationCorruption(
                "confirmed forward effect lacks receipt"
            )
        if record.state in {
            COMPENSATION_REQUIRED,
            COMPENSATION_DISPATCHED,
            COMPENSATED,
        } and record.compensation_reason_digest is None:
            raise CompensationCorruption(
                "compensation state lacks reason evidence"
            )
        if record.state in {
            COMPENSATION_DISPATCHED,
            COMPENSATED,
        } and record.compensation_dispatch_digest is None:
            raise CompensationCorruption(
                "compensation state lacks dispatch evidence"
            )
        if (
            record.state == COMPENSATED
            and record.compensation_receipt_digest is None
        ):
            raise CompensationCorruption(
                "compensated state lacks receipt evidence"
            )
        if record.state == MANUAL_REVIEW and record.manual_review_digest is None:
            raise CompensationCorruption(
                "manual review state lacks evidence"
            )

    @staticmethod
    def _recovery_action(state: str) -> tuple[str, bool]:
        if state == PREPARED:
            return ("dispatch_forward", True)
        if state == FORWARD_DISPATCHED:
            return ("reconcile_forward_outcome", False)
        if state == FORWARD_SUCCEEDED:
            return ("await_workflow_decision", False)
        if state == COMPENSATION_REQUIRED:
            return ("dispatch_compensation", True)
        if state == COMPENSATION_DISPATCHED:
            return ("reconcile_compensation_outcome", False)
        if state == MANUAL_REVIEW:
            return ("manual_review", False)
        raise CompensationCorruption(
            f"no recovery action for nonterminal state {state}"
        )

    def _begin(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._connection.execute("COMMIT")

    def _rollback(self) -> None:
        self._connection.execute("ROLLBACK")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteCompensationLedger":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

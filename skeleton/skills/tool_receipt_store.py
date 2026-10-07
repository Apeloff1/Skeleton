"""Restart-safe reservation and receipt authority for tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

from skeleton.skills.tool_contract import (
    ToolExecutionRequest,
    ToolExecutionReceipt,
    ToolExecutionStatus,
)


class ToolReceiptStoreError(RuntimeError):
    """Base durable tool receipt store failure."""


class ToolReceiptConflict(ToolReceiptStoreError):
    """Idempotency key was reused with incompatible tool intent."""


@dataclass(frozen=True, slots=True)
class ToolReservation:
    status: str
    receipt: ToolExecutionReceipt | None = None

    def __post_init__(self) -> None:
        if self.status not in {"owner", "committed", "in_doubt"}:
            raise ValueError("invalid tool reservation status")
        if self.status == "committed" and self.receipt is None:
            raise ValueError("committed reservation requires receipt")
        if self.status != "committed" and self.receipt is not None:
            raise ValueError("non-committed reservation cannot carry receipt")


class ToolReconciliationOutcome(str, Enum):
    NO_EFFECT = "no_effect"
    COMMITTED = "committed"


@dataclass(frozen=True, slots=True)
class ToolReconciliationReceipt:
    reconciliation_id: str
    tenant_id: str
    operation_id: str
    idempotency_key: str
    request_id: str
    tool_id: str
    arguments_digest: str
    outcome: ToolReconciliationOutcome
    evidence_ref: str
    reconciled_at: datetime
    execution_id: str | None = None
    turn_id: str | None = None
    call_id: str | None = None
    receipt_id: str | None = None

    def __post_init__(self) -> None:
        for name, maximum in (
            ("reconciliation_id", 64),
            ("tenant_id", 512),
            ("operation_id", 512),
            ("idempotency_key", 1024),
            ("request_id", 512),
            ("tool_id", 128),
            ("arguments_digest", 64),
            ("evidence_ref", 2048),
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
            normalized = value.strip()
            if normalized != value or len(normalized) > maximum:
                raise ValueError(f"{name} is invalid")
        if len(self.reconciliation_id) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.reconciliation_id
        ):
            raise ValueError("reconciliation_id must be lowercase sha256")
        if len(self.arguments_digest) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.arguments_digest
        ):
            raise ValueError("arguments_digest must be lowercase sha256")
        if not isinstance(self.outcome, ToolReconciliationOutcome):
            object.__setattr__(
                self,
                "outcome",
                ToolReconciliationOutcome(str(self.outcome)),
            )
        instant = self.reconciled_at
        if (
            not isinstance(instant, datetime)
            or instant.tzinfo is None
            or instant.utcoffset() is None
        ):
            raise ValueError("reconciled_at must be timezone-aware")
        object.__setattr__(
            self,
            "reconciled_at",
            instant.astimezone(timezone.utc),
        )
        lineage = (self.execution_id, self.turn_id, self.call_id)
        if any(value is not None for value in lineage) and not all(
            value is not None for value in lineage
        ):
            raise ValueError(
                "execution_id, turn_id and call_id must be supplied together"
            )
        for name in ("execution_id", "turn_id", "call_id", "receipt_id"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{name} must be non-empty when supplied")
        if (
            self.outcome is ToolReconciliationOutcome.COMMITTED
            and self.receipt_id is None
        ):
            raise ValueError("committed reconciliation requires receipt_id")
        if (
            self.outcome is ToolReconciliationOutcome.NO_EFFECT
            and self.receipt_id is not None
        ):
            raise ValueError("no-effect reconciliation cannot carry receipt_id")

    @property
    def reference(self) -> str:
        return "tool-reconciliation:" + self.reconciliation_id

    def as_dict(self) -> dict[str, object]:
        return {
            "reconciliation_id": self.reconciliation_id,
            "tenant_id": self.tenant_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "turn_id": self.turn_id,
            "call_id": self.call_id,
            "idempotency_key": self.idempotency_key,
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "arguments_digest": self.arguments_digest,
            "outcome": self.outcome.value,
            "evidence_ref": self.evidence_ref,
            "receipt_id": self.receipt_id,
            "reconciled_at": self.reconciled_at.isoformat(),
        }


def _reconciliation_id(
    request: ToolExecutionRequest,
    outcome: ToolReconciliationOutcome,
    evidence_ref: str,
    receipt_id: str | None,
) -> str:
    material = "\x1f".join(
        (
            request.tenant_id,
            request.operation_id,
            request.execution_id or "",
            request.turn_id or "",
            request.call_id or "",
            request.idempotency_key,
            request.request_id,
            request.tool_id,
            request.arguments_digest,
            outcome.value,
            evidence_ref,
            receipt_id or "",
        )
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _parse_time(raw: object, field: str) -> datetime:
    if not isinstance(raw, str):
        raise ToolReceiptStoreError(f"{field} must be ISO text")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ToolReceiptStoreError(f"{field} is invalid") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ToolReceiptStoreError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _receipt_from_json(raw: object) -> ToolExecutionReceipt:
    if not isinstance(raw, str):
        raise ToolReceiptStoreError("receipt_json must be text")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolReceiptStoreError("receipt_json is invalid") from exc
    if not isinstance(payload, dict):
        raise ToolReceiptStoreError("receipt_json must be an object")
    postcondition_verified = payload.get("postcondition_verified", False)
    if not isinstance(postcondition_verified, bool):
        raise ToolReceiptStoreError("postcondition_verified must be boolean")
    return ToolExecutionReceipt(
        receipt_id=payload["receipt_id"],
        request_id=payload["request_id"],
        operation_id=payload["operation_id"],
        execution_id=payload.get("execution_id"),
        turn_id=payload.get("turn_id"),
        call_id=payload.get("call_id"),
        tenant_id=payload["tenant_id"],
        tool_id=payload["tool_id"],
        idempotency_key=payload["idempotency_key"],
        arguments_digest=payload["arguments_digest"],
        status=ToolExecutionStatus(payload["status"]),
        started_at=_parse_time(payload["started_at"], "started_at"),
        finished_at=_parse_time(payload["finished_at"], "finished_at"),
        result_ref=payload.get("result_ref"),
        error_code=payload.get("error_code"),
        approval_ref=payload.get("approval_ref"),
        compensation_ref=payload.get("compensation_ref"),
        data_class=payload.get("data_class", "internal"),
        transfer_purpose=payload.get(
            "transfer_purpose",
            "tool-execution",
        ),
        governance_decision_ref=payload.get(
            "governance_decision_ref"
        ),
        postcondition_verified=postcondition_verified,
        metered_tool_calls=int(payload.get("metered_tool_calls", 1)),
        schema_version=int(payload.get("schema_version", 1)),
    )


class SQLiteToolReceiptStore:
    """Durable exactly-once guard for tool effects.

    A pending reservation is intentionally treated as in-doubt after process
    loss. The runtime must not execute the side effect again until an external
    reconciliation process resolves that reservation.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "tool_execution",
    ) -> None:
        normalized = str(namespace).strip()
        if not normalized:
            raise ValueError("namespace must not be empty")
        self.namespace = normalized
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_execution_receipt (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    execution_id TEXT,
                    turn_id TEXT,
                    call_id TEXT,
                    idempotency_key TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    arguments_digest TEXT NOT NULL,
                    data_class TEXT NOT NULL DEFAULT 'internal',
                    transfer_purpose TEXT NOT NULL DEFAULT 'tool-execution',
                    state TEXT NOT NULL,
                    reserved_at TEXT NOT NULL,
                    receipt_json TEXT,
                    completed_at TEXT,
                    PRIMARY KEY(
                        namespace, tenant_id, operation_id, idempotency_key
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_tool_execution_pending
                ON tool_execution_receipt(namespace, state, reserved_at);

                CREATE TABLE IF NOT EXISTS tool_execution_reconciliation (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    reconciliation_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    execution_id TEXT,
                    turn_id TEXT,
                    call_id TEXT,
                    tool_id TEXT NOT NULL,
                    arguments_digest TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    receipt_id TEXT,
                    reconciled_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, reconciliation_id)
                );

                CREATE INDEX IF NOT EXISTS idx_tool_reconciliation_operation
                ON tool_execution_reconciliation(
                    namespace, tenant_id, operation_id,
                    idempotency_key, reconciled_at
                );
                """
            )
            existing_columns = {
                str(row["name"])
                for row in self._connection.execute(
                    "PRAGMA table_info(tool_execution_receipt)"
                ).fetchall()
            }
            for column in ("execution_id", "turn_id", "call_id"):
                if column not in existing_columns:
                    self._connection.execute(
                        f"ALTER TABLE tool_execution_receipt ADD COLUMN {column} TEXT"
                    )
            if "data_class" not in existing_columns:
                self._connection.execute(
                    "ALTER TABLE tool_execution_receipt "
                    "ADD COLUMN data_class TEXT NOT NULL DEFAULT 'internal'"
                )
            if "transfer_purpose" not in existing_columns:
                self._connection.execute(
                    "ALTER TABLE tool_execution_receipt "
                    "ADD COLUMN transfer_purpose TEXT NOT NULL "
                    "DEFAULT 'tool-execution'"
                )

    def reserve(
        self,
        request: ToolExecutionRequest,
        *,
        now: datetime | None = None,
    ) -> ToolReservation:
        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        instant = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
        key = (
            self.namespace,
            request.tenant_id,
            request.operation_id,
            request.idempotency_key,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM tool_execution_receipt
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                    """,
                    key,
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        """
                        INSERT INTO tool_execution_receipt(
                            namespace, tenant_id, operation_id,
                            execution_id, turn_id, call_id, idempotency_key,
                            request_id, tool_id, arguments_digest,
                            data_class, transfer_purpose, state,
                            reserved_at, receipt_json, completed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)
                        """,
                        (
                            self.namespace,
                            request.tenant_id,
                            request.operation_id,
                            request.execution_id,
                            request.turn_id,
                            request.call_id,
                            request.idempotency_key,
                            request.request_id,
                            request.tool_id,
                            request.arguments_digest,
                            request.data_class,
                            request.transfer_purpose,
                            instant.isoformat(),
                        ),
                    )
                    self._connection.execute("COMMIT")
                    return ToolReservation(status="owner")

                if (
                    row["tool_id"] != request.tool_id
                    or row["arguments_digest"] != request.arguments_digest
                    or row["execution_id"] != request.execution_id
                    or row["turn_id"] != request.turn_id
                    or row["call_id"] != request.call_id
                    or row["data_class"] != request.data_class
                    or row["transfer_purpose"] != request.transfer_purpose
                ):
                    raise ToolReceiptConflict(
                        "idempotency key replayed with different tool or arguments, lineage, or privacy context"
                    )
                if row["state"] == "committed":
                    receipt = _receipt_from_json(row["receipt_json"])
                    self._connection.execute("COMMIT")
                    return ToolReservation(
                        status="committed",
                        receipt=receipt,
                    )
                if row["state"] != "pending":
                    raise ToolReceiptStoreError(
                        "durable tool reservation state is corrupt"
                    )
                self._connection.execute("COMMIT")
                return ToolReservation(status="in_doubt")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def commit(
        self,
        request: ToolExecutionRequest,
        receipt: ToolExecutionReceipt,
        *,
        now: datetime | None = None,
    ) -> ToolExecutionReceipt:
        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        if not isinstance(receipt, ToolExecutionReceipt):
            raise TypeError("receipt must be ToolExecutionReceipt")
        if (
            receipt.tenant_id != request.tenant_id
            or receipt.operation_id != request.operation_id
            or receipt.execution_id != request.execution_id
            or receipt.turn_id != request.turn_id
            or receipt.call_id != request.call_id
            or receipt.tool_id != request.tool_id
            or receipt.idempotency_key != request.idempotency_key
            or receipt.arguments_digest != request.arguments_digest
            or receipt.data_class != request.data_class
            or receipt.transfer_purpose != request.transfer_purpose
        ):
            raise ToolReceiptConflict(
                "receipt does not match durable tool reservation"
            )
        instant = datetime.now(timezone.utc) if now is None else now.astimezone(timezone.utc)
        payload = json.dumps(
            receipt.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM tool_execution_receipt
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                    """,
                    (
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                    ),
                ).fetchone()
                if row is None:
                    raise ToolReceiptStoreError(
                        "tool receipt cannot commit without reservation"
                    )
                if (
                    row["tool_id"] != request.tool_id
                    or row["arguments_digest"] != request.arguments_digest
                    or row["execution_id"] != request.execution_id
                    or row["turn_id"] != request.turn_id
                    or row["call_id"] != request.call_id
                    or row["data_class"] != request.data_class
                    or row["transfer_purpose"] != request.transfer_purpose
                ):
                    raise ToolReceiptConflict(
                        "durable reservation does not match receipt"
                    )
                if row["state"] == "committed":
                    existing = _receipt_from_json(row["receipt_json"])
                    if existing != receipt:
                        raise ToolReceiptConflict(
                            "durable receipt already committed differently"
                        )
                    self._connection.execute("COMMIT")
                    return existing
                cursor = self._connection.execute(
                    """
                    UPDATE tool_execution_receipt
                    SET state = 'committed',
                        receipt_json = ?,
                        completed_at = ?
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                      AND state = 'pending'
                    """,
                    (
                        payload,
                        instant.isoformat(),
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ToolReceiptConflict(
                        "durable tool reservation changed before commit"
                    )
                self._connection.execute("COMMIT")
                return receipt
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> ToolReservation | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM tool_execution_receipt
                WHERE namespace = ?
                  AND tenant_id = ?
                  AND operation_id = ?
                  AND idempotency_key = ?
                """,
                (
                    self.namespace,
                    tenant_id,
                    operation_id,
                    idempotency_key,
                ),
            ).fetchone()
            if row is None:
                return None
            if row["state"] == "committed":
                return ToolReservation(
                    status="committed",
                    receipt=_receipt_from_json(row["receipt_json"]),
                )
            if row["state"] == "pending":
                return ToolReservation(status="in_doubt")
            raise ToolReceiptStoreError(
                "durable tool reservation state is corrupt"
            )

    @staticmethod
    def _assert_request_matches_row(
        row: sqlite3.Row,
        request: ToolExecutionRequest,
    ) -> None:
        if (
            row["tool_id"] != request.tool_id
            or row["arguments_digest"] != request.arguments_digest
            or row["execution_id"] != request.execution_id
            or row["turn_id"] != request.turn_id
            or row["call_id"] != request.call_id
            or row["data_class"] != request.data_class
            or row["transfer_purpose"] != request.transfer_purpose
        ):
            raise ToolReceiptConflict(
                "durable reservation does not match reconciliation request"
            )

    @staticmethod
    def _reconciliation_from_row(
        row: sqlite3.Row,
    ) -> ToolReconciliationReceipt:
        return ToolReconciliationReceipt(
            reconciliation_id=row["reconciliation_id"],
            tenant_id=row["tenant_id"],
            operation_id=row["operation_id"],
            execution_id=row["execution_id"],
            turn_id=row["turn_id"],
            call_id=row["call_id"],
            idempotency_key=row["idempotency_key"],
            request_id=row["request_id"],
            tool_id=row["tool_id"],
            arguments_digest=row["arguments_digest"],
            outcome=ToolReconciliationOutcome(row["outcome"]),
            evidence_ref=row["evidence_ref"],
            receipt_id=row["receipt_id"],
            reconciled_at=_parse_time(
                row["reconciled_at"],
                "reconciled_at",
            ),
        )

    def reconciliation(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> ToolReconciliationReceipt | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM tool_execution_reconciliation
                WHERE namespace = ?
                  AND tenant_id = ?
                  AND operation_id = ?
                  AND idempotency_key = ?
                ORDER BY reconciled_at DESC, reconciliation_id DESC
                LIMIT 1
                """,
                (
                    self.namespace,
                    tenant_id,
                    operation_id,
                    idempotency_key,
                ),
            ).fetchone()
        return (
            None
            if row is None
            else self._reconciliation_from_row(row)
        )

    def resolve_no_effect(
        self,
        request: ToolExecutionRequest,
        *,
        evidence_ref: str,
        now: datetime | None = None,
    ) -> ToolReconciliationReceipt:
        """Release one in-doubt fence only after durable no-effect evidence."""

        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        evidence = str(evidence_ref).strip()
        if not evidence:
            raise ValueError("evidence_ref must be non-empty")
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        receipt = ToolReconciliationReceipt(
            reconciliation_id=_reconciliation_id(
                request,
                ToolReconciliationOutcome.NO_EFFECT,
                evidence,
                None,
            ),
            tenant_id=request.tenant_id,
            operation_id=request.operation_id,
            execution_id=request.execution_id,
            turn_id=request.turn_id,
            call_id=request.call_id,
            idempotency_key=request.idempotency_key,
            request_id=request.request_id,
            tool_id=request.tool_id,
            arguments_digest=request.arguments_digest,
            outcome=ToolReconciliationOutcome.NO_EFFECT,
            evidence_ref=evidence,
            receipt_id=None,
            reconciled_at=instant,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    """
                    SELECT * FROM tool_execution_reconciliation
                    WHERE namespace = ? AND reconciliation_id = ?
                    """,
                    (self.namespace, receipt.reconciliation_id),
                ).fetchone()

                row = self._connection.execute(
                    """
                    SELECT * FROM tool_execution_receipt
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                    """,
                    (
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                    ),
                ).fetchone()
                if existing is not None:
                    resolved = self._reconciliation_from_row(existing)
                    if row is None:
                        self._connection.execute("COMMIT")
                        return resolved
                    raise ToolReceiptConflict(
                        "reconciliation evidence was already consumed by an earlier reservation"
                    )
                if row is None:
                    raise ToolReceiptStoreError(
                        "no in-doubt reservation exists to reconcile"
                    )
                self._assert_request_matches_row(row, request)
                if row["state"] == "committed":
                    raise ToolReceiptConflict(
                        "committed tool execution cannot reconcile as no-effect"
                    )
                if row["state"] != "pending":
                    raise ToolReceiptStoreError(
                        "durable tool reservation state is corrupt"
                    )

                self._connection.execute(
                    """
                    INSERT INTO tool_execution_reconciliation(
                        namespace, tenant_id, operation_id,
                        idempotency_key, reconciliation_id,
                        request_id, execution_id, turn_id, call_id,
                        tool_id, arguments_digest, outcome,
                        evidence_ref, receipt_id, reconciled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        receipt.tenant_id,
                        receipt.operation_id,
                        receipt.idempotency_key,
                        receipt.reconciliation_id,
                        receipt.request_id,
                        receipt.execution_id,
                        receipt.turn_id,
                        receipt.call_id,
                        receipt.tool_id,
                        receipt.arguments_digest,
                        receipt.outcome.value,
                        receipt.evidence_ref,
                        receipt.receipt_id,
                        receipt.reconciled_at.isoformat(),
                    ),
                )
                cursor = self._connection.execute(
                    """
                    DELETE FROM tool_execution_receipt
                    WHERE namespace = ?
                      AND tenant_id = ?
                      AND operation_id = ?
                      AND idempotency_key = ?
                      AND state = 'pending'
                    """,
                    (
                        self.namespace,
                        request.tenant_id,
                        request.operation_id,
                        request.idempotency_key,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ToolReceiptConflict(
                        "in-doubt reservation changed during reconciliation"
                    )
                self._connection.execute("COMMIT")
                return receipt
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def resolve_committed(
        self,
        request: ToolExecutionRequest,
        receipt: ToolExecutionReceipt,
        *,
        evidence_ref: str,
        now: datetime | None = None,
    ) -> ToolReconciliationReceipt:
        """Confirm an in-doubt effect by committing its canonical receipt."""

        if not isinstance(request, ToolExecutionRequest):
            raise TypeError("request must be ToolExecutionRequest")
        if not isinstance(receipt, ToolExecutionReceipt):
            raise TypeError("receipt must be ToolExecutionReceipt")
        evidence = str(evidence_ref).strip()
        if not evidence:
            raise ValueError("evidence_ref must be non-empty")
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        committed = self.commit(
            request,
            receipt,
            now=instant,
        )
        reconciliation = ToolReconciliationReceipt(
            reconciliation_id=_reconciliation_id(
                request,
                ToolReconciliationOutcome.COMMITTED,
                evidence,
                committed.receipt_id,
            ),
            tenant_id=request.tenant_id,
            operation_id=request.operation_id,
            execution_id=request.execution_id,
            turn_id=request.turn_id,
            call_id=request.call_id,
            idempotency_key=request.idempotency_key,
            request_id=request.request_id,
            tool_id=request.tool_id,
            arguments_digest=request.arguments_digest,
            outcome=ToolReconciliationOutcome.COMMITTED,
            evidence_ref=evidence,
            receipt_id=committed.receipt_id,
            reconciled_at=instant,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    """
                    SELECT * FROM tool_execution_reconciliation
                    WHERE namespace = ? AND reconciliation_id = ?
                    """,
                    (self.namespace, reconciliation.reconciliation_id),
                ).fetchone()
                if existing is not None:
                    resolved = self._reconciliation_from_row(existing)
                    self._connection.execute("COMMIT")
                    return resolved
                self._connection.execute(
                    """
                    INSERT INTO tool_execution_reconciliation(
                        namespace, tenant_id, operation_id,
                        idempotency_key, reconciliation_id,
                        request_id, execution_id, turn_id, call_id,
                        tool_id, arguments_digest, outcome,
                        evidence_ref, receipt_id, reconciled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        reconciliation.tenant_id,
                        reconciliation.operation_id,
                        reconciliation.idempotency_key,
                        reconciliation.reconciliation_id,
                        reconciliation.request_id,
                        reconciliation.execution_id,
                        reconciliation.turn_id,
                        reconciliation.call_id,
                        reconciliation.tool_id,
                        reconciliation.arguments_digest,
                        reconciliation.outcome.value,
                        reconciliation.evidence_ref,
                        reconciliation.receipt_id,
                        reconciliation.reconciled_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return reconciliation
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def pending(self) -> tuple[tuple[str, str, str], ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT tenant_id, operation_id, idempotency_key
                FROM tool_execution_receipt
                WHERE namespace = ? AND state = 'pending'
                ORDER BY reserved_at ASC
                """,
                (self.namespace,),
            ).fetchall()
            return tuple(
                (
                    row["tenant_id"],
                    row["operation_id"],
                    row["idempotency_key"],
                )
                for row in rows
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "SQLiteToolReceiptStore",
    "ToolReceiptConflict",
    "ToolReceiptStoreError",
    "ToolReconciliationOutcome",
    "ToolReconciliationReceipt",
    "ToolReservation",
]

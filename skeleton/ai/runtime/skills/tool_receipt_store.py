"""Restart-safe reservation and receipt authority for tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    return ToolExecutionReceipt(
        receipt_id=payload["receipt_id"],
        request_id=payload["request_id"],
        operation_id=payload["operation_id"],
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
                    idempotency_key TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    arguments_digest TEXT NOT NULL,
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
                """
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
                            namespace, tenant_id, operation_id, idempotency_key,
                            request_id, tool_id, arguments_digest, state,
                            reserved_at, receipt_json, completed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)
                        """,
                        (
                            *key,
                            request.request_id,
                            request.tool_id,
                            request.arguments_digest,
                            instant.isoformat(),
                        ),
                    )
                    self._connection.execute("COMMIT")
                    return ToolReservation(status="owner")

                if (
                    row["tool_id"] != request.tool_id
                    or row["arguments_digest"] != request.arguments_digest
                ):
                    raise ToolReceiptConflict(
                        "idempotency key replayed with different tool or arguments"
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
            or receipt.tool_id != request.tool_id
            or receipt.idempotency_key != request.idempotency_key
            or receipt.arguments_digest != request.arguments_digest
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
    "ToolReservation",
]

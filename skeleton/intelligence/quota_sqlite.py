"""Durable SQLite tenant-quota ledger.

This is the multi-process and restart-safe implementation of the quota contract
in skeleton.intelligence.quota. Every mutating operation uses BEGIN IMMEDIATE so
workers sharing the same durable SQLite file serialize quota admission before
checking cumulative usage and concurrency.

The file is a portable durable reference backend. A distributed database may
replace it in multi-host deployments only if it preserves the same idempotency,
fencing, restart, and race invariants.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from typing import Iterator

from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.quota import (
    QuotaCompletion,
    QuotaConflict,
    QuotaError,
    QuotaExceeded,
    QuotaReservation,
    QuotaUsage,
    TenantQuota,
    _finite_nonnegative,
    _quota_excess,
    _required_id,
    _reservation_id,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenant_quota (
    tenant_id TEXT PRIMARY KEY,
    window_id TEXT NOT NULL,
    max_operations INTEGER NOT NULL,
    max_input_tokens INTEGER NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    max_cost_usd REAL NOT NULL,
    max_tool_calls INTEGER NOT NULL,
    max_artifact_bytes INTEGER NOT NULL,
    max_concurrent_operations INTEGER NOT NULL,
    committed_operations INTEGER NOT NULL DEFAULT 0,
    committed_input_tokens INTEGER NOT NULL DEFAULT 0,
    committed_output_tokens INTEGER NOT NULL DEFAULT 0,
    committed_cost_usd REAL NOT NULL DEFAULT 0,
    committed_tool_calls INTEGER NOT NULL DEFAULT 0,
    committed_artifact_bytes INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quota_reservations (
    reservation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    window_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    estimate_operations INTEGER NOT NULL,
    estimate_input_tokens INTEGER NOT NULL,
    estimate_output_tokens INTEGER NOT NULL,
    estimate_cost_usd REAL NOT NULL,
    estimate_tool_calls INTEGER NOT NULL,
    estimate_artifact_bytes INTEGER NOT NULL,
    reserved_at REAL NOT NULL,
    UNIQUE (tenant_id, operation_id)
);

CREATE INDEX IF NOT EXISTS idx_quota_reservations_tenant
ON quota_reservations (tenant_id);

CREATE TABLE IF NOT EXISTS quota_completions (
    reservation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    window_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    estimate_operations INTEGER NOT NULL,
    estimate_input_tokens INTEGER NOT NULL,
    estimate_output_tokens INTEGER NOT NULL,
    estimate_cost_usd REAL NOT NULL,
    estimate_tool_calls INTEGER NOT NULL,
    estimate_artifact_bytes INTEGER NOT NULL,
    actual_operations INTEGER NOT NULL,
    actual_input_tokens INTEGER NOT NULL,
    actual_output_tokens INTEGER NOT NULL,
    actual_cost_usd REAL NOT NULL,
    actual_tool_calls INTEGER NOT NULL,
    actual_artifact_bytes INTEGER NOT NULL,
    overrun_dimensions TEXT NOT NULL,
    completed_at REAL NOT NULL,
    UNIQUE (tenant_id, operation_id)
);
"""


class SqliteTenantQuotaLedger:
    """Restart-safe, multi-process tenant quota ledger."""

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise QuotaError(
                "durable quota ledger requires a filesystem path, not :memory:"
            )
        self.timeout_seconds = float(timeout_seconds)
        if self.timeout_seconds <= 0:
            raise QuotaError("timeout_seconds must be greater than zero")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.path),
            timeout=self.timeout_seconds,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(
            f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}"
        )
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @staticmethod
    def _quota(row: sqlite3.Row) -> TenantQuota:
        return TenantQuota(
            window_id=row["window_id"],
            max_operations=int(row["max_operations"]),
            max_input_tokens=int(row["max_input_tokens"]),
            max_output_tokens=int(row["max_output_tokens"]),
            max_cost_usd=float(row["max_cost_usd"]),
            max_tool_calls=int(row["max_tool_calls"]),
            max_artifact_bytes=int(row["max_artifact_bytes"]),
            max_concurrent_operations=int(row["max_concurrent_operations"]),
        )

    @staticmethod
    def _usage(row: sqlite3.Row, prefix: str) -> QuotaUsage:
        return QuotaUsage(
            operations=int(row[f"{prefix}_operations"]),
            input_tokens=int(row[f"{prefix}_input_tokens"]),
            output_tokens=int(row[f"{prefix}_output_tokens"]),
            cost_usd=float(row[f"{prefix}_cost_usd"]),
            tool_calls=int(row[f"{prefix}_tool_calls"]),
            artifact_bytes=int(row[f"{prefix}_artifact_bytes"]),
        )

    @staticmethod
    def _reservation(row: sqlite3.Row) -> QuotaReservation:
        return QuotaReservation(
            reservation_id=row["reservation_id"],
            tenant_id=row["tenant_id"],
            window_id=row["window_id"],
            operation_id=row["operation_id"],
            estimate=SqliteTenantQuotaLedger._usage(row, "estimate"),
            reserved_at=float(row["reserved_at"]),
        )

    @staticmethod
    def _completion(row: sqlite3.Row) -> QuotaCompletion:
        return QuotaCompletion(
            reservation_id=row["reservation_id"],
            tenant_id=row["tenant_id"],
            window_id=row["window_id"],
            operation_id=row["operation_id"],
            estimate=SqliteTenantQuotaLedger._usage(row, "estimate"),
            actual=SqliteTenantQuotaLedger._usage(row, "actual"),
            overrun_dimensions=tuple(json.loads(row["overrun_dimensions"])),
            completed_at=float(row["completed_at"]),
        )

    @staticmethod
    def _committed(row: sqlite3.Row) -> QuotaUsage:
        return QuotaUsage(
            operations=int(row["committed_operations"]),
            input_tokens=int(row["committed_input_tokens"]),
            output_tokens=int(row["committed_output_tokens"]),
            cost_usd=float(row["committed_cost_usd"]),
            tool_calls=int(row["committed_tool_calls"]),
            artifact_bytes=int(row["committed_artifact_bytes"]),
        )

    @staticmethod
    def _quota_row(conn: sqlite3.Connection, tenant: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM tenant_quota WHERE tenant_id = ?",
            (tenant,),
        ).fetchone()
        if row is None:
            raise QuotaError("tenant quota is not configured")
        return row

    @staticmethod
    def _reserved_usage(
        conn: sqlite3.Connection,
        tenant: str,
    ) -> QuotaUsage:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(estimate_operations), 0) AS operations,
                COALESCE(SUM(estimate_input_tokens), 0) AS input_tokens,
                COALESCE(SUM(estimate_output_tokens), 0) AS output_tokens,
                COALESCE(SUM(estimate_cost_usd), 0) AS cost_usd,
                COALESCE(SUM(estimate_tool_calls), 0) AS tool_calls,
                COALESCE(SUM(estimate_artifact_bytes), 0) AS artifact_bytes
            FROM quota_reservations
            WHERE tenant_id = ?
            """,
            (tenant,),
        ).fetchone()
        assert row is not None
        return QuotaUsage(
            operations=int(row["operations"]),
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
            cost_usd=float(row["cost_usd"]),
            tool_calls=int(row["tool_calls"]),
            artifact_bytes=int(row["artifact_bytes"]),
        )

    def configure(
        self,
        tenant_id: str,
        quota: TenantQuota,
        *,
        replace: bool = False,
    ) -> TenantQuota:
        tenant = _required_id(tenant_id, "tenant_id")
        if not isinstance(quota, TenantQuota):
            raise QuotaError("quota must be TenantQuota")
        with self._write() as conn:
            current = conn.execute(
                "SELECT tenant_id FROM tenant_quota WHERE tenant_id = ?",
                (tenant,),
            ).fetchone()
            if current is not None:
                if not replace:
                    raise QuotaConflict("tenant quota already configured")
                active = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM quota_reservations WHERE tenant_id = ?",
                        (tenant,),
                    ).fetchone()[0]
                )
                if active:
                    raise QuotaConflict(
                        "cannot replace quota while reservations are active"
                    )
                conn.execute(
                    "DELETE FROM quota_completions WHERE tenant_id = ?",
                    (tenant,),
                )

            conn.execute(
                """
                INSERT OR REPLACE INTO tenant_quota (
                    tenant_id, window_id,
                    max_operations, max_input_tokens, max_output_tokens,
                    max_cost_usd, max_tool_calls, max_artifact_bytes,
                    max_concurrent_operations,
                    committed_operations, committed_input_tokens,
                    committed_output_tokens, committed_cost_usd,
                    committed_tool_calls, committed_artifact_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0)
                """,
                (
                    tenant,
                    quota.window_id,
                    quota.max_operations,
                    quota.max_input_tokens,
                    quota.max_output_tokens,
                    quota.max_cost_usd,
                    quota.max_tool_calls,
                    quota.max_artifact_bytes,
                    quota.max_concurrent_operations,
                ),
            )
        return quota

    def reserve(
        self,
        tenant_id: str,
        operation_id: str,
        estimate: UsageEstimate,
        *,
        now: float | None = None,
    ) -> QuotaReservation:
        tenant = _required_id(tenant_id, "tenant_id")
        operation = _required_id(operation_id, "operation_id")
        if not isinstance(estimate, UsageEstimate):
            raise QuotaError("estimate must be UsageEstimate")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        requested = QuotaUsage.from_estimate(estimate)

        with self._write() as conn:
            quota_row = self._quota_row(conn, tenant)
            quota = self._quota(quota_row)

            existing = conn.execute(
                """
                SELECT * FROM quota_reservations
                WHERE tenant_id = ? AND operation_id = ?
                """,
                (tenant, operation),
            ).fetchone()
            if existing is not None:
                reservation = self._reservation(existing)
                if reservation.estimate != requested:
                    raise QuotaConflict(
                        "operation already reserved with a different estimate"
                    )
                return reservation

            completed = conn.execute(
                """
                SELECT 1 FROM quota_completions
                WHERE tenant_id = ? AND operation_id = ?
                """,
                (tenant, operation),
            ).fetchone()
            if completed is not None:
                raise QuotaConflict(
                    "operation quota reservation already completed"
                )

            active = int(
                conn.execute(
                    "SELECT COUNT(*) FROM quota_reservations WHERE tenant_id = ?",
                    (tenant,),
                ).fetchone()[0]
            )
            if active >= quota.max_concurrent_operations:
                raise QuotaExceeded("tenant_concurrency_exceeded")

            committed = self._committed(quota_row)
            reserved = self._reserved_usage(conn, tenant)
            projected = committed.plus(reserved).plus(requested)
            excess = _quota_excess(quota, projected)
            if excess:
                raise QuotaExceeded(
                    "tenant_quota_exceeded:" + ",".join(excess)
                )

            reservation = QuotaReservation(
                reservation_id=_reservation_id(
                    tenant,
                    quota.window_id,
                    operation,
                    requested,
                ),
                tenant_id=tenant,
                window_id=quota.window_id,
                operation_id=operation,
                estimate=requested,
                reserved_at=timestamp,
            )
            values = reservation.estimate.as_dict()
            conn.execute(
                """
                INSERT INTO quota_reservations (
                    reservation_id, tenant_id, window_id, operation_id,
                    estimate_operations, estimate_input_tokens,
                    estimate_output_tokens, estimate_cost_usd,
                    estimate_tool_calls, estimate_artifact_bytes,
                    reserved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation.reservation_id,
                    tenant,
                    quota.window_id,
                    operation,
                    values["operations"],
                    values["input_tokens"],
                    values["output_tokens"],
                    values["cost_usd"],
                    values["tool_calls"],
                    values["artifact_bytes"],
                    timestamp,
                ),
            )
            return reservation

    def release(self, reservation_id: str) -> QuotaReservation:
        key = _required_id(reservation_id, "reservation_id")
        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if row is None:
                raise QuotaError("unknown active quota reservation")
            reservation = self._reservation(row)
            conn.execute(
                "DELETE FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            )
            return reservation

    def complete(
        self,
        reservation_id: str,
        actual: UsageEstimate,
        *,
        now: float | None = None,
    ) -> QuotaCompletion:
        key = _required_id(reservation_id, "reservation_id")
        if not isinstance(actual, UsageEstimate):
            raise QuotaError("actual must be UsageEstimate")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        actual_usage = QuotaUsage.from_estimate(actual)

        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if row is None:
                raise QuotaError("unknown active quota reservation")
            reservation = self._reservation(row)
            quota_row = self._quota_row(conn, reservation.tenant_id)
            quota = self._quota(quota_row)
            committed = self._committed(quota_row)
            projected = committed.plus(actual_usage)
            overruns = _quota_excess(quota, projected)
            completion = QuotaCompletion(
                reservation_id=reservation.reservation_id,
                tenant_id=reservation.tenant_id,
                window_id=reservation.window_id,
                operation_id=reservation.operation_id,
                estimate=reservation.estimate,
                actual=actual_usage,
                overrun_dimensions=overruns,
                completed_at=timestamp,
            )
            values = projected.as_dict()
            conn.execute(
                """
                UPDATE tenant_quota SET
                    committed_operations = ?,
                    committed_input_tokens = ?,
                    committed_output_tokens = ?,
                    committed_cost_usd = ?,
                    committed_tool_calls = ?,
                    committed_artifact_bytes = ?
                WHERE tenant_id = ?
                """,
                (
                    values["operations"],
                    values["input_tokens"],
                    values["output_tokens"],
                    values["cost_usd"],
                    values["tool_calls"],
                    values["artifact_bytes"],
                    reservation.tenant_id,
                ),
            )
            estimate_values = reservation.estimate.as_dict()
            actual_values = actual_usage.as_dict()
            conn.execute(
                "DELETE FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            )
            conn.execute(
                """
                INSERT INTO quota_completions (
                    reservation_id, tenant_id, window_id, operation_id,
                    estimate_operations, estimate_input_tokens,
                    estimate_output_tokens, estimate_cost_usd,
                    estimate_tool_calls, estimate_artifact_bytes,
                    actual_operations, actual_input_tokens,
                    actual_output_tokens, actual_cost_usd,
                    actual_tool_calls, actual_artifact_bytes,
                    overrun_dimensions, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    completion.reservation_id,
                    completion.tenant_id,
                    completion.window_id,
                    completion.operation_id,
                    estimate_values["operations"],
                    estimate_values["input_tokens"],
                    estimate_values["output_tokens"],
                    estimate_values["cost_usd"],
                    estimate_values["tool_calls"],
                    estimate_values["artifact_bytes"],
                    actual_values["operations"],
                    actual_values["input_tokens"],
                    actual_values["output_tokens"],
                    actual_values["cost_usd"],
                    actual_values["tool_calls"],
                    actual_values["artifact_bytes"],
                    json.dumps(list(overruns), separators=(",", ":")),
                    timestamp,
                ),
            )
            return completion

    def snapshot(self, tenant_id: str) -> dict[str, object]:
        tenant = _required_id(tenant_id, "tenant_id")
        with self._read() as conn:
            row = self._quota_row(conn, tenant)
            quota = self._quota(row)
            committed = self._committed(row)
            reserved = self._reserved_usage(conn, tenant)
            projected = committed.plus(reserved)
            active = int(
                conn.execute(
                    "SELECT COUNT(*) FROM quota_reservations WHERE tenant_id = ?",
                    (tenant,),
                ).fetchone()[0]
            )
            completions = int(
                conn.execute(
                    "SELECT COUNT(*) FROM quota_completions WHERE tenant_id = ?",
                    (tenant,),
                ).fetchone()[0]
            )
            return {
                "tenant_id": tenant,
                "window_id": quota.window_id,
                "quota": {
                    "max_operations": quota.max_operations,
                    "max_input_tokens": quota.max_input_tokens,
                    "max_output_tokens": quota.max_output_tokens,
                    "max_cost_usd": quota.max_cost_usd,
                    "max_tool_calls": quota.max_tool_calls,
                    "max_artifact_bytes": quota.max_artifact_bytes,
                    "max_concurrent_operations": quota.max_concurrent_operations,
                },
                "committed": committed.as_dict(),
                "reserved": reserved.as_dict(),
                "projected": projected.as_dict(),
                "active_reservations": active,
                "completions": completions,
                "over_quota_dimensions": list(
                    _quota_excess(quota, projected)
                ),
            }

    def reset_window(
        self,
        tenant_id: str,
        quota: TenantQuota,
    ) -> TenantQuota:
        tenant = _required_id(tenant_id, "tenant_id")
        if not isinstance(quota, TenantQuota):
            raise QuotaError("quota must be TenantQuota")
        with self._write() as conn:
            current = self._quota_row(conn, tenant)
            active = int(
                conn.execute(
                    "SELECT COUNT(*) FROM quota_reservations WHERE tenant_id = ?",
                    (tenant,),
                ).fetchone()[0]
            )
            if active:
                raise QuotaConflict(
                    "cannot reset quota window while reservations are active"
                )
            if quota.window_id == current["window_id"]:
                raise QuotaConflict("new quota window_id must change")
            conn.execute(
                "DELETE FROM quota_completions WHERE tenant_id = ?",
                (tenant,),
            )
            conn.execute(
                """
                UPDATE tenant_quota SET
                    window_id = ?,
                    max_operations = ?,
                    max_input_tokens = ?,
                    max_output_tokens = ?,
                    max_cost_usd = ?,
                    max_tool_calls = ?,
                    max_artifact_bytes = ?,
                    max_concurrent_operations = ?,
                    committed_operations = 0,
                    committed_input_tokens = 0,
                    committed_output_tokens = 0,
                    committed_cost_usd = 0,
                    committed_tool_calls = 0,
                    committed_artifact_bytes = 0
                WHERE tenant_id = ?
                """,
                (
                    quota.window_id,
                    quota.max_operations,
                    quota.max_input_tokens,
                    quota.max_output_tokens,
                    quota.max_cost_usd,
                    quota.max_tool_calls,
                    quota.max_artifact_bytes,
                    quota.max_concurrent_operations,
                    tenant,
                ),
            )
        return quota

    def completion_for_operation(
        self,
        tenant_id: str,
        operation_id: str,
    ) -> QuotaCompletion | None:
        tenant = _required_id(tenant_id, "tenant_id")
        operation = _required_id(operation_id, "operation_id")
        with self._read() as conn:
            row = conn.execute(
                """
                SELECT * FROM quota_completions
                WHERE tenant_id = ? AND operation_id = ?
                """,
                (tenant, operation),
            ).fetchone()
            return None if row is None else self._completion(row)


__all__ = ["SqliteTenantQuotaLedger"]

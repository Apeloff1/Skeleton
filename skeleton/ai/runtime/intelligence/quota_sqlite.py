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
    QuotaUsageEvent,
    TenantQuota,
    _finite_nonnegative,
    _quota_excess,
    _required_id,
    _reservation_id,
)


_USAGE_CATEGORIES = {"tool", "artifact", "storage", "provider", "other"}
_UNKNOWN_USAGE_PREFIX = "unknown:"

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


CREATE TABLE IF NOT EXISTS quota_usage_events (
    event_id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    window_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    category TEXT NOT NULL,
    delta_operations INTEGER NOT NULL DEFAULT 0,
    delta_input_tokens INTEGER NOT NULL DEFAULT 0,
    delta_output_tokens INTEGER NOT NULL DEFAULT 0,
    delta_cost_usd REAL NOT NULL DEFAULT 0,
    delta_tool_calls INTEGER NOT NULL DEFAULT 0,
    delta_artifact_bytes INTEGER NOT NULL DEFAULT 0,
    recorded_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quota_usage_events_reservation
ON quota_usage_events (reservation_id);

CREATE INDEX IF NOT EXISTS idx_quota_usage_events_tenant
ON quota_usage_events (tenant_id);
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
        total = QuotaUsage()
        rows = conn.execute(
            "SELECT * FROM quota_reservations WHERE tenant_id = ?",
            (tenant,),
        ).fetchall()
        for row in rows:
            reservation = SqliteTenantQuotaLedger._reservation(row)
            observed = SqliteTenantQuotaLedger._metered_usage(
                conn,
                reservation.reservation_id,
            )
            total = total.plus(
                SqliteTenantQuotaLedger._usage_max(
                    reservation.estimate,
                    observed,
                )
            )
        return total

    @staticmethod
    def _usage_max(left: QuotaUsage, right: QuotaUsage) -> QuotaUsage:
        return QuotaUsage(
            operations=max(left.operations, right.operations),
            input_tokens=max(left.input_tokens, right.input_tokens),
            output_tokens=max(left.output_tokens, right.output_tokens),
            cost_usd=max(left.cost_usd, right.cost_usd),
            tool_calls=max(left.tool_calls, right.tool_calls),
            artifact_bytes=max(left.artifact_bytes, right.artifact_bytes),
        )

    @staticmethod
    def _metered_usage(
        conn: sqlite3.Connection,
        reservation_id: str,
    ) -> QuotaUsage:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(delta_operations), 0) AS operations,
                COALESCE(SUM(delta_input_tokens), 0) AS input_tokens,
                COALESCE(SUM(delta_output_tokens), 0) AS output_tokens,
                COALESCE(SUM(delta_cost_usd), 0) AS cost_usd,
                COALESCE(SUM(delta_tool_calls), 0) AS tool_calls,
                COALESCE(SUM(delta_artifact_bytes), 0) AS artifact_bytes
            FROM quota_usage_events
            WHERE reservation_id = ?
            """,
            (reservation_id,),
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

    @staticmethod
    def _reserved_usage_excluding(
        conn: sqlite3.Connection,
        tenant: str,
        reservation_id: str,
    ) -> QuotaUsage:
        total = QuotaUsage()
        rows = conn.execute(
            """
            SELECT * FROM quota_reservations
            WHERE tenant_id = ? AND reservation_id != ?
            """,
            (tenant, reservation_id),
        ).fetchall()
        for row in rows:
            reservation = SqliteTenantQuotaLedger._reservation(row)
            observed = SqliteTenantQuotaLedger._metered_usage(
                conn,
                reservation.reservation_id,
            )
            total = total.plus(
                SqliteTenantQuotaLedger._usage_max(
                    reservation.estimate,
                    observed,
                )
            )
        return total

    @staticmethod
    def _usage_event(row: sqlite3.Row) -> QuotaUsageEvent:
        return QuotaUsageEvent(
            event_id=row["event_id"],
            reservation_id=row["reservation_id"],
            tenant_id=row["tenant_id"],
            window_id=row["window_id"],
            operation_id=row["operation_id"],
            category=row["category"],
            delta=QuotaUsage(
                operations=int(row["delta_operations"]),
                input_tokens=int(row["delta_input_tokens"]),
                output_tokens=int(row["delta_output_tokens"]),
                cost_usd=float(row["delta_cost_usd"]),
                tool_calls=int(row["delta_tool_calls"]),
                artifact_bytes=int(row["delta_artifact_bytes"]),
            ),
            recorded_at=float(row["recorded_at"]),
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

    def record_usage_event(
        self,
        reservation_id: str,
        event_id: str,
        category: str,
        delta: UsageEstimate,
        *,
        max_tool_calls: int | None = None,
        max_artifact_bytes: int | None = None,
        now: float | None = None,
    ) -> QuotaUsageEvent:
        """Atomically record one idempotent incremental actual-usage event.

        Storage bytes consume the same byte budget as artifacts. Callers should
        record the event before a side effect when its cost is known. Once an
        event exists, release() is forbidden; completion must reconcile it.
        """

        key = _required_id(reservation_id, "reservation_id")
        event = _required_id(event_id, "event_id")
        normalized_category = str(category).strip().lower()
        if normalized_category not in _USAGE_CATEGORIES:
            raise QuotaError("unsupported usage category")
        if not isinstance(delta, UsageEstimate):
            raise QuotaError("delta must be UsageEstimate")
        for field, value in (
            ("max_tool_calls", max_tool_calls),
            ("max_artifact_bytes", max_artifact_bytes),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise QuotaError(f"{field} must be a non-negative integer")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        delta_usage = QuotaUsage(
            operations=0,
            input_tokens=delta.input_tokens,
            output_tokens=delta.output_tokens,
            cost_usd=delta.cost_usd,
            tool_calls=delta.tool_calls,
            artifact_bytes=delta.artifact_bytes,
        )

        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if row is None:
                completed = conn.execute(
                    "SELECT 1 FROM quota_completions WHERE reservation_id = ?",
                    (key,),
                ).fetchone()
                if completed is not None:
                    raise QuotaConflict("cannot meter a completed quota reservation")
                raise QuotaError("unknown active quota reservation")
            reservation = self._reservation(row)

            existing = conn.execute(
                "SELECT * FROM quota_usage_events WHERE event_id = ?",
                (event,),
            ).fetchone()
            if existing is not None:
                replay = self._usage_event(existing)
                if (
                    replay.reservation_id != key
                    or replay.category != normalized_category
                    or replay.delta != delta_usage
                ):
                    raise QuotaConflict(
                        "usage event id replayed with different inputs"
                    )
                return replay

            observed = self._metered_usage(conn, key)
            prospective = observed.plus(delta_usage)
            if (
                max_tool_calls is not None
                and prospective.tool_calls > max_tool_calls
            ):
                raise QuotaExceeded("operation_budget_exceeded:tool_calls")
            if (
                max_artifact_bytes is not None
                and prospective.artifact_bytes > max_artifact_bytes
            ):
                raise QuotaExceeded("operation_budget_exceeded:artifact_bytes")

            quota_row = self._quota_row(conn, reservation.tenant_id)
            quota = self._quota(quota_row)
            committed = self._committed(quota_row)
            other_reserved = self._reserved_usage_excluding(
                conn,
                reservation.tenant_id,
                key,
            )
            effective_current = self._usage_max(
                reservation.estimate,
                prospective,
            )
            projected = committed.plus(other_reserved).plus(effective_current)
            excess = _quota_excess(quota, projected)
            if excess:
                raise QuotaExceeded(
                    "tenant_quota_exceeded:" + ",".join(excess)
                )

            values = delta_usage.as_dict()
            conn.execute(
                """
                INSERT INTO quota_usage_events (
                    event_id, reservation_id, tenant_id, window_id,
                    operation_id, category,
                    delta_operations, delta_input_tokens, delta_output_tokens,
                    delta_cost_usd, delta_tool_calls, delta_artifact_bytes,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event,
                    reservation.reservation_id,
                    reservation.tenant_id,
                    reservation.window_id,
                    reservation.operation_id,
                    normalized_category,
                    values["operations"],
                    values["input_tokens"],
                    values["output_tokens"],
                    values["cost_usd"],
                    values["tool_calls"],
                    values["artifact_bytes"],
                    timestamp,
                ),
            )
            inserted = conn.execute(
                "SELECT * FROM quota_usage_events WHERE event_id = ?",
                (event,),
            ).fetchone()
            assert inserted is not None
            return self._usage_event(inserted)

    def mark_usage_unknown(
        self,
        reservation_id: str,
        event_id: str,
        category: str,
        *,
        now: float | None = None,
    ) -> QuotaUsageEvent:
        """Persist an unresolved actual-usage marker across process restart."""

        key = _required_id(reservation_id, "reservation_id")
        event = _required_id(event_id, "event_id")
        normalized_category = str(category).strip().lower()
        if normalized_category not in _USAGE_CATEGORIES:
            raise QuotaError("unsupported usage category")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        unknown_category = _UNKNOWN_USAGE_PREFIX + normalized_category

        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if row is None:
                completed = conn.execute(
                    "SELECT 1 FROM quota_completions WHERE reservation_id = ?",
                    (key,),
                ).fetchone()
                if completed is not None:
                    raise QuotaConflict("cannot meter a completed quota reservation")
                raise QuotaError("unknown active quota reservation")
            reservation = self._reservation(row)

            existing = conn.execute(
                "SELECT * FROM quota_usage_events WHERE event_id = ?",
                (event,),
            ).fetchone()
            if existing is not None:
                replay = self._usage_event(existing)
                if (
                    replay.reservation_id != key
                    or replay.category != unknown_category
                    or replay.delta != QuotaUsage()
                ):
                    raise QuotaConflict(
                        "usage event id replayed with different inputs"
                    )
                return replay

            conn.execute(
                """
                INSERT INTO quota_usage_events (
                    event_id, reservation_id, tenant_id, window_id,
                    operation_id, category,
                    delta_operations, delta_input_tokens, delta_output_tokens,
                    delta_cost_usd, delta_tool_calls, delta_artifact_bytes,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?)
                """,
                (
                    event,
                    reservation.reservation_id,
                    reservation.tenant_id,
                    reservation.window_id,
                    reservation.operation_id,
                    unknown_category,
                    timestamp,
                ),
            )
            inserted = conn.execute(
                "SELECT * FROM quota_usage_events WHERE event_id = ?",
                (event,),
            ).fetchone()
            assert inserted is not None
            return self._usage_event(inserted)

    def resolve_unknown_usage(
        self,
        reservation_id: str,
        event_id: str,
        delta: UsageEstimate,
        *,
        max_tool_calls: int | None = None,
        max_artifact_bytes: int | None = None,
        now: float | None = None,
    ) -> QuotaUsageEvent:
        """Replace one durable unknown marker with conservative actual usage."""

        key = _required_id(reservation_id, "reservation_id")
        event = _required_id(event_id, "event_id")
        if not isinstance(delta, UsageEstimate):
            raise QuotaError("delta must be UsageEstimate")
        for field, value in (
            ("max_tool_calls", max_tool_calls),
            ("max_artifact_bytes", max_artifact_bytes),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise QuotaError(f"{field} must be a non-negative integer")
        timestamp = time.time() if now is None else _finite_nonnegative(now, "now")
        delta_usage = QuotaUsage(
            operations=0,
            input_tokens=delta.input_tokens,
            output_tokens=delta.output_tokens,
            cost_usd=delta.cost_usd,
            tool_calls=delta.tool_calls,
            artifact_bytes=delta.artifact_bytes,
        )

        with self._write() as conn:
            reservation_row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if reservation_row is None:
                raise QuotaError("unknown active quota reservation")
            reservation = self._reservation(reservation_row)

            marker_row = conn.execute(
                "SELECT * FROM quota_usage_events WHERE event_id = ?",
                (event,),
            ).fetchone()
            if marker_row is None:
                raise QuotaError("unknown usage marker does not exist")
            marker = self._usage_event(marker_row)
            if marker.reservation_id != key:
                raise QuotaConflict(
                    "usage event belongs to a different reservation"
                )
            if not marker.category.startswith(_UNKNOWN_USAGE_PREFIX):
                raise QuotaConflict("usage event is not unresolved")
            category = marker.category[len(_UNKNOWN_USAGE_PREFIX):]

            observed = self._metered_usage(conn, key)
            prospective = observed.plus(delta_usage)
            if max_tool_calls is not None and prospective.tool_calls > max_tool_calls:
                raise QuotaExceeded("operation_budget_exceeded:tool_calls")
            if (
                max_artifact_bytes is not None
                and prospective.artifact_bytes > max_artifact_bytes
            ):
                raise QuotaExceeded("operation_budget_exceeded:artifact_bytes")

            quota_row = self._quota_row(conn, reservation.tenant_id)
            quota = self._quota(quota_row)
            committed = self._committed(quota_row)
            other_reserved = self._reserved_usage_excluding(
                conn,
                reservation.tenant_id,
                key,
            )
            effective_current = self._usage_max(
                reservation.estimate,
                prospective,
            )
            projected = committed.plus(other_reserved).plus(effective_current)
            excess = _quota_excess(quota, projected)
            if excess:
                raise QuotaExceeded(
                    "tenant_quota_exceeded:" + ",".join(excess)
                )

            values = delta_usage.as_dict()
            conn.execute(
                """
                UPDATE quota_usage_events SET
                    category = ?,
                    delta_operations = ?,
                    delta_input_tokens = ?,
                    delta_output_tokens = ?,
                    delta_cost_usd = ?,
                    delta_tool_calls = ?,
                    delta_artifact_bytes = ?,
                    recorded_at = ?
                WHERE event_id = ?
                """,
                (
                    category,
                    values["operations"],
                    values["input_tokens"],
                    values["output_tokens"],
                    values["cost_usd"],
                    values["tool_calls"],
                    values["artifact_bytes"],
                    timestamp,
                    event,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM quota_usage_events WHERE event_id = ?",
                (event,),
            ).fetchone()
            assert updated is not None
            return self._usage_event(updated)

    def unresolved_usage(self, reservation_id: str) -> tuple[QuotaUsageEvent, ...]:
        key = _required_id(reservation_id, "reservation_id")
        with self._read() as conn:
            active = conn.execute(
                "SELECT 1 FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            completed = conn.execute(
                "SELECT 1 FROM quota_completions WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if active is None and completed is None:
                raise QuotaError("unknown quota reservation")
            rows = conn.execute(
                """
                SELECT * FROM quota_usage_events
                WHERE reservation_id = ? AND category LIKE ?
                ORDER BY event_id
                """,
                (key, _UNKNOWN_USAGE_PREFIX + "%"),
            ).fetchall()
            return tuple(self._usage_event(row) for row in rows)

    def metered_usage(self, reservation_id: str) -> QuotaUsage:
        key = _required_id(reservation_id, "reservation_id")
        with self._read() as conn:
            active = conn.execute(
                "SELECT 1 FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            completed = conn.execute(
                "SELECT 1 FROM quota_completions WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if active is None and completed is None:
                raise QuotaError("unknown quota reservation")
            return self._metered_usage(conn, key)

    def release(self, reservation_id: str) -> QuotaReservation:
        key = _required_id(reservation_id, "reservation_id")
        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if row is None:
                raise QuotaError("unknown active quota reservation")
            metered_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM quota_usage_events WHERE reservation_id = ?",
                    (key,),
                ).fetchone()[0]
            )
            if metered_count:
                raise QuotaConflict(
                    "cannot release reservation after metered usage; complete it instead"
                )
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
        reported_usage = QuotaUsage.from_estimate(actual)

        with self._write() as conn:
            row = conn.execute(
                "SELECT * FROM quota_reservations WHERE reservation_id = ?",
                (key,),
            ).fetchone()
            if row is None:
                completed = conn.execute(
                    "SELECT * FROM quota_completions WHERE reservation_id = ?",
                    (key,),
                ).fetchone()
                if completed is not None:
                    existing = self._completion(completed)
                    if existing.actual == reported_usage:
                        return existing
                    raise QuotaConflict(
                        "completed reservation replayed with different actual usage"
                    )
                raise QuotaError("unknown active quota reservation")
            reservation = self._reservation(row)
            unresolved_rows = conn.execute(
                """
                SELECT category FROM quota_usage_events
                WHERE reservation_id = ? AND category LIKE ?
                """,
                (key, _UNKNOWN_USAGE_PREFIX + "%"),
            ).fetchall()
            if unresolved_rows:
                categories = sorted(
                    {
                        str(item["category"])[len(_UNKNOWN_USAGE_PREFIX):]
                        for item in unresolved_rows
                    }
                )
                raise QuotaConflict(
                    "actual_usage_unknown:" + ",".join(categories)
                )

            observed_usage = self._metered_usage(conn, key)
            actual_usage = self._usage_max(reported_usage, observed_usage)
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
            usage_events = int(
                conn.execute(
                    "SELECT COUNT(*) FROM quota_usage_events WHERE tenant_id = ?",
                    (tenant,),
                ).fetchone()[0]
            )
            unknown_usage_events = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM quota_usage_events
                    WHERE tenant_id = ? AND category LIKE ?
                    """,
                    (tenant, _UNKNOWN_USAGE_PREFIX + "%"),
                ).fetchone()[0]
            )
            category_rows = conn.execute(
                """
                SELECT category,
                       COALESCE(SUM(delta_tool_calls), 0) AS tool_calls,
                       COALESCE(SUM(delta_artifact_bytes), 0) AS artifact_bytes
                FROM quota_usage_events
                WHERE tenant_id = ?
                GROUP BY category
                """,
                (tenant,),
            ).fetchall()
            metered_by_category = {
                str(row["category"]): {
                    "tool_calls": int(row["tool_calls"]),
                    "artifact_bytes": int(row["artifact_bytes"]),
                }
                for row in category_rows
            }
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
                "usage_events": usage_events,
                "unknown_usage_events": unknown_usage_events,
                "metered_by_category": metered_by_category,
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
                "DELETE FROM quota_usage_events WHERE tenant_id = ?",
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

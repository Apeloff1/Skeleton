"""Delivery-log, DLQ and retry-policy adapters (SQLite + in-memory).

Kept separate from ``sqlite_store``/``memory_store`` so the original #4596
adapters stay small; both adapter families share the semantics pinned by
``tests/backend_core/test_log_store_conformance.py``.
"""
from __future__ import annotations

import threading
from typing import Iterable

from skeleton.persistence.app_foundation.db import Database

from .memory_store import MemoryDeliveryRepository
from .models import Delivery, DeliveryStatus
from .ports import AttemptQuery, AttemptRecord, DeliveryQuery
from .retry import RetryPolicy
from .sqlite_store import _dlv

TERMINAL_VALUES = ("succeeded", "dead")


# ------------------------------------------------------------------ in-memory
class MemoryRetryPolicyRepository:
    def __init__(self) -> None:
        self._d: dict[tuple[str, str], RetryPolicy] = {}

    def get(self, tenant_id, webhook_id):
        return self._d.get((tenant_id, webhook_id))

    def put(self, tenant_id, webhook_id, policy, updated_at) -> None:
        self._d[(tenant_id, webhook_id)] = policy

    def delete(self, tenant_id, webhook_id) -> bool:
        return self._d.pop((tenant_id, webhook_id), None) is not None


def _in_window(t: float, since: float | None, until: float | None) -> bool:
    return (since is None or t >= since) and (until is None or t < until)


class MemoryDeliveryLog:
    """Reads the same dicts as ``MemoryDeliveryRepository`` (shared state)."""

    def __init__(self, deliveries: MemoryDeliveryRepository) -> None:
        self.r = deliveries
        self._lock = threading.Lock()

    def _deliveries(self) -> Iterable[Delivery]:
        return list(self.r._d.values())

    def query(self, q: DeliveryQuery, limit: int, after):
        rows = []
        for d in self._deliveries():
            if d.tenant_id != q.tenant_id:
                continue
            if q.webhook_id and d.webhook_id != q.webhook_id:
                continue
            if q.event_id and d.event_id != q.event_id:
                continue
            if q.statuses and d.status.value not in q.statuses:
                continue
            t = getattr(d, q.time_field)
            if not _in_window(t, q.since, q.until):
                continue
            if after is not None and (t, d.delivery_id) <= after:
                continue
            rows.append(d)
        rows.sort(key=lambda d: (getattr(d, q.time_field), d.delivery_id))
        return rows[: limit + 1]

    def query_attempts(self, q: AttemptQuery, limit: int, after):
        out = []
        for did, attempts in list(self.r._attempts.items()):
            d = self.r._d.get(did)
            if d is None or d.tenant_id != q.tenant_id:
                continue
            if q.webhook_id and d.webhook_id != q.webhook_id:
                continue
            if q.event_id and d.event_id != q.event_id:
                continue
            if q.delivery_id and did != q.delivery_id:
                continue
            for a in attempts:
                if q.outcomes and a.outcome not in q.outcomes:
                    continue
                if not _in_window(a.started_at, q.since, q.until):
                    continue
                rec = AttemptRecord(a, d.webhook_id, d.event_id)
                if after is not None and rec.key() <= after:
                    continue
                out.append(rec)
        out.sort(key=AttemptRecord.key)
        return out[: limit + 1]

    def open_replay_exists(self, tenant_id: str, delivery_id: str) -> bool:
        return any(d.tenant_id == tenant_id and d.replay_of == delivery_id and d.status.value not in TERMINAL_VALUES
                   for d in self._deliveries())

    def purge_dead(self, tenant_id, before, webhook_id, limit):
        with self.r._lock:
            victims = sorted((d for d in self.r._d.values()
                              if d.tenant_id == tenant_id and d.status is DeliveryStatus.DEAD
                              and d.updated_at < before and (webhook_id is None or d.webhook_id == webhook_id)),
                             key=lambda d: (d.updated_at, d.delivery_id))[:limit]
            for d in victims:
                del self.r._d[d.delivery_id]
                self.r._attempts.pop(d.delivery_id, None)
            return [d.delivery_id for d in victims]


# --------------------------------------------------------------------- SQLite
class SqliteRetryPolicyRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, tenant_id, webhook_id):
        rows = self.db.query("SELECT * FROM core_v1_retry_policies WHERE tenant_id=? AND webhook_id=?",
                             (tenant_id, webhook_id))
        if not rows:
            return None
        r = rows[0]
        return RetryPolicy(base_seconds=r["base_seconds"], factor=r["factor"], cap_seconds=r["cap_seconds"],
                           max_age_seconds=r["max_age_seconds"])

    def put(self, tenant_id, webhook_id, policy, updated_at) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO core_v1_retry_policies VALUES (?,?,?,?,?,?,?) ON CONFLICT(webhook_id) DO UPDATE "
                      "SET base_seconds=excluded.base_seconds, factor=excluded.factor, "
                      "cap_seconds=excluded.cap_seconds, max_age_seconds=excluded.max_age_seconds, "
                      "updated_at=excluded.updated_at WHERE core_v1_retry_policies.tenant_id=excluded.tenant_id",
                      (webhook_id, tenant_id, policy.base_seconds, policy.factor, policy.cap_seconds,
                       policy.max_age_seconds, updated_at))

    def delete(self, tenant_id, webhook_id) -> bool:
        with self.db.tx() as c:
            return c.execute("DELETE FROM core_v1_retry_policies WHERE tenant_id=? AND webhook_id=?",
                             (tenant_id, webhook_id)).rowcount == 1


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


class SqliteDeliveryLog:
    def __init__(self, db: Database) -> None:
        self.db = db

    def query(self, q: DeliveryQuery, limit: int, after):
        tf = q.time_field  # validated in DeliveryQuery
        sql = "SELECT * FROM core_v1_deliveries WHERE tenant_id=?"
        args: list = [q.tenant_id]
        if q.webhook_id:
            sql += " AND webhook_id=?"; args.append(q.webhook_id)
        if q.event_id:
            sql += " AND event_id=?"; args.append(q.event_id)
        if q.statuses:
            sql += f" AND status IN ({_placeholders(len(q.statuses))})"; args += list(q.statuses)
        if q.since is not None:
            sql += f" AND {tf} >= ?"; args.append(q.since)
        if q.until is not None:
            sql += f" AND {tf} < ?"; args.append(q.until)
        if after is not None:
            sql += f" AND ({tf} > ? OR ({tf} = ? AND delivery_id > ?))"; args += [after[0], after[0], after[1]]
        sql += f" ORDER BY {tf}, delivery_id LIMIT ?"
        args.append(limit + 1)
        return [_dlv(r) for r in self.db.query(sql, tuple(args))]

    def query_attempts(self, q: AttemptQuery, limit: int, after):
        from .models import Attempt
        sql = ("SELECT a.*, d.webhook_id AS d_webhook, d.event_id AS d_event, "
               "a.delivery_id || ':' || substr('0000' || a.attempt, -4, 4) AS k "
               "FROM core_v1_attempts a JOIN core_v1_deliveries d ON d.delivery_id = a.delivery_id "
               "WHERE d.tenant_id=?")
        args: list = [q.tenant_id]
        if q.webhook_id:
            sql += " AND d.webhook_id=?"; args.append(q.webhook_id)
        if q.event_id:
            sql += " AND d.event_id=?"; args.append(q.event_id)
        if q.delivery_id:
            sql += " AND a.delivery_id=?"; args.append(q.delivery_id)
        if q.outcomes:
            sql += f" AND a.outcome IN ({_placeholders(len(q.outcomes))})"; args += list(q.outcomes)
        if q.since is not None:
            sql += " AND a.started_at >= ?"; args.append(q.since)
        if q.until is not None:
            sql += " AND a.started_at < ?"; args.append(q.until)
        if after is not None:
            sql += " AND (a.started_at > ? OR (a.started_at = ? AND k > ?))"; args += [after[0], after[0], after[1]]
        sql += " ORDER BY a.started_at, k LIMIT ?"
        args.append(limit + 1)
        return [AttemptRecord(Attempt(r["delivery_id"], r["attempt"], r["started_at"], r["duration_ms"],
                                      r["status_code"], r["error"], r["outcome"]), r["d_webhook"], r["d_event"])
                for r in self.db.query(sql, tuple(args))]

    def open_replay_exists(self, tenant_id: str, delivery_id: str) -> bool:
        return bool(self.db.query(
            "SELECT 1 FROM core_v1_deliveries WHERE tenant_id=? AND replay_of=? AND status NOT IN (?,?) LIMIT 1",
            (tenant_id, delivery_id, *TERMINAL_VALUES)))

    def purge_dead(self, tenant_id, before, webhook_id, limit):
        with self.db.tx() as c:
            sql = "SELECT delivery_id FROM core_v1_deliveries WHERE tenant_id=? AND status='dead' AND updated_at<?"
            args: list = [tenant_id, before]
            if webhook_id:
                sql += " AND webhook_id=?"; args.append(webhook_id)
            sql += " ORDER BY updated_at, delivery_id LIMIT ?"
            args.append(limit)
            ids = [r[0] for r in c.execute(sql, tuple(args)).fetchall()]
            for did in ids:
                c.execute("DELETE FROM core_v1_attempts WHERE delivery_id=?", (did,))
                c.execute("DELETE FROM core_v1_deliveries WHERE delivery_id=?", (did,))
        return ids


__all__ = ["MemoryRetryPolicyRepository", "MemoryDeliveryLog", "SqliteRetryPolicyRepository",
           "SqliteDeliveryLog"]

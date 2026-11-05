"""SQLite adapters built on ``skeleton.persistence.app_foundation.db.Database``.

Backend core keeps its own forward-only migration ledger
(``core_v1_migrations``) so it never edits the app_foundation schema.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Sequence

from skeleton.persistence.app_foundation.db import Database

from .idempotency import IdempotencyRecord, StoredResponse
from .models import Attempt, Delivery, DeliveryStatus, Event, WebhookSubscription

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "idempotency", """
        CREATE TABLE core_v1_idempotency (
            scope_key TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            response_status INTEGER,
            response_body TEXT,
            locked_until REAL NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE INDEX idx_core_v1_idem_exp ON core_v1_idempotency(expires_at)
    """),
    (2, "webhooks", """
        CREATE TABLE core_v1_webhooks (
            webhook_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            url TEXT NOT NULL,
            event_filters TEXT NOT NULL,
            description TEXT NOT NULL,
            active INTEGER NOT NULL,
            secret_ids TEXT NOT NULL,
            max_attempts INTEGER NOT NULL,
            version INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            disabled_reason TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_core_v1_webhooks_tenant ON core_v1_webhooks(tenant_id, created_at, webhook_id);
        CREATE TABLE core_v1_webhook_secrets (
            secret_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            secret BLOB NOT NULL,
            created_at REAL NOT NULL
        )
    """),
    (3, "events_and_deliveries", """
        CREATE TABLE core_v1_events (
            event_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(tenant_id, dedupe_key)
        );
        CREATE TABLE core_v1_deliveries (
            delivery_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            webhook_id TEXT NOT NULL REFERENCES core_v1_webhooks(webhook_id),
            event_id TEXT NOT NULL REFERENCES core_v1_events(event_id),
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            next_attempt_at REAL NOT NULL,
            lease_until REAL NOT NULL,
            last_status_code INTEGER,
            last_error TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            replay_of TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_core_v1_dlv_due ON core_v1_deliveries(status, next_attempt_at);
        CREATE INDEX idx_core_v1_dlv_hook ON core_v1_deliveries(webhook_id, created_at, delivery_id);
        CREATE UNIQUE INDEX idx_core_v1_dlv_once ON core_v1_deliveries(webhook_id, event_id)
            WHERE replay_of = '';
        CREATE TABLE core_v1_attempts (
            delivery_id TEXT NOT NULL REFERENCES core_v1_deliveries(delivery_id),
            attempt INTEGER NOT NULL,
            started_at REAL NOT NULL,
            duration_ms REAL NOT NULL,
            status_code INTEGER,
            error TEXT NOT NULL,
            outcome TEXT NOT NULL,
            PRIMARY KEY (delivery_id, attempt)
        )
    """),
)


def migrate(db: Database) -> list[int]:
    applied: list[int] = []
    with db.tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS core_v1_migrations ("
                  "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at REAL NOT NULL)")
        current = c.execute("SELECT COALESCE(MAX(version), 0) FROM core_v1_migrations").fetchone()[0]
    for version, name, sql in MIGRATIONS:
        if version <= current:
            continue
        with db.tx() as c:
            for stmt in filter(None, (s.strip() for s in sql.split(";"))):
                c.execute(stmt)
            c.execute("INSERT INTO core_v1_migrations VALUES (?,?,?)", (version, name, time.time()))
        applied.append(version)
    return applied


def open_database(path: str) -> Database:
    db = Database(path)
    migrate(db)
    return db


# ---------------------------------------------------------------- idempotency
class SqliteIdempotencyStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, scope_key: str) -> IdempotencyRecord | None:
        rows = self.db.query("SELECT * FROM core_v1_idempotency WHERE scope_key=?", (scope_key,))
        if not rows:
            return None
        r = rows[0]
        resp = None
        if r["response_status"] is not None:
            resp = StoredResponse(r["response_status"], json.loads(r["response_body"]))
        return IdempotencyRecord(r["scope_key"], r["fingerprint"], resp, r["locked_until"], r["expires_at"])

    def try_lock(self, record: IdempotencyRecord, now: float) -> bool:
        with self.db.tx() as c:
            row = c.execute("SELECT response_status, locked_until, expires_at FROM core_v1_idempotency "
                            "WHERE scope_key=?", (record.scope_key,)).fetchone()
            if row is not None:
                expired = row["expires_at"] <= now
                abandoned = row["response_status"] is None and row["locked_until"] <= now
                if not (expired or abandoned):
                    return False
                c.execute("DELETE FROM core_v1_idempotency WHERE scope_key=?", (record.scope_key,))
            c.execute("INSERT INTO core_v1_idempotency VALUES (?,?,?,?,?,?)",
                      (record.scope_key, record.fingerprint, None, None,
                       record.locked_until, record.expires_at))
        return True

    def save_response(self, scope_key: str, response: StoredResponse) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE core_v1_idempotency SET response_status=?, response_body=?, locked_until=0 "
                      "WHERE scope_key=?", (response.status, json.dumps(response.body), scope_key))

    def release(self, scope_key: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM core_v1_idempotency WHERE scope_key=? AND response_status IS NULL",
                      (scope_key,))

    def purge_expired(self, now: float) -> int:
        with self.db.tx() as c:
            return c.execute("DELETE FROM core_v1_idempotency WHERE expires_at<=?", (now,)).rowcount


# ------------------------------------------------------------------- webhooks
def _sub(r: sqlite3.Row) -> WebhookSubscription:
    return WebhookSubscription(
        webhook_id=r["webhook_id"], tenant_id=r["tenant_id"], url=r["url"],
        event_filters=tuple(json.loads(r["event_filters"])), description=r["description"],
        active=bool(r["active"]), secret_ids=tuple(json.loads(r["secret_ids"])),
        max_attempts=r["max_attempts"], version=r["version"], created_by=r["created_by"],
        created_at=r["created_at"], updated_at=r["updated_at"], disabled_reason=r["disabled_reason"])


class SqliteSubscriptionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, s: WebhookSubscription) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO core_v1_webhooks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (s.webhook_id, s.tenant_id, s.url, json.dumps(list(s.event_filters)),
                       s.description, int(s.active), json.dumps(list(s.secret_ids)), s.max_attempts,
                       s.version, s.created_by, s.created_at, s.updated_at, s.disabled_reason))

    def get(self, tenant_id: str, webhook_id: str) -> WebhookSubscription | None:
        rows = self.db.query("SELECT * FROM core_v1_webhooks WHERE tenant_id=? AND webhook_id=?",
                             (tenant_id, webhook_id))
        return _sub(rows[0]) if rows else None

    def update(self, s: WebhookSubscription, expected_version: int) -> bool:
        with self.db.tx() as c:
            cur = c.execute(
                "UPDATE core_v1_webhooks SET url=?, event_filters=?, description=?, active=?, "
                "secret_ids=?, max_attempts=?, version=?, updated_at=?, disabled_reason=? "
                "WHERE tenant_id=? AND webhook_id=? AND version=?",
                (s.url, json.dumps(list(s.event_filters)), s.description, int(s.active),
                 json.dumps(list(s.secret_ids)), s.max_attempts, s.version, s.updated_at,
                 s.disabled_reason, s.tenant_id, s.webhook_id, expected_version))
            return cur.rowcount == 1

    def count_active(self, tenant_id: str) -> int:
        return self.db.query("SELECT COUNT(*) FROM core_v1_webhooks WHERE tenant_id=? AND active=1",
                             (tenant_id,))[0][0]

    def list_page(self, tenant_id: str, limit: int, after: tuple[float, str] | None) -> list[WebhookSubscription]:
        if after is None:
            rows = self.db.query("SELECT * FROM core_v1_webhooks WHERE tenant_id=? "
                                 "ORDER BY created_at, webhook_id LIMIT ?", (tenant_id, limit + 1))
        else:
            rows = self.db.query("SELECT * FROM core_v1_webhooks WHERE tenant_id=? AND "
                                 "(created_at > ? OR (created_at = ? AND webhook_id > ?)) "
                                 "ORDER BY created_at, webhook_id LIMIT ?",
                                 (tenant_id, after[0], after[0], after[1], limit + 1))
        return [_sub(r) for r in rows]

    def matching(self, tenant_id: str, event_type: str) -> list[WebhookSubscription]:
        rows = self.db.query("SELECT * FROM core_v1_webhooks WHERE tenant_id=? AND active=1 "
                             "ORDER BY created_at, webhook_id", (tenant_id,))
        return [s for s in map(_sub, rows) if s.matches(event_type)]


class SqliteSecretRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def put(self, secret_id: str, tenant_id: str, secret: bytes, created_at: float) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO core_v1_webhook_secrets VALUES (?,?,?,?)",
                      (secret_id, tenant_id, secret, created_at))

    def get(self, tenant_id: str, secret_id: str) -> bytes | None:
        rows = self.db.query("SELECT secret FROM core_v1_webhook_secrets WHERE tenant_id=? AND secret_id=?",
                             (tenant_id, secret_id))
        return bytes(rows[0][0]) if rows else None


# --------------------------------------------------------- events/deliveries
def _evt(r: sqlite3.Row) -> Event:
    return Event(r["event_id"], r["tenant_id"], r["event_type"], json.loads(r["payload"]),
                 r["dedupe_key"], r["created_at"])


def _dlv(r: sqlite3.Row) -> Delivery:
    return Delivery(r["delivery_id"], r["tenant_id"], r["webhook_id"], r["event_id"],
                    DeliveryStatus(r["status"]), r["attempts"], r["next_attempt_at"], r["lease_until"],
                    r["last_status_code"], r["last_error"], r["created_at"], r["updated_at"], r["replay_of"])


class SqliteEventRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_if_new(self, e: Event) -> Event:
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM core_v1_events WHERE tenant_id=? AND dedupe_key=?",
                            (e.tenant_id, e.dedupe_key)).fetchone()
            if row is not None:
                return _evt(row)
            c.execute("INSERT INTO core_v1_events VALUES (?,?,?,?,?,?)",
                      (e.event_id, e.tenant_id, e.event_type, json.dumps(dict(e.payload), sort_keys=True),
                       e.dedupe_key, e.created_at))
        return e

    def get(self, tenant_id: str, event_id: str) -> Event | None:
        rows = self.db.query("SELECT * FROM core_v1_events WHERE tenant_id=? AND event_id=?",
                             (tenant_id, event_id))
        return _evt(rows[0]) if rows else None


class SqliteDeliveryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_many(self, ds: Sequence[Delivery]) -> None:
        with self.db.tx() as c:
            for d in ds:
                c.execute("INSERT OR IGNORE INTO core_v1_deliveries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (d.delivery_id, d.tenant_id, d.webhook_id, d.event_id, d.status.value,
                           d.attempts, d.next_attempt_at, d.lease_until, d.last_status_code,
                           d.last_error, d.created_at, d.updated_at, d.replay_of))

    def get(self, tenant_id: str, delivery_id: str) -> Delivery | None:
        rows = self.db.query("SELECT * FROM core_v1_deliveries WHERE tenant_id=? AND delivery_id=?",
                             (tenant_id, delivery_id))
        return _dlv(rows[0]) if rows else None

    def exists_for(self, webhook_id: str, event_id: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM core_v1_deliveries WHERE webhook_id=? AND event_id=? "
                                  "AND replay_of=''", (webhook_id, event_id)))

    def claim_due(self, now: float, lease_seconds: float, limit: int) -> list[Delivery]:
        """Lease due deliveries. Expired leases (crashed worker) are reclaimable."""
        with self.db.tx() as c:
            rows = c.execute(
                "SELECT * FROM core_v1_deliveries WHERE "
                "((status IN ('pending','failed') AND next_attempt_at<=?) OR "
                " (status='in_flight' AND lease_until<=?)) "
                "ORDER BY next_attempt_at, delivery_id LIMIT ?", (now, now, limit)).fetchall()
            out = []
            for r in rows:
                c.execute("UPDATE core_v1_deliveries SET status='in_flight', lease_until=?, updated_at=? "
                          "WHERE delivery_id=?", (now + lease_seconds, now, r["delivery_id"]))
                out.append(_dlv(r))
        return [Delivery(**{**d.__dict__, "status": DeliveryStatus.IN_FLIGHT,
                            "lease_until": now + lease_seconds}) for d in out]

    def complete(self, d: Delivery, a: Attempt) -> bool:
        with self.db.tx() as c:
            cur = c.execute(
                "UPDATE core_v1_deliveries SET status=?, attempts=?, next_attempt_at=?, lease_until=0, "
                "last_status_code=?, last_error=?, updated_at=? "
                "WHERE delivery_id=? AND status='in_flight' AND attempts=?",
                (d.status.value, d.attempts, d.next_attempt_at, d.last_status_code, d.last_error,
                 d.updated_at, d.delivery_id, d.attempts - 1))
            if cur.rowcount != 1:
                return False
            c.execute("INSERT INTO core_v1_attempts VALUES (?,?,?,?,?,?,?)",
                      (a.delivery_id, a.attempt, a.started_at, a.duration_ms, a.status_code, a.error, a.outcome))
        return True

    def list_page(self, tenant_id: str, webhook_id: str, limit: int,
                  after: tuple[float, str] | None, status: str | None) -> list[Delivery]:
        sql = "SELECT * FROM core_v1_deliveries WHERE tenant_id=? AND webhook_id=?"
        args: list = [tenant_id, webhook_id]
        if status:
            sql += " AND status=?"
            args.append(status)
        if after is not None:
            sql += " AND (created_at > ? OR (created_at = ? AND delivery_id > ?))"
            args += [after[0], after[0], after[1]]
        sql += " ORDER BY created_at, delivery_id LIMIT ?"
        args.append(limit + 1)
        return [_dlv(r) for r in self.db.query(sql, tuple(args))]

    def attempts(self, delivery_id: str) -> list[Attempt]:
        rows = self.db.query("SELECT * FROM core_v1_attempts WHERE delivery_id=? ORDER BY attempt",
                             (delivery_id,))
        return [Attempt(r["delivery_id"], r["attempt"], r["started_at"], r["duration_ms"],
                        r["status_code"], r["error"], r["outcome"]) for r in rows]

"""Composition root for Backend core v1 webhooks.

Wires the SQLite adapters on ``skeleton.persistence.app_foundation.db`` to the
``WebhookService``. The DB path comes from ``SKELETON_BACKEND_CORE_DB``
(default ``data/backend_core_v1.sqlite3``); the cursor key from
``SKELETON_BACKEND_CORE_CURSOR_KEY`` (random per process when unset, which
only invalidates outstanding cursors on restart).
"""
from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass

from core.core_v1.clock import Clock, SystemClock
from core.core_v1.idempotency import Idempotency
from core.core_v1.pagination import CursorCodec
from core.core_v1.ports import Transport, UrlPolicy
from core.core_v1.service import WebhookService
from core.core_v1.sqlite_store import (SqliteDeliveryRepository, SqliteEventRepository,
                                       SqliteIdempotencyStore, SqliteSecretRepository,
                                       SqliteSubscriptionRepository, open_database)
from core.core_v1.transport import HttpTransport, PublicHttpsPolicy

DB_ENV = "SKELETON_BACKEND_CORE_DB"
CURSOR_KEY_ENV = "SKELETON_BACKEND_CORE_CURSOR_KEY"
DEFAULT_DB = "data/backend_core_v1.sqlite3"


@dataclass(frozen=True)
class CoreRuntime:
    webhooks: WebhookService
    idempotency: Idempotency


def build_runtime(db_path: str, *, clock: Clock | None = None, transport: Transport | None = None,
                  url_policy: UrlPolicy | None = None, cursor_key: bytes | None = None) -> CoreRuntime:
    db = open_database(db_path)
    clock = clock or SystemClock()
    policy = url_policy or PublicHttpsPolicy()
    service = WebhookService(
        subs=SqliteSubscriptionRepository(db), secrets=SqliteSecretRepository(db),
        events=SqliteEventRepository(db), deliveries=SqliteDeliveryRepository(db),
        transport=transport or HttpTransport(), url_policy=policy, clock=clock,
        cursor_codec=CursorCodec(cursor_key or secrets.token_bytes(32)))
    return CoreRuntime(service, Idempotency(SqliteIdempotencyStore(db), clock))


_lock = threading.Lock()
_runtime: CoreRuntime | None = None


def get_runtime() -> CoreRuntime:
    global _runtime
    with _lock:
        if _runtime is None:
            key = os.environ.get(CURSOR_KEY_ENV)
            _runtime = build_runtime(os.environ.get(DB_ENV, DEFAULT_DB),
                                     cursor_key=key.encode() if key else None)
        return _runtime


def set_runtime(runtime: CoreRuntime | None) -> None:
    """Test/composition hook."""
    global _runtime
    with _lock:
        _runtime = runtime

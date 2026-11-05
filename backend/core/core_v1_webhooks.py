"""Composition root for Backend core v1 webhooks.

Wires the SQLite adapters on ``skeleton.persistence.app_foundation.db`` to the
``WebhookService``. The DB path comes from ``SKELETON_BACKEND_CORE_DB``
(default ``data/backend_core_v1.sqlite3``); the cursor key from
``SKELETON_BACKEND_CORE_CURSOR_KEY`` (random per process when unset, which
only invalidates outstanding cursors on restart).

Secrets at rest: when ``SKELETON_BACKEND_CORE_KEKS`` is set (see
``core.core_v1.keys``) new webhook signing secrets are sealed with AES-256-GCM
envelopes and the ``/admin/secrets/*`` routes can migrate/rewrap old rows.
Production/default composition fails closed when the keyring is absent. Explicit
``key_provider=None`` is reserved for isolated development and migration tests;
no implicit plaintext fallback is permitted in the runtime entrypoint.
"""
from __future__ import annotations

import os
import secrets
import logging
import threading
from dataclasses import dataclass

from core.core_v1.clock import Clock, SystemClock
from core.core_v1.delivery_ops import DeliveryOps, SecretsAdmin
from core.core_v1.keys import KEYS_ENV, KeyProvider, KeyProviderError, provider_from_env
from core.core_v1.log_store import SqliteDeliveryLog, SqliteRetryPolicyRepository
from core.core_v1.secret_migration import SecretMigrator
from core.core_v1.secret_vault import EncryptedSecretRepository, PlaintextSecretRepository
from core.core_v1.idempotency import Idempotency
from core.core_v1.pagination import CursorCodec
from core.core_v1.ports import Transport, UrlPolicy
from core.core_v1.service import WebhookService
from core.core_v1.sqlite_store import (SqliteDeliveryRepository, SqliteEventRepository,
                                       SqliteCheckpointStore, SqliteIdempotencyStore,
                                       SqliteSecretRepository,
                                       SqliteSubscriptionRepository, open_database)
from core.core_v1.transport import HttpTransport, PublicHttpsPolicy

DB_ENV = "SKELETON_BACKEND_CORE_DB"
CURSOR_KEY_ENV = "SKELETON_BACKEND_CORE_CURSOR_KEY"
DEFAULT_DB = "data/backend_core_v1.sqlite3"
log = logging.getLogger(__name__)
_FROM_ENV = object()


@dataclass(frozen=True)
class CoreRuntime:
    webhooks: WebhookService
    idempotency: Idempotency
    ops: DeliveryOps | None = None


def build_runtime(db_path: str, *, clock: Clock | None = None, transport: Transport | None = None,
                  url_policy: UrlPolicy | None = None, cursor_key: bytes | None = None,
                  key_provider: "KeyProvider | None | object" = _FROM_ENV) -> CoreRuntime:
    """Default requires an environment KEK; explicit ``None`` is dev-only plaintext."""
    # Validate key custody before opening or creating any durable SQLite state.
    provider = provider_from_env() if key_provider is _FROM_ENV else key_provider
    if provider is None and key_provider is _FROM_ENV:
        raise KeyProviderError(f"{KEYS_ENV} is required for backend core webhook secret custody")
    db = open_database(db_path)
    clock = clock or SystemClock()
    policy = url_policy or PublicHttpsPolicy()
    blob_store = SqliteSecretRepository(db)
    if provider is None:
        log.warning("backend core v1: explicit development plaintext secret repository selected")
        secret_repo = PlaintextSecretRepository(blob_store)
    else:
        secret_repo = EncryptedSecretRepository(blob_store, provider)
    codec = CursorCodec(cursor_key or secrets.token_bytes(32))
    policies = SqliteRetryPolicyRepository(db)
    service = WebhookService(
        subs=SqliteSubscriptionRepository(db), secrets=secret_repo,
        events=SqliteEventRepository(db), deliveries=SqliteDeliveryRepository(db),
        transport=transport or HttpTransport(), url_policy=policy, clock=clock,
        cursor_codec=codec, retry_policies=policies)
    admin = None
    if provider is not None:
        admin = SecretsAdmin(SecretMigrator(blob_store, provider, SqliteCheckpointStore(db), clock.now))
    ops = DeliveryOps(webhooks=service, log=SqliteDeliveryLog(db), policies=policies,
                      cursor_codec=codec, secrets_admin=admin)
    return CoreRuntime(service, Idempotency(SqliteIdempotencyStore(db), clock), ops)


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

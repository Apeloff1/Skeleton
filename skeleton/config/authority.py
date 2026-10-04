"""Durable configuration authority and immutable snapshots for hostile gap G014.

Existing lightweight configuration helpers remain useful for local tuning, but
a production control plane needs one explicit authority contract.  This module
provides that contract as a small SQLite reference implementation.

Properties:
* snapshots are canonical-JSON, content addressed and immutable;
* activation is a compare-and-swap on the exact active generation;
* generations never move backward, including rollback;
* rollback creates a new immutable generation instead of reactivating history;
* tenant/namespace identities are part of every digest and lookup;
* persisted rows are re-hashed on read so corruption fails closed;
* callers receive decoded copies, never a mutable reference to stored state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Mapping


_SCHEMA = "skeleton.configuration_authority.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_INT = (1 << 63) - 1


class ConfigurationAuthorityError(RuntimeError):
    """Base configuration-authority failure."""


class ConfigurationConflict(ConfigurationAuthorityError):
    """The caller attempted a stale or conflicting activation."""


class ConfigurationCorruption(ConfigurationAuthorityError):
    """Persisted configuration state failed integrity validation."""


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConfigurationAuthorityError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise ConfigurationAuthorityError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ConfigurationAuthorityError(f"{field} contains control characters")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _MAX_INT
    ):
        raise ConfigurationAuthorityError(
            f"{field} must be an integer in [{minimum}, {_MAX_INT}]"
        )
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationAuthorityError(
            "configuration must be canonical-JSON encodable"
        ) from exc


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ConfigurationAuthorityError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


@dataclass(frozen=True, slots=True)
class ConfigAuthoritySnapshot:
    tenant_id: str
    namespace: str
    generation: int
    payload_json: str
    payload_digest: str
    parent_snapshot_digest: str | None
    actor_id: str
    reason: str
    created_at_ns: int
    snapshot_digest: str

    @property
    def values(self) -> Any:
        return json.loads(self.payload_json)

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "tenant_id": self.tenant_id,
            "namespace": self.namespace,
            "generation": self.generation,
            "payload_digest": self.payload_digest,
            "parent_snapshot_digest": self.parent_snapshot_digest,
            "actor_id": self.actor_id,
            "reason": self.reason,
            "created_at_ns": self.created_at_ns,
        }


class SQLiteConfigurationAuthority:
    """Crash-stable configuration snapshot/activation authority."""

    def __init__(self, path: str | Path = ":memory:") -> None:
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
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS config_snapshot (
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    parent_snapshot_digest TEXT,
                    actor_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_ns INTEGER NOT NULL,
                    snapshot_digest TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, namespace, generation),
                    UNIQUE(tenant_id, namespace, snapshot_digest)
                );

                CREATE TABLE IF NOT EXISTS config_active (
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    snapshot_digest TEXT NOT NULL,
                    updated_at_ns INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id, namespace)
                );
                """
            )

    @staticmethod
    def _now(value: int | None) -> int:
        return _integer(time.time_ns() if value is None else value, "now_ns", minimum=1)

    @staticmethod
    def _build_snapshot(
        *,
        tenant_id: str,
        namespace: str,
        generation: int,
        values: object,
        parent_snapshot_digest: str | None,
        actor_id: str,
        reason: str,
        created_at_ns: int,
    ) -> ConfigAuthoritySnapshot:
        tenant = _text(tenant_id, "tenant_id")
        scope = _text(namespace, "namespace")
        generation = _integer(generation, "generation", minimum=1)
        actor = _text(actor_id, "actor_id")
        reason = _text(reason, "reason", maximum=1024)
        created = _integer(created_at_ns, "created_at_ns", minimum=1)
        if parent_snapshot_digest is not None:
            parent_snapshot_digest = _digest(
                parent_snapshot_digest, "parent_snapshot_digest"
            )
        payload_json = _canonical_json(values)
        payload_digest = _sha256(payload_json)
        identity = {
            "schema": _SCHEMA,
            "tenant_id": tenant,
            "namespace": scope,
            "generation": generation,
            "payload_digest": payload_digest,
            "parent_snapshot_digest": parent_snapshot_digest,
            "actor_id": actor,
            "reason": reason,
            "created_at_ns": created,
        }
        return ConfigAuthoritySnapshot(
            tenant_id=tenant,
            namespace=scope,
            generation=generation,
            payload_json=payload_json,
            payload_digest=payload_digest,
            parent_snapshot_digest=parent_snapshot_digest,
            actor_id=actor,
            reason=reason,
            created_at_ns=created,
            snapshot_digest=_sha256(_canonical_json(identity)),
        )

    def _active_row(self, tenant_id: str, namespace: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT generation, snapshot_digest, updated_at_ns
            FROM config_active
            WHERE tenant_id = ? AND namespace = ?
            """,
            (tenant_id, namespace),
        ).fetchone()

    def commit(
        self,
        *,
        tenant_id: str,
        namespace: str,
        expected_generation: int,
        actor_id: str,
        reason: str,
        values: object,
        now_ns: int | None = None,
    ) -> ConfigAuthoritySnapshot:
        """Create and atomically activate one immutable generation."""

        tenant = _text(tenant_id, "tenant_id")
        scope = _text(namespace, "namespace")
        expected = _integer(expected_generation, "expected_generation")
        now = self._now(now_ns)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                active = self._active_row(tenant, scope)
                current_generation = 0 if active is None else int(active["generation"])
                if current_generation != expected:
                    raise ConfigurationConflict(
                        f"stale config generation: expected {expected}, current {current_generation}"
                    )
                if current_generation >= _MAX_INT:
                    raise ConfigurationAuthorityError("configuration generation exhausted")
                parent_digest = None if active is None else str(active["snapshot_digest"])
                snapshot = self._build_snapshot(
                    tenant_id=tenant,
                    namespace=scope,
                    generation=current_generation + 1,
                    values=values,
                    parent_snapshot_digest=parent_digest,
                    actor_id=actor_id,
                    reason=reason,
                    created_at_ns=now,
                )
                self._connection.execute(
                    """
                    INSERT INTO config_snapshot(
                        tenant_id, namespace, generation, payload_json,
                        payload_digest, parent_snapshot_digest, actor_id,
                        reason, created_at_ns, snapshot_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.tenant_id,
                        snapshot.namespace,
                        snapshot.generation,
                        snapshot.payload_json,
                        snapshot.payload_digest,
                        snapshot.parent_snapshot_digest,
                        snapshot.actor_id,
                        snapshot.reason,
                        snapshot.created_at_ns,
                        snapshot.snapshot_digest,
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO config_active(
                        tenant_id, namespace, generation, snapshot_digest, updated_at_ns
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, namespace) DO UPDATE SET
                        generation = excluded.generation,
                        snapshot_digest = excluded.snapshot_digest,
                        updated_at_ns = excluded.updated_at_ns
                    """,
                    (tenant, scope, snapshot.generation, snapshot.snapshot_digest, now),
                )
                self._connection.execute("COMMIT")
                return snapshot
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def _decode_row(self, row: sqlite3.Row) -> ConfigAuthoritySnapshot:
        try:
            payload_json = str(row["payload_json"])
            parsed = json.loads(payload_json)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ConfigurationCorruption("persisted config payload is invalid JSON") from exc
        canonical = _canonical_json(parsed)
        if canonical != payload_json:
            raise ConfigurationCorruption("persisted config payload is not canonical JSON")
        payload_digest = _sha256(payload_json)
        if payload_digest != row["payload_digest"]:
            raise ConfigurationCorruption("persisted config payload digest mismatch")
        snapshot = self._build_snapshot(
            tenant_id=row["tenant_id"],
            namespace=row["namespace"],
            generation=int(row["generation"]),
            values=parsed,
            parent_snapshot_digest=row["parent_snapshot_digest"],
            actor_id=row["actor_id"],
            reason=row["reason"],
            created_at_ns=int(row["created_at_ns"]),
        )
        if snapshot.snapshot_digest != row["snapshot_digest"]:
            raise ConfigurationCorruption("persisted config snapshot digest mismatch")
        return snapshot

    def read_generation(
        self, *, tenant_id: str, namespace: str, generation: int
    ) -> ConfigAuthoritySnapshot:
        tenant = _text(tenant_id, "tenant_id")
        scope = _text(namespace, "namespace")
        generation = _integer(generation, "generation", minimum=1)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM config_snapshot
                WHERE tenant_id = ? AND namespace = ? AND generation = ?
                """,
                (tenant, scope, generation),
            ).fetchone()
        if row is None:
            raise ConfigurationAuthorityError("configuration generation not found")
        return self._decode_row(row)

    def read_snapshot(
        self, *, tenant_id: str, namespace: str, snapshot_digest: str
    ) -> ConfigAuthoritySnapshot:
        tenant = _text(tenant_id, "tenant_id")
        scope = _text(namespace, "namespace")
        digest = _digest(snapshot_digest, "snapshot_digest")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM config_snapshot
                WHERE tenant_id = ? AND namespace = ? AND snapshot_digest = ?
                """,
                (tenant, scope, digest),
            ).fetchone()
        if row is None:
            raise ConfigurationAuthorityError("configuration snapshot not found")
        return self._decode_row(row)

    def active(self, *, tenant_id: str, namespace: str) -> ConfigAuthoritySnapshot | None:
        tenant = _text(tenant_id, "tenant_id")
        scope = _text(namespace, "namespace")
        with self._lock:
            active = self._active_row(tenant, scope)
            if active is None:
                return None
            row = self._connection.execute(
                """
                SELECT * FROM config_snapshot
                WHERE tenant_id = ? AND namespace = ? AND generation = ?
                """,
                (tenant, scope, int(active["generation"])),
            ).fetchone()
        if row is None:
            raise ConfigurationCorruption("active config points to missing snapshot")
        snapshot = self._decode_row(row)
        if snapshot.snapshot_digest != active["snapshot_digest"]:
            raise ConfigurationCorruption("active config digest does not match snapshot")
        return snapshot

    def rollback(
        self,
        *,
        tenant_id: str,
        namespace: str,
        expected_generation: int,
        target_generation: int,
        actor_id: str,
        reason: str,
        now_ns: int | None = None,
    ) -> ConfigAuthoritySnapshot:
        """Rollback by copying old values into a new monotonic generation."""

        target = self.read_generation(
            tenant_id=tenant_id,
            namespace=namespace,
            generation=target_generation,
        )
        return self.commit(
            tenant_id=tenant_id,
            namespace=namespace,
            expected_generation=expected_generation,
            actor_id=actor_id,
            reason=reason,
            values=target.values,
            now_ns=now_ns,
        )

    def verify_chain(self, *, tenant_id: str, namespace: str) -> tuple[str, ...]:
        tenant = _text(tenant_id, "tenant_id")
        scope = _text(namespace, "namespace")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM config_snapshot
                WHERE tenant_id = ? AND namespace = ?
                ORDER BY generation ASC
                """,
                (tenant, scope),
            ).fetchall()
        previous: str | None = None
        digests: list[str] = []
        for expected_generation, row in enumerate(rows, start=1):
            snapshot = self._decode_row(row)
            if snapshot.generation != expected_generation:
                raise ConfigurationCorruption("configuration generations are not contiguous")
            if snapshot.parent_snapshot_digest != previous:
                raise ConfigurationCorruption("configuration parent chain is broken")
            previous = snapshot.snapshot_digest
            digests.append(snapshot.snapshot_digest)
        return tuple(digests)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteConfigurationAuthority":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

"""Durable configuration authority and immutable snapshots for hostile gap G014.

The repository already contains convenience snapshot helpers, but those helpers
are process-local or best-effort. This module defines the authoritative runtime
configuration contract for the canonical `skeleton/config` plane.

Laws:
* snapshots are deep-immutable canonical-JSON values;
* every snapshot is content-addressed and parent-chained;
* proposal never mutates the active configuration;
* activation is compare-and-swap fenced by the active-head generation;
* normal activation must descend from the current active snapshot;
* rollback is explicit, audited, and also head-generation fenced;
* persisted snapshots are verified before they are returned;
* secret-shaped material is rejected from configuration snapshots;
* restart/reopen preserves the active head and immutable history.

Secret material belongs in the secret/vault plane. Configuration may carry
opaque references, but not credential values.
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
from types import MappingProxyType
from typing import Any, Mapping


_SCHEMA = "skeleton.config_authority.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_INT = (1 << 63) - 1

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
        "api_key",
        "private_key",
        "client_secret",
        "access_token",
        "refresh_token",
    }
)
_SENSITIVE_SUFFIXES = (
    "_credential",
    "_credentials",
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_private_key",
    "_client_secret",
    "_access_token",
    "_refresh_token",
)


class ConfigAuthorityError(RuntimeError):
    """Base configuration authority failure."""


class ConfigConflict(ConfigAuthorityError):
    """Caller head/version assumptions no longer match authority."""


class ConfigCorruption(ConfigAuthorityError):
    """Persisted configuration state cannot be trusted."""


class ConfigSecretMaterialError(ConfigAuthorityError):
    """Secret-shaped material was attempted in canonical configuration."""


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConfigAuthorityError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise ConfigAuthorityError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ConfigAuthorityError(f"{field} contains control characters")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _MAX_INT
    ):
        raise ConfigAuthorityError(
            f"{field} must be an integer in [{minimum}, {_MAX_INT}]"
        )
    return value


def _now(value: int | None) -> int:
    return _integer(time.time_ns() if value is None else value, "now_ns", minimum=1)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def _validate_value(value: object, path: str = "$", *, depth: int = 0) -> None:
    if depth > 32:
        raise ConfigAuthorityError("configuration exceeds maximum nesting depth")
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ConfigAuthorityError(f"{path} contains non-finite number")
        return
    if isinstance(value, bytes):
        raise ConfigAuthorityError(f"{path} cannot contain bytes")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_value(item, f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key or key != key.strip():
                raise ConfigAuthorityError(
                    f"{path} keys must be canonical non-empty strings"
                )
            if _is_sensitive_key(key):
                raise ConfigSecretMaterialError(
                    f"secret-shaped configuration field rejected: {path}.{key}"
                )
            _validate_value(item, f"{path}.{key}", depth=depth + 1)
        return
    raise ConfigAuthorityError(
        f"{path} contains unsupported configuration type {type(value).__name__}"
    )


def _canonical_json(value: object) -> str:
    _validate_value(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigAuthorityError(
            "configuration must be canonical JSON"
        ) from exc


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze(value[key]) for key in sorted(value)}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _digest_payload(
    *,
    namespace: str,
    version: int,
    parent_digest: str | None,
    values: object,
) -> str:
    payload = {
        "schema": _SCHEMA,
        "namespace": namespace,
        "version": version,
        "parent_digest": parent_digest,
        "values": values,
    }
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    namespace: str
    version: int
    parent_digest: str | None
    digest: str
    values: Mapping[str, Any]
    actor_id: str
    reason: str
    created_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _text(self.namespace, "namespace"))
        object.__setattr__(
            self,
            "version",
            _integer(self.version, "version", minimum=1),
        )
        if self.parent_digest is not None:
            if (
                not isinstance(self.parent_digest, str)
                or _SHA256.fullmatch(self.parent_digest) is None
            ):
                raise ConfigAuthorityError(
                    "parent_digest must be lowercase SHA-256 or null"
                )
        if not isinstance(self.digest, str) or _SHA256.fullmatch(self.digest) is None:
            raise ConfigAuthorityError("digest must be lowercase SHA-256")
        object.__setattr__(self, "actor_id", _text(self.actor_id, "actor_id"))
        object.__setattr__(self, "reason", _text(self.reason, "reason", maximum=2048))
        object.__setattr__(
            self,
            "created_at_ns",
            _integer(self.created_at_ns, "created_at_ns", minimum=1),
        )
        material = _thaw(self.values)
        if not isinstance(material, dict):
            raise ConfigAuthorityError("snapshot values must be an object")
        canonical = json.loads(_canonical_json(material))
        expected = _digest_payload(
            namespace=self.namespace,
            version=self.version,
            parent_digest=self.parent_digest,
            values=canonical,
        )
        if expected != self.digest:
            raise ConfigAuthorityError("snapshot digest mismatch")
        object.__setattr__(self, "values", _freeze(canonical))

    def get(self, path: str, default: Any = None) -> Any:
        current: object = self.values
        for key in _text(path, "path").split("."):
            if not isinstance(current, Mapping) or key not in current:
                return default
            current = current[key]
        return current

    def payload(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "version": self.version,
            "parent_digest": self.parent_digest,
            "digest": self.digest,
            "values": _thaw(self.values),
            "actor_id": self.actor_id,
            "reason": self.reason,
            "created_at_ns": self.created_at_ns,
            "secret_material_present": False,
        }


@dataclass(frozen=True, slots=True)
class ConfigHead:
    namespace: str
    generation: int
    active_version: int | None
    active_digest: str | None
    updated_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _text(self.namespace, "namespace"))
        object.__setattr__(
            self,
            "generation",
            _integer(self.generation, "generation", minimum=0),
        )
        if self.active_version is None:
            if self.active_digest is not None:
                raise ConfigAuthorityError(
                    "empty config head cannot carry active_digest"
                )
        else:
            object.__setattr__(
                self,
                "active_version",
                _integer(self.active_version, "active_version", minimum=1),
            )
            if (
                not isinstance(self.active_digest, str)
                or _SHA256.fullmatch(self.active_digest) is None
            ):
                raise ConfigAuthorityError(
                    "active_digest must be lowercase SHA-256"
                )
        object.__setattr__(
            self,
            "updated_at_ns",
            _integer(self.updated_at_ns, "updated_at_ns", minimum=0),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "generation": self.generation,
            "active_version": self.active_version,
            "active_digest": self.active_digest,
            "updated_at_ns": self.updated_at_ns,
        }


class SQLiteConfigAuthority:
    """Durable immutable configuration snapshot authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "runtime_config",
    ) -> None:
        self.namespace = _text(namespace, "namespace")
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,
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
                    namespace TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    parent_digest TEXT,
                    snapshot_digest TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_ns INTEGER NOT NULL,
                    PRIMARY KEY(namespace, version),
                    UNIQUE(namespace, snapshot_digest)
                );

                CREATE TABLE IF NOT EXISTS config_head (
                    namespace TEXT PRIMARY KEY,
                    generation INTEGER NOT NULL,
                    active_version INTEGER,
                    active_digest TEXT,
                    updated_at_ns INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS config_transition (
                    namespace TEXT NOT NULL,
                    head_generation INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    from_version INTEGER,
                    to_version INTEGER,
                    actor_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    at_ns INTEGER NOT NULL,
                    PRIMARY KEY(namespace, head_generation)
                );
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO config_head(
                    namespace, generation, active_version,
                    active_digest, updated_at_ns
                ) VALUES (?, 0, NULL, NULL, 0)
                """,
                (self.namespace,),
            )

    def propose(
        self,
        values: Mapping[str, Any],
        *,
        actor_id: str,
        reason: str,
        now_ns: int | None = None,
    ) -> ConfigSnapshot:
        actor = _text(actor_id, "actor_id")
        why = _text(reason, "reason", maximum=2048)
        instant = _now(now_ns)
        if not isinstance(values, Mapping):
            raise ConfigAuthorityError("values must be a mapping")
        material = dict(values)
        values_json = _canonical_json(material)
        canonical = json.loads(values_json)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                head = self._head_from_row(self._head_row())
                row = self._connection.execute(
                    """
                    SELECT MAX(version) AS n
                    FROM config_snapshot
                    WHERE namespace = ?
                    """,
                    (self.namespace,),
                ).fetchone()
                latest = 0 if row["n"] is None else _integer(
                    row["n"], "persisted latest version", minimum=1
                )
                version = latest + 1
                if version > _MAX_INT:
                    raise ConfigCorruption("configuration version exhausted")
                parent_digest = head.active_digest
                digest = _digest_payload(
                    namespace=self.namespace,
                    version=version,
                    parent_digest=parent_digest,
                    values=canonical,
                )
                self._connection.execute(
                    """
                    INSERT INTO config_snapshot(
                        namespace, version, parent_digest, snapshot_digest,
                        values_json, actor_id, reason, created_at_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        version,
                        parent_digest,
                        digest,
                        values_json,
                        actor,
                        why,
                        instant,
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.read_snapshot(version)

    def activate(
        self,
        *,
        version: int,
        expected_head_generation: int,
        actor_id: str,
        reason: str,
        now_ns: int | None = None,
    ) -> ConfigHead:
        return self._move_head(
            version=version,
            expected_head_generation=expected_head_generation,
            actor_id=actor_id,
            reason=reason,
            action="activate",
            allow_non_descendant=False,
            now_ns=now_ns,
        )

    def rollback(
        self,
        *,
        version: int,
        expected_head_generation: int,
        actor_id: str,
        reason: str,
        now_ns: int | None = None,
    ) -> ConfigHead:
        return self._move_head(
            version=version,
            expected_head_generation=expected_head_generation,
            actor_id=actor_id,
            reason=reason,
            action="rollback",
            allow_non_descendant=True,
            now_ns=now_ns,
        )

    def read_snapshot(self, version: int) -> ConfigSnapshot:
        target = _integer(version, "version", minimum=1)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT *
                FROM config_snapshot
                WHERE namespace = ? AND version = ?
                """,
                (self.namespace, target),
            ).fetchone()
        if row is None:
            raise ConfigAuthorityError("unknown configuration snapshot")
        return self._snapshot_from_row(row)

    def active_snapshot(self) -> ConfigSnapshot | None:
        head = self.head()
        if head.active_version is None:
            return None
        snapshot = self.read_snapshot(head.active_version)
        if snapshot.digest != head.active_digest:
            raise ConfigCorruption("active head digest disagrees with snapshot")
        return snapshot

    def head(self) -> ConfigHead:
        with self._lock:
            return self._head_from_row(self._head_row())

    def history(self) -> tuple[ConfigSnapshot, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM config_snapshot
                WHERE namespace = ?
                ORDER BY version ASC
                """,
                (self.namespace,),
            ).fetchall()
        snapshots = tuple(self._snapshot_from_row(row) for row in rows)
        for index, snapshot in enumerate(snapshots):
            if snapshot.version != index + 1:
                raise ConfigCorruption("configuration history version gap")
        return snapshots

    def transition_log(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT head_generation, action, from_version, to_version,
                       actor_id, reason, at_ns
                FROM config_transition
                WHERE namespace = ?
                ORDER BY head_generation ASC
                """,
                (self.namespace,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        expected_generation = 1
        for row in rows:
            generation = _integer(
                row["head_generation"],
                "persisted transition generation",
                minimum=1,
            )
            if generation != expected_generation:
                raise ConfigCorruption("configuration transition generation gap")
            expected_generation += 1
            action = row["action"]
            if action not in {"activate", "rollback"}:
                raise ConfigCorruption("unknown configuration transition action")
            result.append(
                {
                    "head_generation": generation,
                    "action": action,
                    "from_version": row["from_version"],
                    "to_version": _integer(
                        row["to_version"],
                        "persisted transition to_version",
                        minimum=1,
                    ),
                    "actor_id": _text(row["actor_id"], "persisted actor_id"),
                    "reason": _text(
                        row["reason"],
                        "persisted reason",
                        maximum=2048,
                    ),
                    "at_ns": _integer(
                        row["at_ns"],
                        "persisted transition at_ns",
                        minimum=1,
                    ),
                }
            )
        return tuple(result)

    def card(self) -> dict[str, Any]:
        head = self.head()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COUNT(*) AS n FROM config_snapshot
                WHERE namespace = ?
                """,
                (self.namespace,),
            ).fetchone()
        return {
            "kind": "configuration_authority",
            "gap": "G014",
            "law": "immutable-snapshot-parent-chain-plus-head-cas",
            "snapshot_count": int(row["n"]),
            "head": head.payload(),
            "secret_material_present": False,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _move_head(
        self,
        *,
        version: int,
        expected_head_generation: int,
        actor_id: str,
        reason: str,
        action: str,
        allow_non_descendant: bool,
        now_ns: int | None,
    ) -> ConfigHead:
        target_version = _integer(version, "version", minimum=1)
        expected_generation = _integer(
            expected_head_generation,
            "expected_head_generation",
            minimum=0,
        )
        actor = _text(actor_id, "actor_id")
        why = _text(reason, "reason", maximum=2048)
        instant = _now(now_ns)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                head = self._head_from_row(self._head_row())
                if head.generation != expected_generation:
                    raise ConfigConflict("stale configuration head generation")
                target_row = self._connection.execute(
                    """
                    SELECT * FROM config_snapshot
                    WHERE namespace = ? AND version = ?
                    """,
                    (self.namespace, target_version),
                ).fetchone()
                if target_row is None:
                    raise ConfigAuthorityError("unknown configuration snapshot")
                target = self._snapshot_from_row(target_row)
                if (
                    not allow_non_descendant
                    and target.parent_digest != head.active_digest
                ):
                    raise ConfigConflict(
                        "activation candidate does not descend from active head"
                    )
                if (
                    head.active_version == target.version
                    and head.active_digest == target.digest
                ):
                    raise ConfigConflict("configuration snapshot is already active")
                generation = head.generation + 1
                if generation > _MAX_INT:
                    raise ConfigCorruption("configuration head generation exhausted")
                cursor = self._connection.execute(
                    """
                    UPDATE config_head
                    SET generation = ?, active_version = ?,
                        active_digest = ?, updated_at_ns = ?
                    WHERE namespace = ? AND generation = ?
                    """,
                    (
                        generation,
                        target.version,
                        target.digest,
                        instant,
                        self.namespace,
                        expected_generation,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConfigConflict("configuration head CAS lost race")
                self._connection.execute(
                    """
                    INSERT INTO config_transition(
                        namespace, head_generation, action,
                        from_version, to_version, actor_id, reason, at_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        generation,
                        action,
                        head.active_version,
                        target.version,
                        actor,
                        why,
                        instant,
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.head()

    def _head_row(self) -> sqlite3.Row:
        row = self._connection.execute(
            """
            SELECT generation, active_version, active_digest, updated_at_ns
            FROM config_head
            WHERE namespace = ?
            """,
            (self.namespace,),
        ).fetchone()
        if row is None:
            raise ConfigCorruption("configuration head is missing")
        return row

    def _head_from_row(self, row: sqlite3.Row) -> ConfigHead:
        try:
            return ConfigHead(
                namespace=self.namespace,
                generation=_integer(
                    row["generation"],
                    "persisted head generation",
                    minimum=0,
                ),
                active_version=(
                    None
                    if row["active_version"] is None
                    else _integer(
                        row["active_version"],
                        "persisted active_version",
                        minimum=1,
                    )
                ),
                active_digest=row["active_digest"],
                updated_at_ns=_integer(
                    row["updated_at_ns"],
                    "persisted head updated_at_ns",
                    minimum=0,
                ),
            )
        except ConfigAuthorityError as exc:
            raise ConfigCorruption("persisted configuration head is invalid") from exc

    def _snapshot_from_row(self, row: sqlite3.Row) -> ConfigSnapshot:
        try:
            values = json.loads(row["values_json"])
            if not isinstance(values, dict):
                raise ConfigAuthorityError("persisted values must be object")
            canonical = _canonical_json(values)
            if canonical != row["values_json"]:
                raise ConfigAuthorityError(
                    "persisted configuration JSON is not canonical"
                )
            snapshot = ConfigSnapshot(
                namespace=self.namespace,
                version=_integer(
                    row["version"],
                    "persisted version",
                    minimum=1,
                ),
                parent_digest=row["parent_digest"],
                digest=row["snapshot_digest"],
                values=_freeze(values),
                actor_id=row["actor_id"],
                reason=row["reason"],
                created_at_ns=_integer(
                    row["created_at_ns"],
                    "persisted created_at_ns",
                    minimum=1,
                ),
            )
            return snapshot
        except (
            json.JSONDecodeError,
            ConfigAuthorityError,
        ) as exc:
            raise ConfigCorruption(
                "persisted configuration snapshot is invalid"
            ) from exc

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteConfigAuthority":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "ConfigAuthorityError",
    "ConfigConflict",
    "ConfigCorruption",
    "ConfigHead",
    "ConfigSecretMaterialError",
    "ConfigSnapshot",
    "SQLiteConfigAuthority",
]

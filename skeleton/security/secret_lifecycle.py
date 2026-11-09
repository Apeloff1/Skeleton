"""Durable secret lifecycle and taint propagation contract for hostile gap G011.

This module deliberately stores no secret material. It complements the
credential vault and opaque secret-handle contracts by making lifecycle and
derived-value taint state explicit, durable, tenant-scoped, and fail closed.

Core laws
---------
* one handle version has one immutable tenant/provider/owner identity;
* only the current ACTIVE version may authorize secret use;
* rotation atomically retires the prior version and activates a new version;
* revocation and destruction survive process restart;
* a value derived from any secret-tainted input remains secret-tainted;
* taint lineage is a canonical union of exact secret-version identities;
* secret taint cannot be silently cleared or replaced with caller assertions;
* rotation/revocation/destruction makes prior taint stale for secret-aware use;
* untrusted sinks must prove a value is untainted before emission.

This is lifecycle/taint metadata authority only. Secret plaintext, ciphertext,
keys, and material digests are intentionally outside this database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterable

from skeleton.security.secret_handles import SecretRef


_SCHEMA = "skeleton.secret_lifecycle_taint.v1"
_MAX_NS = (1 << 63) - 1


class SecretLifecycleError(RuntimeError):
    """Base failure for lifecycle or taint policy."""


class SecretLifecycleConflict(SecretLifecycleError):
    """Caller state no longer matches canonical lifecycle state."""


class SecretLifecycleCorruption(SecretLifecycleError):
    """Persisted lifecycle or taint state is malformed."""


class SecretVersionUnavailable(SecretLifecycleError):
    """Secret version cannot authorize new use."""


class SecretTaintViolation(SecretLifecycleError):
    """Secret-tainted data reached a sink that requires untainted data."""


class SecretTaintStale(SecretLifecycleError):
    """Taint lineage references a no-longer-active secret version."""


class SecretVersionState(str, Enum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    DESTROYED = "destroyed"


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SecretLifecycleError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise SecretLifecycleError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise SecretLifecycleError(f"{field} contains control characters")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _MAX_NS
    ):
        raise SecretLifecycleError(
            f"{field} must be an integer in [{minimum}, {_MAX_NS}]"
        )
    return value


def _now(value: int | None) -> int:
    return _integer(time.time_ns() if value is None else value, "now_ns", minimum=1)


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
        raise SecretLifecycleError("lifecycle payload must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SecretVersionIdentity:
    tenant_id: str
    owner_id: str
    handle_id: str
    provider_id: str
    version_id: str
    generation: int

    def __post_init__(self) -> None:
        for field in (
            "tenant_id",
            "owner_id",
            "handle_id",
            "provider_id",
            "version_id",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "generation",
            _integer(self.generation, "generation", minimum=1),
        )

    @property
    def ref(self) -> SecretRef:
        return SecretRef(
            handle_id=self.handle_id,
            provider_id=self.provider_id,
            version_id=self.version_id,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "handle_id": self.handle_id,
            "provider_id": self.provider_id,
            "version_id": self.version_id,
            "generation": self.generation,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class SecretLifecycleRecord:
    identity: SecretVersionIdentity
    state: SecretVersionState
    created_at_ns: int
    state_changed_at_ns: int
    superseded_by_version_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SecretVersionIdentity):
            raise SecretLifecycleError("identity must be SecretVersionIdentity")
        try:
            state = SecretVersionState(self.state)
        except ValueError as exc:
            raise SecretLifecycleError("invalid secret lifecycle state") from exc
        object.__setattr__(self, "state", state)
        created = _integer(self.created_at_ns, "created_at_ns", minimum=1)
        changed = _integer(self.state_changed_at_ns, "state_changed_at_ns", minimum=1)
        if changed < created:
            raise SecretLifecycleError("state_changed_at_ns cannot predate creation")
        if self.superseded_by_version_id is not None:
            object.__setattr__(
                self,
                "superseded_by_version_id",
                _text(
                    self.superseded_by_version_id,
                    "superseded_by_version_id",
                ),
            )
        if state is SecretVersionState.ROTATED and self.superseded_by_version_id is None:
            raise SecretLifecycleError("rotated version requires successor identity")
        if state is not SecretVersionState.ROTATED and self.superseded_by_version_id is not None:
            raise SecretLifecycleError(
                "only rotated versions may identify a successor"
            )

    @property
    def usable(self) -> bool:
        return self.state is SecretVersionState.ACTIVE

    def payload(self) -> dict[str, Any]:
        return {
            "identity": self.identity.payload(),
            "state": self.state.value,
            "created_at_ns": self.created_at_ns,
            "state_changed_at_ns": self.state_changed_at_ns,
            "superseded_by_version_id": self.superseded_by_version_id,
            "secret_material_present": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class SecretTaint:
    tenant_id: str
    value_id: str
    sources: tuple[SecretVersionIdentity, ...]
    parent_value_ids: tuple[str, ...]
    transformation_id: str
    created_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "value_id", _text(self.value_id, "value_id"))
        object.__setattr__(
            self,
            "transformation_id",
            _text(self.transformation_id, "transformation_id"),
        )
        object.__setattr__(
            self,
            "created_at_ns",
            _integer(self.created_at_ns, "created_at_ns", minimum=1),
        )
        if not isinstance(self.sources, tuple) or not self.sources:
            raise SecretLifecycleError("taint sources must be a non-empty tuple")
        for source in self.sources:
            if not isinstance(source, SecretVersionIdentity):
                raise SecretLifecycleError(
                    "taint sources must contain SecretVersionIdentity values"
                )
            if source.tenant_id != self.tenant_id:
                raise SecretLifecycleError("cross-tenant taint source forbidden")
        canonical_sources = tuple(
            sorted(
                set(self.sources),
                key=lambda item: (
                    item.provider_id,
                    item.handle_id,
                    item.generation,
                    item.version_id,
                    item.owner_id,
                ),
            )
        )
        if canonical_sources != self.sources:
            raise SecretLifecycleError("taint sources must be canonical and unique")
        if not isinstance(self.parent_value_ids, tuple):
            raise SecretLifecycleError("parent_value_ids must be a tuple")
        parents = tuple(sorted({_text(v, "parent_value_id") for v in self.parent_value_ids}))
        if parents != self.parent_value_ids:
            raise SecretLifecycleError("parent_value_ids must be canonical and unique")
        if self.value_id in parents:
            raise SecretLifecycleError("value cannot be its own taint parent")

    def payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "value_id": self.value_id,
            "sources": [source.payload() for source in self.sources],
            "parent_value_ids": list(self.parent_value_ids),
            "transformation_id": self.transformation_id,
            "created_at_ns": self.created_at_ns,
            "secret_material_present": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class SecretSinkDecision:
    tenant_id: str
    value_id: str
    sink_id: str
    secret_aware: bool
    allowed: bool
    reason_code: str
    source_digests: tuple[str, ...]
    decided_at_ns: int

    def __post_init__(self) -> None:
        for field in ("tenant_id", "value_id", "sink_id", "reason_code"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if not isinstance(self.secret_aware, bool) or not isinstance(self.allowed, bool):
            raise SecretLifecycleError("sink booleans must be boolean")
        object.__setattr__(
            self,
            "source_digests",
            tuple(sorted({_text(v, "source_digest", maximum=64) for v in self.source_digests})),
        )
        object.__setattr__(
            self,
            "decided_at_ns",
            _integer(self.decided_at_ns, "decided_at_ns", minimum=1),
        )
        if self.allowed and not self.secret_aware and self.source_digests:
            raise SecretLifecycleError(
                "untainted-only sink cannot allow a tainted value"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "value_id": self.value_id,
            "sink_id": self.sink_id,
            "secret_aware": self.secret_aware,
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "source_digests": list(self.source_digests),
            "decided_at_ns": self.decided_at_ns,
            "secret_material_present": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


class SQLiteSecretLifecycle:
    """Durable secret-version lifecycle and taint metadata authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "secret_lifecycle",
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

                CREATE TABLE IF NOT EXISTS secret_version_lifecycle (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    handle_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at_ns INTEGER NOT NULL,
                    state_changed_at_ns INTEGER NOT NULL,
                    superseded_by_version_id TEXT,
                    PRIMARY KEY(namespace, tenant_id, provider_id, handle_id, version_id),
                    UNIQUE(namespace, tenant_id, provider_id, handle_id, generation)
                );

                CREATE TABLE IF NOT EXISTS secret_taint (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    value_id TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    parent_value_ids_json TEXT NOT NULL,
                    transformation_id TEXT NOT NULL,
                    created_at_ns INTEGER NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, value_id)
                );
                """
            )

    def register_version(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        secret_ref: SecretRef,
        now_ns: int | None = None,
    ) -> SecretLifecycleRecord:
        tenant = _text(tenant_id, "tenant_id")
        owner = _text(owner_id, "owner_id")
        self._require_ref(secret_ref)
        instant = _now(now_ns)
        with self._lock:
            self._begin()
            try:
                existing = self._version_row(
                    tenant, secret_ref.provider_id, secret_ref.handle_id, secret_ref.version_id
                )
                if existing is not None:
                    record = self._record_from_row(existing)
                    if record.identity.owner_id != owner:
                        raise SecretLifecycleConflict(
                            "existing secret version owner mismatch"
                        )
                    self._commit()
                    return record

                active = self._active_row(
                    tenant, secret_ref.provider_id, secret_ref.handle_id
                )
                if active is not None:
                    raise SecretLifecycleConflict(
                        "handle already has an active version; rotate explicitly"
                    )
                latest_generation = self._latest_generation(
                    tenant, secret_ref.provider_id, secret_ref.handle_id
                )
                generation = latest_generation + 1
                identity = SecretVersionIdentity(
                    tenant_id=tenant,
                    owner_id=owner,
                    handle_id=secret_ref.handle_id,
                    provider_id=secret_ref.provider_id,
                    version_id=secret_ref.version_id,
                    generation=generation,
                )
                self._insert_record(
                    SecretLifecycleRecord(
                        identity=identity,
                        state=SecretVersionState.ACTIVE,
                        created_at_ns=instant,
                        state_changed_at_ns=instant,
                    )
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.read_version(
            tenant_id=tenant,
            secret_ref=secret_ref,
        )

    def rotate(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        current_ref: SecretRef,
        new_ref: SecretRef,
        expected_generation: int,
        now_ns: int | None = None,
    ) -> tuple[SecretLifecycleRecord, SecretLifecycleRecord]:
        tenant = _text(tenant_id, "tenant_id")
        owner = _text(owner_id, "owner_id")
        self._require_ref(current_ref)
        self._require_ref(new_ref)
        expected = _integer(expected_generation, "expected_generation", minimum=1)
        instant = _now(now_ns)
        if current_ref.handle_id != new_ref.handle_id:
            raise SecretLifecycleError("rotation cannot change handle_id")
        if current_ref.provider_id != new_ref.provider_id:
            raise SecretLifecycleError("rotation cannot silently change provider_id")
        if current_ref.version_id == new_ref.version_id:
            raise SecretLifecycleError("rotation requires a new version_id")

        with self._lock:
            self._begin()
            try:
                current_row = self._version_row(
                    tenant,
                    current_ref.provider_id,
                    current_ref.handle_id,
                    current_ref.version_id,
                )
                if current_row is None:
                    raise SecretLifecycleConflict("current secret version is unknown")
                current = self._record_from_row(current_row)
                self._assert_exact_active(current, owner, expected)
                if self._version_row(
                    tenant,
                    new_ref.provider_id,
                    new_ref.handle_id,
                    new_ref.version_id,
                ) is not None:
                    raise SecretLifecycleConflict("new secret version already exists")
                new_generation = current.identity.generation + 1
                if new_generation > _MAX_NS:
                    raise SecretLifecycleCorruption("secret generation exhausted")
                cursor = self._connection.execute(
                    """
                    UPDATE secret_version_lifecycle
                    SET state = ?, state_changed_at_ns = ?,
                        superseded_by_version_id = ?
                    WHERE namespace = ? AND tenant_id = ? AND provider_id = ?
                      AND handle_id = ? AND version_id = ? AND state = ?
                      AND generation = ? AND owner_id = ?
                    """,
                    (
                        SecretVersionState.ROTATED.value,
                        instant,
                        new_ref.version_id,
                        self.namespace,
                        tenant,
                        current_ref.provider_id,
                        current_ref.handle_id,
                        current_ref.version_id,
                        SecretVersionState.ACTIVE.value,
                        expected,
                        owner,
                    ),
                )
                if cursor.rowcount != 1:
                    raise SecretLifecycleConflict("rotation lost lifecycle race")
                successor = SecretLifecycleRecord(
                    identity=SecretVersionIdentity(
                        tenant_id=tenant,
                        owner_id=owner,
                        handle_id=new_ref.handle_id,
                        provider_id=new_ref.provider_id,
                        version_id=new_ref.version_id,
                        generation=new_generation,
                    ),
                    state=SecretVersionState.ACTIVE,
                    created_at_ns=instant,
                    state_changed_at_ns=instant,
                )
                self._insert_record(successor)
                self._commit()
            except Exception:
                self._rollback()
                raise
        return (
            self.read_version(tenant_id=tenant, secret_ref=current_ref),
            self.read_version(tenant_id=tenant, secret_ref=new_ref),
        )

    def revoke(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        secret_ref: SecretRef,
        expected_generation: int,
        now_ns: int | None = None,
    ) -> SecretLifecycleRecord:
        return self._terminal_transition(
            tenant_id=tenant_id,
            owner_id=owner_id,
            secret_ref=secret_ref,
            expected_generation=expected_generation,
            target=SecretVersionState.REVOKED,
            allowed_from=frozenset({SecretVersionState.ACTIVE}),
            now_ns=now_ns,
        )

    def destroy(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        secret_ref: SecretRef,
        expected_generation: int,
        now_ns: int | None = None,
    ) -> SecretLifecycleRecord:
        return self._terminal_transition(
            tenant_id=tenant_id,
            owner_id=owner_id,
            secret_ref=secret_ref,
            expected_generation=expected_generation,
            target=SecretVersionState.DESTROYED,
            allowed_from=frozenset(
                {SecretVersionState.ROTATED, SecretVersionState.REVOKED}
            ),
            now_ns=now_ns,
        )

    def read_version(
        self,
        *,
        tenant_id: str,
        secret_ref: SecretRef,
    ) -> SecretLifecycleRecord:
        tenant = _text(tenant_id, "tenant_id")
        self._require_ref(secret_ref)
        with self._lock:
            row = self._version_row(
                tenant,
                secret_ref.provider_id,
                secret_ref.handle_id,
                secret_ref.version_id,
            )
        if row is None:
            raise SecretVersionUnavailable("unknown secret version")
        return self._record_from_row(row)

    def assert_usable(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        secret_ref: SecretRef,
    ) -> SecretLifecycleRecord:
        owner = _text(owner_id, "owner_id")
        record = self.read_version(tenant_id=tenant_id, secret_ref=secret_ref)
        if record.identity.owner_id != owner:
            raise SecretVersionUnavailable("secret owner mismatch")
        if not record.usable:
            raise SecretVersionUnavailable(
                f"secret version is {record.state.value}"
            )
        return record

    def taint_from_secrets(
        self,
        *,
        tenant_id: str,
        value_id: str,
        secret_refs: Iterable[SecretRef],
        owner_id: str,
        transformation_id: str,
        now_ns: int | None = None,
    ) -> SecretTaint:
        tenant = _text(tenant_id, "tenant_id")
        value = _text(value_id, "value_id")
        owner = _text(owner_id, "owner_id")
        transform = _text(transformation_id, "transformation_id")
        refs = tuple(secret_refs)
        if not refs:
            raise SecretLifecycleError("secret_refs must be non-empty")
        sources = tuple(
            sorted(
                {
                    self.assert_usable(
                        tenant_id=tenant,
                        owner_id=owner,
                        secret_ref=ref,
                    ).identity
                    for ref in refs
                },
                key=lambda item: (
                    item.provider_id,
                    item.handle_id,
                    item.generation,
                    item.version_id,
                    item.owner_id,
                ),
            )
        )
        return self._store_taint(
            SecretTaint(
                tenant_id=tenant,
                value_id=value,
                sources=sources,
                parent_value_ids=(),
                transformation_id=transform,
                created_at_ns=_now(now_ns),
            )
        )

    def propagate_taint(
        self,
        *,
        tenant_id: str,
        value_id: str,
        parent_value_ids: Iterable[str],
        transformation_id: str,
        now_ns: int | None = None,
    ) -> SecretTaint:
        tenant = _text(tenant_id, "tenant_id")
        value = _text(value_id, "value_id")
        transform = _text(transformation_id, "transformation_id")
        parents = tuple(sorted({_text(item, "parent_value_id") for item in parent_value_ids}))
        if not parents:
            raise SecretLifecycleError("parent_value_ids must be non-empty")
        source_by_digest: dict[str, SecretVersionIdentity] = {}
        for parent_id in parents:
            parent = self.read_taint(tenant_id=tenant, value_id=parent_id)
            for source in parent.sources:
                source_by_digest[source.digest] = source
        sources = tuple(
            sorted(
                source_by_digest.values(),
                key=lambda item: (
                    item.provider_id,
                    item.handle_id,
                    item.generation,
                    item.version_id,
                    item.owner_id,
                ),
            )
        )
        return self._store_taint(
            SecretTaint(
                tenant_id=tenant,
                value_id=value,
                sources=sources,
                parent_value_ids=parents,
                transformation_id=transform,
                created_at_ns=_now(now_ns),
            )
        )

    def read_taint(
        self,
        *,
        tenant_id: str,
        value_id: str,
        require_current_sources: bool = True,
    ) -> SecretTaint:
        tenant = _text(tenant_id, "tenant_id")
        value = _text(value_id, "value_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT sources_json, parent_value_ids_json,
                       transformation_id, created_at_ns
                FROM secret_taint
                WHERE namespace = ? AND tenant_id = ? AND value_id = ?
                """,
                (self.namespace, tenant, value),
            ).fetchone()
        if row is None:
            raise SecretLifecycleError("value has no secret taint record")
        taint = self._taint_from_row(tenant, value, row)
        if require_current_sources:
            for source in taint.sources:
                current = self.read_version(
                    tenant_id=tenant,
                    secret_ref=source.ref,
                )
                if current.identity != source or not current.usable:
                    raise SecretTaintStale(
                        "taint references a non-active secret version"
                    )
        return taint

    def is_tainted(self, *, tenant_id: str, value_id: str) -> bool:
        tenant = _text(tenant_id, "tenant_id")
        value = _text(value_id, "value_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT 1 FROM secret_taint
                WHERE namespace = ? AND tenant_id = ? AND value_id = ?
                """,
                (self.namespace, tenant, value),
            ).fetchone()
        return row is not None

    def evaluate_sink(
        self,
        *,
        tenant_id: str,
        value_id: str,
        sink_id: str,
        secret_aware: bool,
        now_ns: int | None = None,
    ) -> SecretSinkDecision:
        tenant = _text(tenant_id, "tenant_id")
        value = _text(value_id, "value_id")
        sink = _text(sink_id, "sink_id")
        if not isinstance(secret_aware, bool):
            raise SecretLifecycleError("secret_aware must be boolean")
        instant = _now(now_ns)
        if not self.is_tainted(tenant_id=tenant, value_id=value):
            return SecretSinkDecision(
                tenant_id=tenant,
                value_id=value,
                sink_id=sink,
                secret_aware=secret_aware,
                allowed=True,
                reason_code="untainted",
                source_digests=(),
                decided_at_ns=instant,
            )
        try:
            taint = self.read_taint(
                tenant_id=tenant,
                value_id=value,
                require_current_sources=True,
            )
        except SecretTaintStale:
            return SecretSinkDecision(
                tenant_id=tenant,
                value_id=value,
                sink_id=sink,
                secret_aware=secret_aware,
                allowed=False,
                reason_code="stale-secret-lineage",
                source_digests=(),
                decided_at_ns=instant,
            )
        source_digests = tuple(source.digest for source in taint.sources)
        if not secret_aware:
            return SecretSinkDecision(
                tenant_id=tenant,
                value_id=value,
                sink_id=sink,
                secret_aware=False,
                allowed=False,
                reason_code="secret-taint",
                source_digests=source_digests,
                decided_at_ns=instant,
            )
        return SecretSinkDecision(
            tenant_id=tenant,
            value_id=value,
            sink_id=sink,
            secret_aware=True,
            allowed=True,
            reason_code="secret-aware-sink",
            source_digests=source_digests,
            decided_at_ns=instant,
        )

    def assert_untainted(
        self,
        *,
        tenant_id: str,
        value_id: str,
        sink_id: str,
        now_ns: int | None = None,
    ) -> SecretSinkDecision:
        decision = self.evaluate_sink(
            tenant_id=tenant_id,
            value_id=value_id,
            sink_id=sink_id,
            secret_aware=False,
            now_ns=now_ns,
        )
        if not decision.allowed:
            raise SecretTaintViolation(
                f"{decision.sink_id} rejected value: {decision.reason_code}"
            )
        return decision

    def card(self) -> dict[str, Any]:
        with self._lock:
            versions = self._connection.execute(
                """
                SELECT state, COUNT(*) AS n
                FROM secret_version_lifecycle
                WHERE namespace = ?
                GROUP BY state
                """,
                (self.namespace,),
            ).fetchall()
            taints = self._connection.execute(
                "SELECT COUNT(*) AS n FROM secret_taint WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        counts = {state.value: 0 for state in SecretVersionState}
        for row in versions:
            try:
                state = SecretVersionState(row["state"])
            except ValueError as exc:
                raise SecretLifecycleCorruption(
                    "persisted lifecycle state is invalid"
                ) from exc
            counts[state.value] = int(row["n"])
        return {
            "kind": "secret_lifecycle_taint",
            "gap": "G011",
            "law": "exact-version-lifecycle-plus-monotonic-taint",
            "version_states": counts,
            "taint_count": int(taints["n"]),
            "secret_material_present": False,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _terminal_transition(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        secret_ref: SecretRef,
        expected_generation: int,
        target: SecretVersionState,
        allowed_from: frozenset[SecretVersionState],
        now_ns: int | None,
    ) -> SecretLifecycleRecord:
        tenant = _text(tenant_id, "tenant_id")
        owner = _text(owner_id, "owner_id")
        self._require_ref(secret_ref)
        expected = _integer(expected_generation, "expected_generation", minimum=1)
        instant = _now(now_ns)
        with self._lock:
            self._begin()
            try:
                row = self._version_row(
                    tenant,
                    secret_ref.provider_id,
                    secret_ref.handle_id,
                    secret_ref.version_id,
                )
                if row is None:
                    raise SecretLifecycleConflict("secret version is unknown")
                current = self._record_from_row(row)
                if current.identity.owner_id != owner:
                    raise SecretLifecycleConflict("secret owner mismatch")
                if current.identity.generation != expected:
                    raise SecretLifecycleConflict("stale secret generation")
                if current.state is target:
                    self._commit()
                    return current
                if current.state not in allowed_from:
                    raise SecretLifecycleConflict(
                        f"cannot transition {current.state.value} to {target.value}"
                    )
                cursor = self._connection.execute(
                    """
                    UPDATE secret_version_lifecycle
                    SET state = ?, state_changed_at_ns = ?,
                        superseded_by_version_id = NULL
                    WHERE namespace = ? AND tenant_id = ? AND provider_id = ?
                      AND handle_id = ? AND version_id = ? AND state = ?
                      AND generation = ? AND owner_id = ?
                    """,
                    (
                        target.value,
                        instant,
                        self.namespace,
                        tenant,
                        secret_ref.provider_id,
                        secret_ref.handle_id,
                        secret_ref.version_id,
                        current.state.value,
                        expected,
                        owner,
                    ),
                )
                if cursor.rowcount != 1:
                    raise SecretLifecycleConflict("lifecycle transition lost race")
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.read_version(tenant_id=tenant, secret_ref=secret_ref)

    def _assert_exact_active(
        self,
        record: SecretLifecycleRecord,
        owner_id: str,
        expected_generation: int,
    ) -> None:
        if record.identity.owner_id != owner_id:
            raise SecretLifecycleConflict("secret owner mismatch")
        if record.identity.generation != expected_generation:
            raise SecretLifecycleConflict("stale secret generation")
        if record.state is not SecretVersionState.ACTIVE:
            raise SecretLifecycleConflict(
                f"secret version is {record.state.value}"
            )

    def _store_taint(self, taint: SecretTaint) -> SecretTaint:
        sources_json = _canonical_json(
            [source.payload() for source in taint.sources]
        )
        parents_json = _canonical_json(list(taint.parent_value_ids))
        with self._lock:
            self._begin()
            try:
                existing = self._connection.execute(
                    """
                    SELECT sources_json, parent_value_ids_json,
                           transformation_id, created_at_ns
                    FROM secret_taint
                    WHERE namespace = ? AND tenant_id = ? AND value_id = ?
                    """,
                    (self.namespace, taint.tenant_id, taint.value_id),
                ).fetchone()
                if existing is not None:
                    prior = self._taint_from_row(
                        taint.tenant_id, taint.value_id, existing
                    )
                    if prior != taint:
                        raise SecretLifecycleConflict(
                            "tainted value identity cannot be rebound"
                        )
                    self._commit()
                    return prior
                self._connection.execute(
                    """
                    INSERT INTO secret_taint(
                        namespace, tenant_id, value_id, sources_json,
                        parent_value_ids_json, transformation_id, created_at_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        taint.tenant_id,
                        taint.value_id,
                        sources_json,
                        parents_json,
                        taint.transformation_id,
                        taint.created_at_ns,
                    ),
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return taint

    def _taint_from_row(
        self,
        tenant_id: str,
        value_id: str,
        row: sqlite3.Row,
    ) -> SecretTaint:
        try:
            raw_sources = json.loads(row["sources_json"])
            raw_parents = json.loads(row["parent_value_ids_json"])
            if not isinstance(raw_sources, list) or not raw_sources:
                raise SecretLifecycleError("persisted taint sources invalid")
            if not isinstance(raw_parents, list):
                raise SecretLifecycleError("persisted taint parents invalid")
            sources: list[SecretVersionIdentity] = []
            required = {
                "tenant_id",
                "owner_id",
                "handle_id",
                "provider_id",
                "version_id",
                "generation",
            }
            for item in raw_sources:
                if not isinstance(item, dict) or set(item) != required:
                    raise SecretLifecycleError("persisted taint source schema drift")
                sources.append(SecretVersionIdentity(**item))
            taint = SecretTaint(
                tenant_id=tenant_id,
                value_id=value_id,
                sources=tuple(sources),
                parent_value_ids=tuple(raw_parents),
                transformation_id=row["transformation_id"],
                created_at_ns=row["created_at_ns"],
            )
            if raw_sources != [source.payload() for source in taint.sources]:
                raise SecretLifecycleError("persisted taint sources not canonical")
            if raw_parents != list(taint.parent_value_ids):
                raise SecretLifecycleError("persisted taint parents not canonical")
            return taint
        except (
            json.JSONDecodeError,
            TypeError,
            SecretLifecycleError,
        ) as exc:
            raise SecretLifecycleCorruption(
                "persisted secret taint is invalid"
            ) from exc

    def _record_from_row(self, row: sqlite3.Row) -> SecretLifecycleRecord:
        try:
            return SecretLifecycleRecord(
                identity=SecretVersionIdentity(
                    tenant_id=row["tenant_id"],
                    owner_id=row["owner_id"],
                    handle_id=row["handle_id"],
                    provider_id=row["provider_id"],
                    version_id=row["version_id"],
                    generation=row["generation"],
                ),
                state=SecretVersionState(row["state"]),
                created_at_ns=_integer(
                    row["created_at_ns"],
                    "persisted created_at_ns",
                    minimum=1,
                ),
                state_changed_at_ns=_integer(
                    row["state_changed_at_ns"],
                    "persisted state_changed_at_ns",
                    minimum=1,
                ),
                superseded_by_version_id=row["superseded_by_version_id"],
            )
        except (ValueError, SecretLifecycleError) as exc:
            raise SecretLifecycleCorruption(
                "persisted secret lifecycle is invalid"
            ) from exc

    def _version_row(
        self,
        tenant_id: str,
        provider_id: str,
        handle_id: str,
        version_id: str,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT *
            FROM secret_version_lifecycle
            WHERE namespace = ? AND tenant_id = ? AND provider_id = ?
              AND handle_id = ? AND version_id = ?
            """,
            (self.namespace, tenant_id, provider_id, handle_id, version_id),
        ).fetchone()

    def _active_row(
        self,
        tenant_id: str,
        provider_id: str,
        handle_id: str,
    ) -> sqlite3.Row | None:
        rows = self._connection.execute(
            """
            SELECT *
            FROM secret_version_lifecycle
            WHERE namespace = ? AND tenant_id = ? AND provider_id = ?
              AND handle_id = ? AND state = ?
            """,
            (
                self.namespace,
                tenant_id,
                provider_id,
                handle_id,
                SecretVersionState.ACTIVE.value,
            ),
        ).fetchall()
        if len(rows) > 1:
            raise SecretLifecycleCorruption(
                "handle has multiple active secret versions"
            )
        return rows[0] if rows else None

    def _latest_generation(
        self,
        tenant_id: str,
        provider_id: str,
        handle_id: str,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT MAX(generation) AS n
            FROM secret_version_lifecycle
            WHERE namespace = ? AND tenant_id = ? AND provider_id = ?
              AND handle_id = ?
            """,
            (self.namespace, tenant_id, provider_id, handle_id),
        ).fetchone()
        if row["n"] is None:
            return 0
        try:
            return _integer(row["n"], "persisted generation", minimum=1)
        except SecretLifecycleError as exc:
            raise SecretLifecycleCorruption(
                "persisted secret generation is invalid"
            ) from exc

    def _insert_record(self, record: SecretLifecycleRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO secret_version_lifecycle(
                namespace, tenant_id, owner_id, handle_id, provider_id,
                version_id, generation, state, created_at_ns,
                state_changed_at_ns, superseded_by_version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.namespace,
                record.identity.tenant_id,
                record.identity.owner_id,
                record.identity.handle_id,
                record.identity.provider_id,
                record.identity.version_id,
                record.identity.generation,
                record.state.value,
                record.created_at_ns,
                record.state_changed_at_ns,
                record.superseded_by_version_id,
            ),
        )

    @staticmethod
    def _require_ref(value: object) -> SecretRef:
        if not isinstance(value, SecretRef):
            raise TypeError("secret_ref must be SecretRef")
        return value

    def _begin(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._connection.execute("COMMIT")

    def _rollback(self) -> None:
        self._connection.execute("ROLLBACK")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteSecretLifecycle":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "SQLiteSecretLifecycle",
    "SecretLifecycleConflict",
    "SecretLifecycleCorruption",
    "SecretLifecycleError",
    "SecretLifecycleRecord",
    "SecretSinkDecision",
    "SecretTaint",
    "SecretTaintStale",
    "SecretTaintViolation",
    "SecretVersionIdentity",
    "SecretVersionState",
    "SecretVersionUnavailable",
]

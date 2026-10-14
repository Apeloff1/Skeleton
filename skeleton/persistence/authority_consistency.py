"""Authoritative storage consistency contract for hostile gap G009.

This module makes state authority executable rather than inferring it from the
durability or storage technology of a record. It is intentionally narrower
than a distributed consensus protocol: it provides a tenant-scoped,
content-addressed compare-and-commit ledger plus freshness validation for
derived/cache projections.

The contract is fail closed:
* one authoritative resource has one explicit owner at a time;
* mutations require the exact current generation and owner;
* ownership changes use a separate transfer operation;
* every committed value is bound to a canonical SHA-256 content digest;
* derived/cache projections bind the exact authoritative generations they used;
* stale or malformed projection lineage is never returned as current state.

The SQLite implementation is a reference implementation for the canonical
``skeleton/persistence`` plane. The semantics are storage-independent and can
be implemented by other durable repositories without changing the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Iterable


_SCHEMA = "skeleton.authority_consistency.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROJECTION_KINDS = frozenset({"derived", "cache"})


class AuthorityConsistencyError(RuntimeError):
    """Base failure for authoritative-state consistency."""


class AuthorityConflict(AuthorityConsistencyError):
    """A write or transfer did not match current authority."""


class ProjectionStale(AuthorityConsistencyError):
    """A projection no longer binds the current authoritative state."""


class AuthorityCorruption(AuthorityConsistencyError):
    """Persisted authority/projection state is malformed or contradictory."""


def _text(value: object, field: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise AuthorityConsistencyError(f"{field} must be non-empty text")
    if value != value.strip():
        raise AuthorityConsistencyError(f"{field} must be canonical text")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise AuthorityConsistencyError(f"{field} contains control characters")
    if len(value) > max_length:
        raise AuthorityConsistencyError(f"{field} exceeds maximum length")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AuthorityConsistencyError(f"{field} must be canonical lowercase SHA-256")
    return value


def _generation(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AuthorityConsistencyError(f"{field} must be an integer >= {minimum}")
    return value


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise AuthorityConsistencyError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuthorityConsistencyError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise AuthorityCorruption(f"{field} must be persisted as text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthorityCorruption(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorityCorruption(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


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
        raise AuthorityConsistencyError("value is not canonical-JSON encodable") from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityToken:
    namespace: str
    tenant_id: str
    domain_id: str
    resource_id: str
    owner_id: str
    generation: int
    content_digest: str
    updated_at: datetime

    @property
    def digest(self) -> str:
        return _sha256_json(
            {
                "schema": _SCHEMA,
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "domain_id": self.domain_id,
                "resource_id": self.resource_id,
                "owner_id": self.owner_id,
                "generation": self.generation,
                "content_digest": self.content_digest,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "resource_id": self.resource_id,
            "owner_id": self.owner_id,
            "generation": self.generation,
            "content_digest": self.content_digest,
            "updated_at": self.updated_at.isoformat(),
            "token_digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class SourceBinding:
    namespace: str
    tenant_id: str
    domain_id: str
    resource_id: str
    owner_id: str
    generation: int
    content_digest: str
    token_digest: str

    @classmethod
    def from_token(cls, token: AuthorityToken) -> "SourceBinding":
        return cls(
            namespace=token.namespace,
            tenant_id=token.tenant_id,
            domain_id=token.domain_id,
            resource_id=token.resource_id,
            owner_id=token.owner_id,
            generation=token.generation,
            content_digest=token.content_digest,
            token_digest=token.digest,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "resource_id": self.resource_id,
            "owner_id": self.owner_id,
            "generation": self.generation,
            "content_digest": self.content_digest,
            "token_digest": self.token_digest,
        }


@dataclass(frozen=True, slots=True)
class ProjectionRecord:
    namespace: str
    tenant_id: str
    projection_id: str
    kind: str
    payload_digest: str
    sources: tuple[SourceBinding, ...]
    created_at: datetime

    @property
    def digest(self) -> str:
        return _sha256_json(
            {
                "schema": _SCHEMA,
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "projection_id": self.projection_id,
                "kind": self.kind,
                "payload_digest": self.payload_digest,
                "sources": [source.as_dict() for source in self.sources],
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "projection_id": self.projection_id,
            "kind": self.kind,
            "payload_digest": self.payload_digest,
            "sources": [source.as_dict() for source in self.sources],
            "created_at": self.created_at.isoformat(),
            "projection_digest": self.digest,
        }


class SQLiteAuthorityConsistency:
    """Reference authoritative-state ledger with projection freshness fencing."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "authority_consistency",
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

                CREATE TABLE IF NOT EXISTS authoritative_state (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    domain_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, domain_id, resource_id)
                );

                CREATE TABLE IF NOT EXISTS state_projection (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    projection_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, projection_id)
                );
                """
            )

    def open_authority(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        resource_id: str,
        owner_id: str,
        content_digest: str,
        now: datetime | None = None,
    ) -> AuthorityToken:
        return self.compare_and_commit(
            tenant_id=tenant_id,
            domain_id=domain_id,
            resource_id=resource_id,
            expected_generation=0,
            owner_id=owner_id,
            content_digest=content_digest,
            now=now,
        )

    def compare_and_commit(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        resource_id: str,
        expected_generation: int,
        owner_id: str,
        content_digest: str,
        expected_content_digest: str | None = None,
        now: datetime | None = None,
    ) -> AuthorityToken:
        tenant = _text(tenant_id, "tenant_id")
        domain = _text(domain_id, "domain_id")
        resource = _text(resource_id, "resource_id")
        owner = _text(owner_id, "owner_id")
        expected = _generation(expected_generation, "expected_generation")
        content = _digest(content_digest, "content_digest")
        prior_digest = (
            None
            if expected_content_digest is None
            else _digest(expected_content_digest, "expected_content_digest")
        )
        instant = _aware(now or datetime.now(timezone.utc), "now")

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_authority_row(tenant, domain, resource)
                if row is None:
                    if expected != 0:
                        raise AuthorityConflict("unknown authoritative resource")
                    if prior_digest is not None:
                        raise AuthorityConflict(
                            "new authoritative resource cannot assert prior content"
                        )
                    generation = 1
                    self._connection.execute(
                        """
                        INSERT INTO authoritative_state(
                            namespace, tenant_id, domain_id, resource_id,
                            owner_id, generation, content_digest, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.namespace,
                            tenant,
                            domain,
                            resource,
                            owner,
                            generation,
                            content,
                            instant.isoformat(),
                        ),
                    )
                else:
                    current = self._authority_from_row(row)
                    if current.generation != expected:
                        raise AuthorityConflict("stale authoritative generation")
                    if current.owner_id != owner:
                        raise AuthorityConflict(
                            "authority owner changed; explicit transfer required"
                        )
                    if (
                        prior_digest is not None
                        and current.content_digest != prior_digest
                    ):
                        raise AuthorityConflict("authoritative content changed")
                    if instant < current.updated_at:
                        raise AuthorityConflict(
                            "authoritative commit cannot predate current generation"
                        )
                    generation = current.generation + 1
                    cursor = self._connection.execute(
                        """
                        UPDATE authoritative_state
                        SET generation = ?, content_digest = ?, updated_at = ?
                        WHERE namespace = ? AND tenant_id = ? AND domain_id = ?
                          AND resource_id = ? AND generation = ? AND owner_id = ?
                        """,
                        (
                            generation,
                            content,
                            instant.isoformat(),
                            self.namespace,
                            tenant,
                            domain,
                            resource,
                            current.generation,
                            current.owner_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise AuthorityConflict("authoritative compare-and-commit lost race")
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

        return AuthorityToken(
            namespace=self.namespace,
            tenant_id=tenant,
            domain_id=domain,
            resource_id=resource,
            owner_id=owner,
            generation=generation,
            content_digest=content,
            updated_at=instant,
        )

    def transfer_authority(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        resource_id: str,
        expected_generation: int,
        current_owner_id: str,
        new_owner_id: str,
        expected_content_digest: str,
        now: datetime | None = None,
    ) -> AuthorityToken:
        tenant = _text(tenant_id, "tenant_id")
        domain = _text(domain_id, "domain_id")
        resource = _text(resource_id, "resource_id")
        current_owner = _text(current_owner_id, "current_owner_id")
        new_owner = _text(new_owner_id, "new_owner_id")
        if current_owner == new_owner:
            raise AuthorityConsistencyError("authority transfer requires a new owner")
        expected = _generation(expected_generation, "expected_generation", minimum=1)
        content = _digest(expected_content_digest, "expected_content_digest")
        instant = _aware(now or datetime.now(timezone.utc), "now")

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._select_authority_row(tenant, domain, resource)
                if row is None:
                    raise AuthorityConflict("unknown authoritative resource")
                current = self._authority_from_row(row)
                if current.generation != expected:
                    raise AuthorityConflict("stale authoritative generation")
                if current.owner_id != current_owner:
                    raise AuthorityConflict("current authority owner mismatch")
                if current.content_digest != content:
                    raise AuthorityConflict("authoritative content changed")
                if instant < current.updated_at:
                    raise AuthorityConflict(
                        "authority transfer cannot predate current generation"
                    )
                generation = current.generation + 1
                cursor = self._connection.execute(
                    """
                    UPDATE authoritative_state
                    SET owner_id = ?, generation = ?, updated_at = ?
                    WHERE namespace = ? AND tenant_id = ? AND domain_id = ?
                      AND resource_id = ? AND generation = ? AND owner_id = ?
                      AND content_digest = ?
                    """,
                    (
                        new_owner,
                        generation,
                        instant.isoformat(),
                        self.namespace,
                        tenant,
                        domain,
                        resource,
                        current.generation,
                        current.owner_id,
                        current.content_digest,
                    ),
                )
                if cursor.rowcount != 1:
                    raise AuthorityConflict("authority transfer lost race")
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

        return AuthorityToken(
            namespace=self.namespace,
            tenant_id=tenant,
            domain_id=domain,
            resource_id=resource,
            owner_id=new_owner,
            generation=generation,
            content_digest=content,
            updated_at=instant,
        )

    def read_authority(
        self,
        *,
        tenant_id: str,
        domain_id: str,
        resource_id: str,
    ) -> AuthorityToken:
        tenant = _text(tenant_id, "tenant_id")
        domain = _text(domain_id, "domain_id")
        resource = _text(resource_id, "resource_id")
        with self._lock:
            row = self._select_authority_row(tenant, domain, resource)
        if row is None:
            raise AuthorityConsistencyError("unknown authoritative resource")
        return self._authority_from_row(row)

    def register_projection(
        self,
        *,
        tenant_id: str,
        projection_id: str,
        kind: str,
        payload_digest: str,
        sources: Iterable[AuthorityToken | SourceBinding],
        now: datetime | None = None,
    ) -> ProjectionRecord:
        tenant = _text(tenant_id, "tenant_id")
        projection = _text(projection_id, "projection_id")
        projection_kind = _text(kind, "kind", max_length=32)
        if projection_kind not in _PROJECTION_KINDS:
            raise AuthorityConsistencyError(
                "projection kind must be 'derived' or 'cache'"
            )
        payload = _digest(payload_digest, "payload_digest")
        normalized = self._normalize_sources(tenant, sources)
        instant = _aware(now or datetime.now(timezone.utc), "now")
        sources_json = _canonical_json(
            [binding.as_dict() for binding in normalized]
        )

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for binding in normalized:
                    self._assert_binding_current(binding)
                self._connection.execute(
                    """
                    INSERT INTO state_projection(
                        namespace, tenant_id, projection_id, kind,
                        payload_digest, sources_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, tenant_id, projection_id)
                    DO UPDATE SET
                        kind = excluded.kind,
                        payload_digest = excluded.payload_digest,
                        sources_json = excluded.sources_json,
                        created_at = excluded.created_at
                    """,
                    (
                        self.namespace,
                        tenant,
                        projection,
                        projection_kind,
                        payload,
                        sources_json,
                        instant.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

        return ProjectionRecord(
            namespace=self.namespace,
            tenant_id=tenant,
            projection_id=projection,
            kind=projection_kind,
            payload_digest=payload,
            sources=normalized,
            created_at=instant,
        )

    def read_projection(
        self,
        *,
        tenant_id: str,
        projection_id: str,
    ) -> ProjectionRecord:
        tenant = _text(tenant_id, "tenant_id")
        projection = _text(projection_id, "projection_id")
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                row = self._connection.execute(
                    """
                    SELECT kind, payload_digest, sources_json, created_at
                    FROM state_projection
                    WHERE namespace = ? AND tenant_id = ? AND projection_id = ?
                    """,
                    (self.namespace, tenant, projection),
                ).fetchone()
                if row is None:
                    raise AuthorityConsistencyError("unknown projection")
                record = self._projection_from_row(
                    tenant_id=tenant,
                    projection_id=projection,
                    row=row,
                )
                for binding in record.sources:
                    self._assert_binding_current(binding)
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return record

    def card(self) -> dict[str, Any]:
        with self._lock:
            authority = self._connection.execute(
                "SELECT COUNT(*) AS n FROM authoritative_state WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
            projections = self._connection.execute(
                "SELECT COUNT(*) AS n FROM state_projection WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        return {
            "kind": "authority_consistency",
            "gap": "G009",
            "law": "single-owner-generation-content-cas",
            "authority_count": int(authority["n"]),
            "projection_count": int(projections["n"]),
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _select_authority_row(
        self,
        tenant_id: str,
        domain_id: str,
        resource_id: str,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT tenant_id, domain_id, resource_id, owner_id,
                   generation, content_digest, updated_at
            FROM authoritative_state
            WHERE namespace = ? AND tenant_id = ? AND domain_id = ?
              AND resource_id = ?
            """,
            (self.namespace, tenant_id, domain_id, resource_id),
        ).fetchone()

    def _authority_from_row(self, row: sqlite3.Row) -> AuthorityToken:
        try:
            tenant = _text(row["tenant_id"], "tenant_id")
            domain = _text(row["domain_id"], "domain_id")
            resource = _text(row["resource_id"], "resource_id")
            owner = _text(row["owner_id"], "owner_id")
            generation = _generation(row["generation"], "generation", minimum=1)
            content = _digest(row["content_digest"], "content_digest")
        except AuthorityConsistencyError as exc:
            raise AuthorityCorruption("persisted authoritative state is invalid") from exc
        return AuthorityToken(
            namespace=self.namespace,
            tenant_id=tenant,
            domain_id=domain,
            resource_id=resource,
            owner_id=owner,
            generation=generation,
            content_digest=content,
            updated_at=_parse_time(row["updated_at"], "updated_at"),
        )

    def _normalize_sources(
        self,
        tenant_id: str,
        sources: Iterable[AuthorityToken | SourceBinding],
    ) -> tuple[SourceBinding, ...]:
        try:
            raw_sources = list(sources)
        except TypeError as exc:
            raise AuthorityConsistencyError("sources must be iterable") from exc
        if not raw_sources:
            raise AuthorityConsistencyError(
                "derived/cache projection requires authoritative source lineage"
            )

        by_resource: dict[tuple[str, str], SourceBinding] = {}
        for raw in raw_sources:
            if isinstance(raw, AuthorityToken):
                binding = SourceBinding.from_token(raw)
            elif isinstance(raw, SourceBinding):
                binding = raw
            else:
                raise AuthorityConsistencyError(
                    "projection sources must be authority tokens or bindings"
                )
            self._validate_binding(binding)
            if binding.namespace != self.namespace:
                raise AuthorityConsistencyError("source namespace mismatch")
            if binding.tenant_id != tenant_id:
                raise AuthorityConsistencyError("cross-tenant projection source forbidden")
            key = (binding.domain_id, binding.resource_id)
            if key in by_resource:
                raise AuthorityConsistencyError("duplicate authoritative projection source")
            by_resource[key] = binding

        return tuple(by_resource[key] for key in sorted(by_resource))

    def _validate_binding(self, binding: SourceBinding) -> None:
        namespace = _text(binding.namespace, "source.namespace")
        tenant = _text(binding.tenant_id, "source.tenant_id")
        domain = _text(binding.domain_id, "source.domain_id")
        resource = _text(binding.resource_id, "source.resource_id")
        owner = _text(binding.owner_id, "source.owner_id")
        generation = _generation(
            binding.generation, "source.generation", minimum=1
        )
        content = _digest(binding.content_digest, "source.content_digest")
        token_digest = _digest(binding.token_digest, "source.token_digest")
        expected = _sha256_json(
            {
                "schema": _SCHEMA,
                "namespace": namespace,
                "tenant_id": tenant,
                "domain_id": domain,
                "resource_id": resource,
                "owner_id": owner,
                "generation": generation,
                "content_digest": content,
            }
        )
        if token_digest != expected:
            raise AuthorityConsistencyError("source token digest mismatch")

    def _assert_binding_current(self, binding: SourceBinding) -> None:
        row = self._select_authority_row(
            binding.tenant_id,
            binding.domain_id,
            binding.resource_id,
        )
        if row is None:
            raise ProjectionStale("projection source authority is unavailable")
        current = self._authority_from_row(row)
        if (
            current.owner_id != binding.owner_id
            or current.generation != binding.generation
            or current.content_digest != binding.content_digest
            or current.digest != binding.token_digest
        ):
            raise ProjectionStale("projection source is stale")

    def _projection_from_row(
        self,
        *,
        tenant_id: str,
        projection_id: str,
        row: sqlite3.Row,
    ) -> ProjectionRecord:
        try:
            projection_kind = _text(row["kind"], "kind", max_length=32)
            if projection_kind not in _PROJECTION_KINDS:
                raise AuthorityConsistencyError("unknown projection kind")
            payload_digest = _digest(row["payload_digest"], "payload_digest")
            raw_sources = json.loads(row["sources_json"])
            if not isinstance(raw_sources, list):
                raise AuthorityConsistencyError("sources_json must be a list")
            bindings: list[SourceBinding] = []
            for raw in raw_sources:
                if not isinstance(raw, dict) or set(raw) != {
                    "namespace",
                    "tenant_id",
                    "domain_id",
                    "resource_id",
                    "owner_id",
                    "generation",
                    "content_digest",
                    "token_digest",
                }:
                    raise AuthorityConsistencyError("projection source schema drift")
                binding = SourceBinding(**raw)
                self._validate_binding(binding)
                if binding.namespace != self.namespace:
                    raise AuthorityConsistencyError("source namespace mismatch")
                if binding.tenant_id != tenant_id:
                    raise AuthorityConsistencyError(
                        "cross-tenant projection source forbidden"
                    )
                bindings.append(binding)
            normalized = self._normalize_sources(tenant_id, bindings)
            if list(raw_sources) != [item.as_dict() for item in normalized]:
                raise AuthorityConsistencyError(
                    "projection sources are not canonically ordered"
                )
        except (json.JSONDecodeError, TypeError, AuthorityConsistencyError) as exc:
            raise AuthorityCorruption("persisted projection state is invalid") from exc

        return ProjectionRecord(
            namespace=self.namespace,
            tenant_id=tenant_id,
            projection_id=projection_id,
            kind=projection_kind,
            payload_digest=payload_digest,
            sources=normalized,
            created_at=_parse_time(row["created_at"], "created_at"),
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteAuthorityConsistency":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

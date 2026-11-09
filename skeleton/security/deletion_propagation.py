"""Durable privacy-deletion tombstone propagation and resurrection fencing.

The repository already has evidence-only deletion contracts and a lifecycle
coordinator. This module supplies the missing runtime authority that keeps a
deleted subject deleted while replicas, caches, indexes, backups, and rebuilds
converge asynchronously.

The authority stores metadata only. It never stores deleted payloads.

Laws
----
* deletion generations are monotonic per tenant + target;
* every tombstone declares the exact surfaces that must converge;
* acknowledgements are generation-bound and surface-bound;
* stale/future acknowledgements fail closed;
* a surface cannot replace an acknowledgement with different evidence;
* reads/restores/rebuilds carrying a source generation at or before the latest
  tombstone are rejected as resurrection attempts;
* a later legitimate write must explicitly use a generation newer than the
  tombstone and a caller-supplied creation authority reference;
* the latest tombstone survives restart and cannot be garbage-collected by this
  authority;
* completion means every required surface acknowledged the exact generation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable, Mapping


_SCHEMA = "skeleton.privacy_deletion_propagation.v1"
_MAX_I64 = (1 << 63) - 1


class DeletionPropagationError(RuntimeError):
    """Base deletion propagation authority error."""


class DeletionPropagationConflict(DeletionPropagationError):
    """Persisted deletion identity conflicts with the requested transition."""


class DeletionResurrectionDenied(DeletionPropagationError):
    """A stale copy or restore attempted to resurrect deleted data."""


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DeletionPropagationError(
            f"{field} must be normalized non-empty text"
        )
    if len(value) > maximum:
        raise DeletionPropagationError(f"{field} exceeds maximum length")
    return value


def _counter(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _MAX_I64
    ):
        raise DeletionPropagationError(
            f"{field} must be an integer in [{minimum}, {_MAX_I64}]"
        )
    return value


def _sha256(value: object, field: str) -> str:
    raw = _text(value, field, maximum=64)
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise DeletionPropagationError(f"{field} must be lowercase sha256")
    return raw


def _surfaces(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DeletionPropagationError("required_surfaces must be a collection")
    result = tuple(sorted({_text(v, "surface", maximum=128) for v in values}))
    if not result:
        raise DeletionPropagationError("required_surfaces must be non-empty")
    if len(result) > 256:
        raise DeletionPropagationError("too many deletion surfaces")
    return result


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DeletionPropagationError(
            "deletion propagation state must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class PrivacyDeletionTombstone:
    tenant_id: str
    target_ref: str
    request_id: str
    generation: int
    source_digest: str
    required_surfaces: tuple[str, ...]
    issued_at_ns: int
    authority_ref: str
    schema_version: str = _SCHEMA

    def __post_init__(self) -> None:
        for name in ("tenant_id", "target_ref", "request_id", "authority_ref"):
            object.__setattr__(
                self,
                name,
                _text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "generation",
            _counter(self.generation, "generation", minimum=1),
        )
        object.__setattr__(
            self,
            "source_digest",
            _sha256(self.source_digest, "source_digest"),
        )
        object.__setattr__(
            self,
            "required_surfaces",
            _surfaces(self.required_surfaces),
        )
        object.__setattr__(
            self,
            "issued_at_ns",
            _counter(self.issued_at_ns, "issued_at_ns"),
        )
        if self.schema_version != _SCHEMA:
            raise DeletionPropagationError(
                "unsupported tombstone schema version"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "target_ref": self.target_ref,
            "request_id": self.request_id,
            "generation": self.generation,
            "source_digest": self.source_digest,
            "required_surfaces": list(self.required_surfaces),
            "issued_at_ns": self.issued_at_ns,
            "authority_ref": self.authority_ref,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class DeletionSurfaceAck:
    tenant_id: str
    target_ref: str
    generation: int
    surface: str
    evidence_ref: str
    acknowledged_at_ns: int
    tombstone_digest: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "target_ref", "surface", "evidence_ref"):
            object.__setattr__(
                self,
                name,
                _text(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "generation",
            _counter(self.generation, "generation", minimum=1),
        )
        object.__setattr__(
            self,
            "acknowledged_at_ns",
            _counter(self.acknowledged_at_ns, "acknowledged_at_ns"),
        )
        object.__setattr__(
            self,
            "tombstone_digest",
            _sha256(self.tombstone_digest, "tombstone_digest"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "target_ref": self.target_ref,
            "generation": self.generation,
            "surface": self.surface,
            "evidence_ref": self.evidence_ref,
            "acknowledged_at_ns": self.acknowledged_at_ns,
            "tombstone_digest": self.tombstone_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class DeletionPropagationStatus:
    tombstone: PrivacyDeletionTombstone
    acknowledged_surfaces: tuple[str, ...]
    missing_surfaces: tuple[str, ...]
    acknowledgement_digests: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_surfaces

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": _SCHEMA,
                "tombstone_digest": self.tombstone.digest,
                "acknowledged_surfaces": list(self.acknowledged_surfaces),
                "missing_surfaces": list(self.missing_surfaces),
                "acknowledgement_digests": list(
                    self.acknowledgement_digests
                ),
                "complete": self.complete,
            }
        )


@dataclass(frozen=True, slots=True)
class ResurrectionDecision:
    tenant_id: str
    target_ref: str
    source_generation: int
    latest_tombstone_generation: int | None
    permitted: bool
    reason: str
    creation_authority_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "target_ref", _text(self.target_ref, "target_ref"))
        object.__setattr__(
            self,
            "source_generation",
            _counter(self.source_generation, "source_generation"),
        )
        if self.latest_tombstone_generation is not None:
            object.__setattr__(
                self,
                "latest_tombstone_generation",
                _counter(
                    self.latest_tombstone_generation,
                    "latest_tombstone_generation",
                    minimum=1,
                ),
            )
        if not isinstance(self.permitted, bool):
            raise DeletionPropagationError("permitted must be boolean")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if self.creation_authority_ref is not None:
            object.__setattr__(
                self,
                "creation_authority_ref",
                _text(
                    self.creation_authority_ref,
                    "creation_authority_ref",
                ),
            )


class SQLiteDeletionPropagationAuthority:
    """Restart-safe deletion tombstone and anti-resurrection authority."""

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
                CREATE TABLE IF NOT EXISTS privacy_deletion_tombstone (
                    tenant_id TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    source_digest TEXT NOT NULL,
                    required_surfaces_json TEXT NOT NULL,
                    issued_at_ns INTEGER NOT NULL,
                    authority_ref TEXT NOT NULL,
                    tombstone_digest TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, target_ref, generation),
                    UNIQUE(tenant_id, target_ref, request_id)
                );

                CREATE INDEX IF NOT EXISTS idx_privacy_deletion_latest
                ON privacy_deletion_tombstone(
                    tenant_id, target_ref, generation DESC
                );

                CREATE TABLE IF NOT EXISTS privacy_deletion_ack (
                    tenant_id TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    surface TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    acknowledged_at_ns INTEGER NOT NULL,
                    tombstone_digest TEXT NOT NULL,
                    ack_digest TEXT NOT NULL,
                    PRIMARY KEY(
                        tenant_id, target_ref, generation, surface
                    )
                );
                """
            )

    @staticmethod
    def _tombstone_from_row(row: sqlite3.Row) -> PrivacyDeletionTombstone:
        try:
            surfaces = json.loads(row["required_surfaces_json"])
        except json.JSONDecodeError as exc:
            raise DeletionPropagationError(
                "persisted deletion surfaces are invalid"
            ) from exc
        if not isinstance(surfaces, list):
            raise DeletionPropagationError(
                "persisted deletion surfaces must be a list"
            )
        tombstone = PrivacyDeletionTombstone(
            tenant_id=row["tenant_id"],
            target_ref=row["target_ref"],
            request_id=row["request_id"],
            generation=int(row["generation"]),
            source_digest=row["source_digest"],
            required_surfaces=tuple(surfaces),
            issued_at_ns=int(row["issued_at_ns"]),
            authority_ref=row["authority_ref"],
        )
        if tombstone.digest != row["tombstone_digest"]:
            raise DeletionPropagationError(
                "persisted tombstone digest mismatch"
            )
        return tombstone

    @staticmethod
    def _ack_from_row(row: sqlite3.Row) -> DeletionSurfaceAck:
        ack = DeletionSurfaceAck(
            tenant_id=row["tenant_id"],
            target_ref=row["target_ref"],
            generation=int(row["generation"]),
            surface=row["surface"],
            evidence_ref=row["evidence_ref"],
            acknowledged_at_ns=int(row["acknowledged_at_ns"]),
            tombstone_digest=row["tombstone_digest"],
        )
        if ack.digest != row["ack_digest"]:
            raise DeletionPropagationError(
                "persisted acknowledgement digest mismatch"
            )
        return ack

    def _latest_row(
        self,
        tenant_id: str,
        target_ref: str,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM privacy_deletion_tombstone
            WHERE tenant_id = ? AND target_ref = ?
            ORDER BY generation DESC
            LIMIT 1
            """,
            (tenant_id, target_ref),
        ).fetchone()

    def issue(
        self,
        *,
        tenant_id: str,
        target_ref: str,
        request_id: str,
        source_digest: str,
        required_surfaces: Iterable[str],
        issued_at_ns: int,
        authority_ref: str,
        expected_previous_generation: int | None = None,
    ) -> PrivacyDeletionTombstone:
        tenant = _text(tenant_id, "tenant_id")
        target = _text(target_ref, "target_ref")
        request = _text(request_id, "request_id")
        digest = _sha256(source_digest, "source_digest")
        surfaces = _surfaces(required_surfaces)
        issued = _counter(issued_at_ns, "issued_at_ns")
        authority = _text(authority_ref, "authority_ref")
        if expected_previous_generation is not None:
            expected_previous_generation = _counter(
                expected_previous_generation,
                "expected_previous_generation",
            )

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing_request = self._connection.execute(
                    """
                    SELECT * FROM privacy_deletion_tombstone
                    WHERE tenant_id = ? AND target_ref = ? AND request_id = ?
                    """,
                    (tenant, target, request),
                ).fetchone()
                if existing_request is not None:
                    existing = self._tombstone_from_row(existing_request)
                    candidate = PrivacyDeletionTombstone(
                        tenant_id=tenant,
                        target_ref=target,
                        request_id=request,
                        generation=existing.generation,
                        source_digest=digest,
                        required_surfaces=surfaces,
                        issued_at_ns=issued,
                        authority_ref=authority,
                    )
                    if candidate != existing:
                        raise DeletionPropagationConflict(
                            "request_id was replayed with different deletion intent"
                        )
                    self._connection.execute("COMMIT")
                    return existing

                latest_row = self._latest_row(tenant, target)
                latest_generation = (
                    0 if latest_row is None else int(latest_row["generation"])
                )
                if (
                    expected_previous_generation is not None
                    and latest_generation != expected_previous_generation
                ):
                    raise DeletionPropagationConflict(
                        "deletion generation compare-and-swap failed"
                    )
                generation = latest_generation + 1
                tombstone = PrivacyDeletionTombstone(
                    tenant_id=tenant,
                    target_ref=target,
                    request_id=request,
                    generation=generation,
                    source_digest=digest,
                    required_surfaces=surfaces,
                    issued_at_ns=issued,
                    authority_ref=authority,
                )
                self._connection.execute(
                    """
                    INSERT INTO privacy_deletion_tombstone(
                        tenant_id, target_ref, request_id, generation,
                        source_digest, required_surfaces_json, issued_at_ns,
                        authority_ref, tombstone_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tombstone.tenant_id,
                        tombstone.target_ref,
                        tombstone.request_id,
                        tombstone.generation,
                        tombstone.source_digest,
                        json.dumps(
                            list(tombstone.required_surfaces),
                            separators=(",", ":"),
                        ),
                        tombstone.issued_at_ns,
                        tombstone.authority_ref,
                        tombstone.digest,
                    ),
                )
                self._connection.execute("COMMIT")
                return tombstone
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def latest(
        self,
        *,
        tenant_id: str,
        target_ref: str,
    ) -> PrivacyDeletionTombstone | None:
        tenant = _text(tenant_id, "tenant_id")
        target = _text(target_ref, "target_ref")
        with self._lock:
            row = self._latest_row(tenant, target)
            return None if row is None else self._tombstone_from_row(row)

    def acknowledge(
        self,
        *,
        tenant_id: str,
        target_ref: str,
        generation: int,
        surface: str,
        evidence_ref: str,
        acknowledged_at_ns: int,
    ) -> DeletionSurfaceAck:
        tenant = _text(tenant_id, "tenant_id")
        target = _text(target_ref, "target_ref")
        gen = _counter(generation, "generation", minimum=1)
        surface_id = _text(surface, "surface", maximum=128)
        evidence = _text(evidence_ref, "evidence_ref")
        acknowledged = _counter(
            acknowledged_at_ns,
            "acknowledged_at_ns",
        )

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                latest_row = self._latest_row(tenant, target)
                if latest_row is None:
                    raise DeletionPropagationConflict(
                        "cannot acknowledge unknown tombstone"
                    )
                tombstone = self._tombstone_from_row(latest_row)
                if gen != tombstone.generation:
                    raise DeletionPropagationConflict(
                        "acknowledgement generation is stale or future"
                    )
                if surface_id not in tombstone.required_surfaces:
                    raise DeletionPropagationConflict(
                        "surface is outside tombstone propagation scope"
                    )
                if acknowledged < tombstone.issued_at_ns:
                    raise DeletionPropagationConflict(
                        "acknowledgement predates tombstone"
                    )
                ack = DeletionSurfaceAck(
                    tenant_id=tenant,
                    target_ref=target,
                    generation=gen,
                    surface=surface_id,
                    evidence_ref=evidence,
                    acknowledged_at_ns=acknowledged,
                    tombstone_digest=tombstone.digest,
                )
                prior = self._connection.execute(
                    """
                    SELECT * FROM privacy_deletion_ack
                    WHERE tenant_id = ? AND target_ref = ?
                      AND generation = ? AND surface = ?
                    """,
                    (tenant, target, gen, surface_id),
                ).fetchone()
                if prior is not None:
                    existing = self._ack_from_row(prior)
                    if existing != ack:
                        raise DeletionPropagationConflict(
                            "surface acknowledgement already exists with different evidence"
                        )
                    self._connection.execute("COMMIT")
                    return existing
                self._connection.execute(
                    """
                    INSERT INTO privacy_deletion_ack(
                        tenant_id, target_ref, generation, surface,
                        evidence_ref, acknowledged_at_ns,
                        tombstone_digest, ack_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ack.tenant_id,
                        ack.target_ref,
                        ack.generation,
                        ack.surface,
                        ack.evidence_ref,
                        ack.acknowledged_at_ns,
                        ack.tombstone_digest,
                        ack.digest,
                    ),
                )
                self._connection.execute("COMMIT")
                return ack
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def status(
        self,
        *,
        tenant_id: str,
        target_ref: str,
    ) -> DeletionPropagationStatus | None:
        tombstone = self.latest(
            tenant_id=tenant_id,
            target_ref=target_ref,
        )
        if tombstone is None:
            return None
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM privacy_deletion_ack
                WHERE tenant_id = ? AND target_ref = ? AND generation = ?
                ORDER BY surface ASC
                """,
                (
                    tombstone.tenant_id,
                    tombstone.target_ref,
                    tombstone.generation,
                ),
            ).fetchall()
            acks = tuple(self._ack_from_row(row) for row in rows)
        acknowledged = tuple(ack.surface for ack in acks)
        missing = tuple(
            surface
            for surface in tombstone.required_surfaces
            if surface not in set(acknowledged)
        )
        return DeletionPropagationStatus(
            tombstone=tombstone,
            acknowledged_surfaces=acknowledged,
            missing_surfaces=missing,
            acknowledgement_digests=tuple(ack.digest for ack in acks),
        )

    def guard_source_generation(
        self,
        *,
        tenant_id: str,
        target_ref: str,
        source_generation: int,
        creation_authority_ref: str | None = None,
    ) -> ResurrectionDecision:
        """Fail closed when a stale cache/restore/rebuild can resurrect deletion."""

        tenant = _text(tenant_id, "tenant_id")
        target = _text(target_ref, "target_ref")
        source = _counter(source_generation, "source_generation")
        authority = (
            None
            if creation_authority_ref is None
            else _text(
                creation_authority_ref,
                "creation_authority_ref",
            )
        )
        tombstone = self.latest(
            tenant_id=tenant,
            target_ref=target,
        )
        if tombstone is None:
            return ResurrectionDecision(
                tenant_id=tenant,
                target_ref=target,
                source_generation=source,
                latest_tombstone_generation=None,
                permitted=True,
                reason="no_tombstone",
                creation_authority_ref=authority,
            )

        if source <= tombstone.generation:
            raise DeletionResurrectionDenied(
                "source generation is at or before privacy deletion tombstone"
            )
        if authority is None:
            raise DeletionResurrectionDenied(
                "post-deletion generation requires explicit creation authority"
            )
        return ResurrectionDecision(
            tenant_id=tenant,
            target_ref=target,
            source_generation=source,
            latest_tombstone_generation=tombstone.generation,
            permitted=True,
            reason="newer_authorized_generation",
            creation_authority_ref=authority,
        )

    def completion_evidence(
        self,
        *,
        tenant_id: str,
        target_ref: str,
    ) -> Mapping[str, object]:
        status = self.status(
            tenant_id=tenant_id,
            target_ref=target_ref,
        )
        if status is None:
            raise DeletionPropagationError(
                "no tombstone exists for completion evidence"
            )
        return {
            "schema_version": _SCHEMA,
            "tenant_id": status.tombstone.tenant_id,
            "target_ref": status.tombstone.target_ref,
            "generation": status.tombstone.generation,
            "tombstone_digest": status.tombstone.digest,
            "acknowledged_surfaces": list(status.acknowledged_surfaces),
            "missing_surfaces": list(status.missing_surfaces),
            "acknowledgement_digests": list(
                status.acknowledgement_digests
            ),
            "complete": status.complete,
            "status_digest": status.digest,
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "DeletionPropagationConflict",
    "DeletionPropagationError",
    "DeletionPropagationStatus",
    "DeletionResurrectionDenied",
    "DeletionSurfaceAck",
    "PrivacyDeletionTombstone",
    "ResurrectionDecision",
    "SQLiteDeletionPropagationAuthority",
]

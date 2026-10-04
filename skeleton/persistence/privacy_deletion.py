"""Durable privacy deletion and tombstone propagation authority for G016.

The authority traces one privacy subject through primary and derived copies
without retaining raw content.  It solves the failure mode where one subsystem
"deletes" a record while caches, indexes, memories, exports, training
candidates, checkpoints, or provenance copies silently survive.

Core laws:

* deletion creates a permanent subject tombstone;
* new materialization for a tombstoned subject is denied;
* every known copy is content-addressed and lineage-bound;
* copies discovered after deletion reopen propagation;
* destructive targets require deletion receipts;
* provenance targets require non-content tombstones instead of deletion;
* completion requires a post-propagation absence scan for every required target;
* any later discovery invalidates the old completion certificate;
* only hashes, references, target identities, and receipts are retained here.

This is a coordination authority, not a storage-engine-specific eraser.  Each
storage adapter must delete/redact its own bytes and acknowledge the result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Iterable


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INT64_MAX = (1 << 63) - 1

PRIMARY_RECORD = "primary_record"
SEARCH_INDEX = "search_index"
VECTOR_INDEX = "vector_index"
SEMANTIC_MEMORY = "semantic_memory"
EPISODIC_MEMORY = "episodic_memory"
CACHE = "cache"
MATERIALIZED_SUMMARY = "materialized_summary"
EXPORT_ARTIFACT = "export_artifact"
TRAINING_CANDIDATE = "training_candidate"
CHECKPOINT = "checkpoint"
PROVENANCE_REFERENCE = "provenance_reference"

REQUIRED_TARGET_CLASSES = (
    PRIMARY_RECORD,
    SEARCH_INDEX,
    VECTOR_INDEX,
    SEMANTIC_MEMORY,
    EPISODIC_MEMORY,
    CACHE,
    MATERIALIZED_SUMMARY,
    EXPORT_ARTIFACT,
    TRAINING_CANDIDATE,
    CHECKPOINT,
    PROVENANCE_REFERENCE,
)
_REQUIRED_TARGET_SET = frozenset(REQUIRED_TARGET_CLASSES)

PROPAGATING = "propagating"
COMPLETE = "complete"

DELETED = "deleted"
TOMBSTONED = "tombstoned"


class PrivacyDeletionError(RuntimeError):
    """Base privacy-deletion authority failure."""


class DeletionConflict(PrivacyDeletionError):
    """The requested operation conflicts with durable deletion state."""


class DeletionFence(PrivacyDeletionError):
    """A tombstone forbids new privacy-subject materialization."""


class DeletionIncomplete(PrivacyDeletionError):
    """Deletion cannot be finalized because propagation is incomplete."""


class DeletionCorruption(PrivacyDeletionError):
    """Persisted deletion state cannot be trusted."""


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PrivacyDeletionError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise PrivacyDeletionError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PrivacyDeletionError(f"{field} contains control characters")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PrivacyDeletionError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _INT64_MAX,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise PrivacyDeletionError(
            f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _target_class(value: object) -> str:
    target = _text(value, "target_class", maximum=64)
    if target not in _REQUIRED_TARGET_SET:
        raise PrivacyDeletionError(f"unknown deletion target class: {target}")
    return target


def _canonical_digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PrivacyDeletionError("payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SubjectTombstone:
    namespace: str
    tenant_id: str
    subject_id: str
    deletion_id: str
    request_digest: str
    reason_digest: str
    generation: int
    revision: int
    status: str
    requested_order: int
    completed_order: int | None

    @property
    def tombstone_digest(self) -> str:
        return _canonical_digest(
            {
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "subject_id": self.subject_id,
                "deletion_id": self.deletion_id,
                "request_digest": self.request_digest,
                "reason_digest": self.reason_digest,
                "generation": self.generation,
                "requested_order": self.requested_order,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "subject_id": self.subject_id,
            "deletion_id": self.deletion_id,
            "request_digest": self.request_digest,
            "reason_digest": self.reason_digest,
            "generation": self.generation,
            "revision": self.revision,
            "status": self.status,
            "requested_order": self.requested_order,
            "completed_order": self.completed_order,
            "tombstone_digest": self.tombstone_digest,
        }


@dataclass(frozen=True, slots=True)
class MaterializedCopy:
    namespace: str
    tenant_id: str
    subject_id: str
    copy_id: str
    target_class: str
    store_id: str
    resource_ref: str
    content_digest: str
    parent_copy_id: str | None
    discovered_order: int
    resolution: str | None
    resolution_receipt_digest: str | None
    resolution_order: int | None

    @property
    def active(self) -> bool:
        return self.resolution is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "subject_id": self.subject_id,
            "copy_id": self.copy_id,
            "target_class": self.target_class,
            "store_id": self.store_id,
            "resource_ref": self.resource_ref,
            "content_digest": self.content_digest,
            "parent_copy_id": self.parent_copy_id,
            "discovered_order": self.discovered_order,
            "resolution": self.resolution,
            "resolution_receipt_digest": self.resolution_receipt_digest,
            "resolution_order": self.resolution_order,
        }


@dataclass(frozen=True, slots=True)
class TargetScan:
    namespace: str
    tenant_id: str
    subject_id: str
    target_class: str
    subject_revision: int
    inventory_digest: str
    active_copy_ids: tuple[str, ...]
    scanned_order: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "subject_id": self.subject_id,
            "target_class": self.target_class,
            "subject_revision": self.subject_revision,
            "inventory_digest": self.inventory_digest,
            "active_copy_ids": list(self.active_copy_ids),
            "scanned_order": self.scanned_order,
        }


@dataclass(frozen=True, slots=True)
class DeletionCertificate:
    tombstone: SubjectTombstone
    target_scans: tuple[TargetScan, ...]
    certificate_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.privacy_deletion_certificate.v1",
            "tombstone": self.tombstone.as_dict(),
            "target_scans": [scan.as_dict() for scan in self.target_scans],
            "certificate_digest": self.certificate_digest,
        }


class SQLitePrivacyDeletionAuthority:
    """Durable privacy tombstone, lineage, propagation, and scan authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "privacy_deletion",
    ) -> None:
        self.namespace = _text(namespace, "namespace", maximum=128)
        self._connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
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

                CREATE TABLE IF NOT EXISTS privacy_clock (
                    namespace TEXT PRIMARY KEY,
                    order_index INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS privacy_subject (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    deletion_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    reason_digest TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    requested_order INTEGER NOT NULL,
                    completed_order INTEGER,
                    PRIMARY KEY(namespace, tenant_id, subject_id),
                    UNIQUE(namespace, tenant_id, deletion_id)
                );

                CREATE TABLE IF NOT EXISTS privacy_copy (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    copy_id TEXT NOT NULL,
                    target_class TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    resource_ref TEXT NOT NULL,
                    content_digest TEXT NOT NULL,
                    parent_copy_id TEXT,
                    discovered_order INTEGER NOT NULL,
                    resolution TEXT,
                    resolution_receipt_digest TEXT,
                    resolution_order INTEGER,
                    PRIMARY KEY(namespace, tenant_id, subject_id, copy_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_privacy_copy_resource
                ON privacy_copy(
                    namespace, tenant_id, subject_id, store_id, resource_ref
                );

                CREATE TABLE IF NOT EXISTS privacy_scan (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    target_class TEXT NOT NULL,
                    subject_revision INTEGER NOT NULL,
                    inventory_digest TEXT NOT NULL,
                    active_copy_ids_json TEXT NOT NULL,
                    scanned_order INTEGER NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, subject_id, target_class)
                );
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO privacy_clock(namespace, order_index)
                VALUES (?, 0)
                """,
                (self.namespace,),
            )

    def register_copy(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        copy_id: str,
        target_class: str,
        store_id: str,
        resource_ref: str,
        content_digest: str,
        parent_copy_id: str | None = None,
    ) -> MaterializedCopy:
        """Register a normal materialization before deletion.

        Once a subject tombstone exists, new materialization is forbidden.
        Use discover_copy() only to report a copy that already existed or was
        found after deletion.
        """

        tenant, subject, copy = self._copy_identity(
            tenant_id, subject_id, copy_id
        )
        target = _target_class(target_class)
        store = _text(store_id, "store_id")
        resource = _text(resource_ref, "resource_ref", maximum=2048)
        content = _digest(content_digest, "content_digest")
        parent = (
            None
            if parent_copy_id is None
            else _text(parent_copy_id, "parent_copy_id")
        )
        with self._lock:
            self._begin()
            try:
                if self._subject_row(tenant, subject) is not None:
                    raise DeletionFence(
                        "subject is tombstoned; new materialization denied"
                    )
                existing = self._copy_row(tenant, subject, copy)
                if existing is not None:
                    record = self._copy_from_row(existing)
                    self._assert_copy_identity(
                        record,
                        target=target,
                        store=store,
                        resource=resource,
                        content=content,
                        parent=parent,
                    )
                    self._commit()
                    return record
                self._validate_parent(tenant, subject, copy, parent)
                order_index = self._next_order()
                self._insert_copy(
                    tenant=tenant,
                    subject=subject,
                    copy=copy,
                    target=target,
                    store=store,
                    resource=resource,
                    content=content,
                    parent=parent,
                    order_index=order_index,
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.require_copy(
            tenant_id=tenant, subject_id=subject, copy_id=copy
        )

    def request_deletion(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        deletion_id: str,
        request_digest: str,
        reason_digest: str,
    ) -> SubjectTombstone:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        deletion = _text(deletion_id, "deletion_id")
        request = _digest(request_digest, "request_digest")
        reason = _digest(reason_digest, "reason_digest")
        with self._lock:
            self._begin()
            try:
                row = self._subject_row(tenant, subject)
                if row is not None:
                    existing = self._subject_from_row(row)
                    if (
                        existing.deletion_id != deletion
                        or existing.request_digest != request
                        or existing.reason_digest != reason
                    ):
                        raise DeletionConflict(
                            "subject deletion replay changed identity"
                        )
                    self._commit()
                    return existing
                order_index = self._next_order()
                self._connection.execute(
                    """
                    INSERT INTO privacy_subject(
                        namespace, tenant_id, subject_id, deletion_id,
                        request_digest, reason_digest, generation, revision,
                        status, requested_order, completed_order
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?, NULL)
                    """,
                    (
                        self.namespace,
                        tenant,
                        subject,
                        deletion,
                        request,
                        reason,
                        PROPAGATING,
                        order_index,
                    ),
                )
                self._connection.execute(
                    """
                    DELETE FROM privacy_scan
                    WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                    """,
                    (self.namespace, tenant, subject),
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.require_tombstone(tenant_id=tenant, subject_id=subject)

    def assert_materialization_allowed(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> None:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        with self._lock:
            row = self._subject_row(tenant, subject)
        if row is not None:
            raise DeletionFence(
                "privacy tombstone permanently fences subject materialization"
            )

    def discover_copy(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        copy_id: str,
        target_class: str,
        store_id: str,
        resource_ref: str,
        content_digest: str,
        parent_copy_id: str | None = None,
    ) -> MaterializedCopy:
        """Report a copy found during or after deletion.

        Discovery is intentionally allowed after completion.  It increments the
        subject revision, invalidates prior scans/certificates, and reopens
        propagation rather than pretending the old certificate is still current.
        """

        tenant, subject, copy = self._copy_identity(
            tenant_id, subject_id, copy_id
        )
        target = _target_class(target_class)
        store = _text(store_id, "store_id")
        resource = _text(resource_ref, "resource_ref", maximum=2048)
        content = _digest(content_digest, "content_digest")
        parent = (
            None
            if parent_copy_id is None
            else _text(parent_copy_id, "parent_copy_id")
        )
        with self._lock:
            self._begin()
            try:
                tombstone = self._subject_row(tenant, subject)
                if tombstone is None:
                    raise DeletionConflict(
                        "discover_copy requires an active subject tombstone"
                    )
                existing = self._copy_row(tenant, subject, copy)
                if existing is not None:
                    record = self._copy_from_row(existing)
                    self._assert_copy_identity(
                        record,
                        target=target,
                        store=store,
                        resource=resource,
                        content=content,
                        parent=parent,
                    )
                    self._commit()
                    return record
                self._validate_parent(tenant, subject, copy, parent)
                order_index = self._next_order()
                self._insert_copy(
                    tenant=tenant,
                    subject=subject,
                    copy=copy,
                    target=target,
                    store=store,
                    resource=resource,
                    content=content,
                    parent=parent,
                    order_index=order_index,
                )
                self._bump_revision(tenant, subject)
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.require_copy(
            tenant_id=tenant, subject_id=subject, copy_id=copy
        )

    def acknowledge_resolution(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        copy_id: str,
        resolution: str,
        receipt_digest: str,
    ) -> MaterializedCopy:
        tenant, subject, copy = self._copy_identity(
            tenant_id, subject_id, copy_id
        )
        receipt = _digest(receipt_digest, "receipt_digest")
        if resolution not in {DELETED, TOMBSTONED}:
            raise PrivacyDeletionError(
                "resolution must be deleted or tombstoned"
            )
        with self._lock:
            self._begin()
            try:
                if self._subject_row(tenant, subject) is None:
                    raise DeletionConflict("subject is not tombstoned")
                row = self._copy_row(tenant, subject, copy)
                if row is None:
                    raise DeletionConflict("unknown materialized copy")
                current = self._copy_from_row(row)
                expected = (
                    TOMBSTONED
                    if current.target_class == PROVENANCE_REFERENCE
                    else DELETED
                )
                if resolution != expected:
                    raise DeletionConflict(
                        f"{current.target_class} requires {expected} resolution"
                    )
                if current.resolution is not None:
                    if (
                        current.resolution == resolution
                        and current.resolution_receipt_digest == receipt
                    ):
                        self._commit()
                        return current
                    raise DeletionConflict(
                        "copy resolution replay changed evidence"
                    )
                order_index = self._next_order()
                cursor = self._connection.execute(
                    """
                    UPDATE privacy_copy
                    SET resolution = ?, resolution_receipt_digest = ?,
                        resolution_order = ?
                    WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                      AND copy_id = ? AND resolution IS NULL
                    """,
                    (
                        resolution,
                        receipt,
                        order_index,
                        self.namespace,
                        tenant,
                        subject,
                        copy,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DeletionConflict("copy resolution lost race")
                self._bump_revision(tenant, subject)
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.require_copy(
            tenant_id=tenant, subject_id=subject, copy_id=copy
        )

    def record_scan(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        target_class: str,
        inventory_digest: str,
        active_copy_ids: Iterable[str],
    ) -> TargetScan:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        target = _target_class(target_class)
        inventory = _digest(inventory_digest, "inventory_digest")
        ids = tuple(sorted({_text(value, "active_copy_id") for value in active_copy_ids}))
        with self._lock:
            self._begin()
            try:
                row = self._subject_row(tenant, subject)
                if row is None:
                    raise DeletionConflict("subject is not tombstoned")
                tombstone = self._subject_from_row(row)
                actual_rows = self._connection.execute(
                    """
                    SELECT copy_id FROM privacy_copy
                    WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                      AND target_class = ? AND resolution IS NULL
                    ORDER BY copy_id ASC
                    """,
                    (self.namespace, tenant, subject, target),
                ).fetchall()
                actual = tuple(value["copy_id"] for value in actual_rows)
                if ids != actual:
                    raise DeletionConflict(
                        "scan active-copy set does not match deletion inventory"
                    )
                order_index = self._next_order()
                self._connection.execute(
                    """
                    INSERT INTO privacy_scan(
                        namespace, tenant_id, subject_id, target_class,
                        subject_revision, inventory_digest,
                        active_copy_ids_json, scanned_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, tenant_id, subject_id, target_class)
                    DO UPDATE SET
                        subject_revision = excluded.subject_revision,
                        inventory_digest = excluded.inventory_digest,
                        active_copy_ids_json = excluded.active_copy_ids_json,
                        scanned_order = excluded.scanned_order
                    """,
                    (
                        self.namespace,
                        tenant,
                        subject,
                        target,
                        tombstone.revision,
                        inventory,
                        json.dumps(ids, separators=(",", ":")),
                        order_index,
                    ),
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.require_scan(
            tenant_id=tenant,
            subject_id=subject,
            target_class=target,
        )

    def pending_copies(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> tuple[MaterializedCopy, ...]:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM privacy_copy
                WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                  AND resolution IS NULL
                ORDER BY discovered_order ASC, copy_id ASC
                """,
                (self.namespace, tenant, subject),
            ).fetchall()
        return tuple(self._copy_from_row(row) for row in rows)

    def finalize(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> DeletionCertificate:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        with self._lock:
            self._begin()
            try:
                row = self._subject_row(tenant, subject)
                if row is None:
                    raise DeletionConflict("subject is not tombstoned")
                tombstone = self._subject_from_row(row)
                pending = self._connection.execute(
                    """
                    SELECT COUNT(*) AS n FROM privacy_copy
                    WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                      AND resolution IS NULL
                    """,
                    (self.namespace, tenant, subject),
                ).fetchone()
                if int(pending["n"]) != 0:
                    raise DeletionIncomplete(
                        "materialized copies still require propagation"
                    )
                scans = self._current_scans(tenant, subject)
                by_target = {scan.target_class: scan for scan in scans}
                missing = [
                    target
                    for target in REQUIRED_TARGET_CLASSES
                    if target not in by_target
                    or by_target[target].subject_revision != tombstone.revision
                    or by_target[target].active_copy_ids
                ]
                if missing:
                    raise DeletionIncomplete(
                        "fresh zero-active scans required for: "
                        + ", ".join(missing)
                    )
                if tombstone.status != COMPLETE:
                    completed_order = self._next_order()
                    cursor = self._connection.execute(
                        """
                        UPDATE privacy_subject
                        SET status = ?, completed_order = ?
                        WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                          AND revision = ?
                        """,
                        (
                            COMPLETE,
                            completed_order,
                            self.namespace,
                            tenant,
                            subject,
                            tombstone.revision,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise DeletionConflict("finalization lost race")
                self._commit()
            except Exception:
                self._rollback()
                raise
        return self.certificate(tenant_id=tenant, subject_id=subject)

    def certificate(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> DeletionCertificate:
        tombstone = self.require_tombstone(
            tenant_id=tenant_id, subject_id=subject_id
        )
        if tombstone.status != COMPLETE or tombstone.completed_order is None:
            raise DeletionIncomplete("subject does not have a current certificate")
        scans = self._current_scans(tombstone.tenant_id, tombstone.subject_id)
        if (
            len(scans) != len(REQUIRED_TARGET_CLASSES)
            or any(
                scan.subject_revision != tombstone.revision
                or scan.active_copy_ids
                for scan in scans
            )
        ):
            raise DeletionIncomplete("completion certificate is stale")
        payload = {
            "tombstone": tombstone.as_dict(),
            "target_scans": [scan.as_dict() for scan in scans],
        }
        return DeletionCertificate(
            tombstone=tombstone,
            target_scans=scans,
            certificate_digest=_canonical_digest(payload),
        )

    def require_tombstone(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> SubjectTombstone:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        with self._lock:
            row = self._subject_row(tenant, subject)
        if row is None:
            raise DeletionConflict("subject is not tombstoned")
        return self._subject_from_row(row)

    def require_copy(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        copy_id: str,
    ) -> MaterializedCopy:
        tenant, subject, copy = self._copy_identity(
            tenant_id, subject_id, copy_id
        )
        with self._lock:
            row = self._copy_row(tenant, subject, copy)
        if row is None:
            raise DeletionConflict("unknown materialized copy")
        return self._copy_from_row(row)

    def require_scan(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        target_class: str,
    ) -> TargetScan:
        tenant = _text(tenant_id, "tenant_id")
        subject = _text(subject_id, "subject_id")
        target = _target_class(target_class)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM privacy_scan
                WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                  AND target_class = ?
                """,
                (self.namespace, tenant, subject, target),
            ).fetchone()
        if row is None:
            raise DeletionConflict("target class has no deletion scan")
        return self._scan_from_row(row)

    def card(self) -> dict[str, Any]:
        with self._lock:
            subjects = self._connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS complete
                FROM privacy_subject WHERE namespace = ?
                """,
                (COMPLETE, self.namespace),
            ).fetchone()
            pending = self._connection.execute(
                """
                SELECT COUNT(*) AS n FROM privacy_copy
                WHERE namespace = ? AND resolution IS NULL
                """,
                (self.namespace,),
            ).fetchone()
        return {
            "kind": "privacy_deletion_authority",
            "gap": "G016",
            "law": "permanent-tombstone-traced-propagation-post-delete-scan",
            "required_target_classes": list(REQUIRED_TARGET_CLASSES),
            "subject_count": int(subjects["total"] or 0),
            "complete_subject_count": int(subjects["complete"] or 0),
            "pending_copy_count": int(pending["n"] or 0),
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _copy_identity(
        self,
        tenant_id: str,
        subject_id: str,
        copy_id: str,
    ) -> tuple[str, str, str]:
        return (
            _text(tenant_id, "tenant_id"),
            _text(subject_id, "subject_id"),
            _text(copy_id, "copy_id"),
        )

    def _subject_row(
        self, tenant_id: str, subject_id: str
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM privacy_subject
            WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
            """,
            (self.namespace, tenant_id, subject_id),
        ).fetchone()

    def _copy_row(
        self, tenant_id: str, subject_id: str, copy_id: str
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM privacy_copy
            WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
              AND copy_id = ?
            """,
            (self.namespace, tenant_id, subject_id, copy_id),
        ).fetchone()

    def _insert_copy(
        self,
        *,
        tenant: str,
        subject: str,
        copy: str,
        target: str,
        store: str,
        resource: str,
        content: str,
        parent: str | None,
        order_index: int,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO privacy_copy(
                namespace, tenant_id, subject_id, copy_id, target_class,
                store_id, resource_ref, content_digest, parent_copy_id,
                discovered_order, resolution, resolution_receipt_digest,
                resolution_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                self.namespace,
                tenant,
                subject,
                copy,
                target,
                store,
                resource,
                content,
                parent,
                order_index,
            ),
        )

    def _validate_parent(
        self,
        tenant: str,
        subject: str,
        copy: str,
        parent: str | None,
    ) -> None:
        if parent is None:
            return
        if parent == copy:
            raise DeletionConflict("copy cannot derive from itself")
        row = self._copy_row(tenant, subject, parent)
        if row is None:
            raise DeletionConflict(
                "parent copy must exist in the same privacy subject"
            )

    def _assert_copy_identity(
        self,
        record: MaterializedCopy,
        *,
        target: str,
        store: str,
        resource: str,
        content: str,
        parent: str | None,
    ) -> None:
        if (
            record.target_class != target
            or record.store_id != store
            or record.resource_ref != resource
            or record.content_digest != content
            or record.parent_copy_id != parent
        ):
            raise DeletionConflict("copy replay changed materialization identity")

    def _bump_revision(self, tenant: str, subject: str) -> None:
        row = self._subject_row(tenant, subject)
        if row is None:
            raise DeletionConflict("subject is not tombstoned")
        current = self._subject_from_row(row)
        if current.revision >= _INT64_MAX:
            raise DeletionCorruption("subject revision exhausted")
        cursor = self._connection.execute(
            """
            UPDATE privacy_subject
            SET revision = ?, status = ?, completed_order = NULL
            WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
              AND revision = ?
            """,
            (
                current.revision + 1,
                PROPAGATING,
                self.namespace,
                tenant,
                subject,
                current.revision,
            ),
        )
        if cursor.rowcount != 1:
            raise DeletionConflict("subject revision lost race")

    def _current_scans(
        self,
        tenant: str,
        subject: str,
    ) -> tuple[TargetScan, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM privacy_scan
                WHERE namespace = ? AND tenant_id = ? AND subject_id = ?
                ORDER BY target_class ASC
                """,
                (self.namespace, tenant, subject),
            ).fetchall()
        return tuple(self._scan_from_row(row) for row in rows)

    def _subject_from_row(self, row: sqlite3.Row) -> SubjectTombstone:
        try:
            status = _text(row["status"], "persisted status", maximum=32)
            if status not in {PROPAGATING, COMPLETE}:
                raise PrivacyDeletionError("unknown persisted subject status")
            completed_raw = row["completed_order"]
            return SubjectTombstone(
                namespace=self.namespace,
                tenant_id=_text(row["tenant_id"], "persisted tenant_id"),
                subject_id=_text(row["subject_id"], "persisted subject_id"),
                deletion_id=_text(row["deletion_id"], "persisted deletion_id"),
                request_digest=_digest(
                    row["request_digest"], "persisted request_digest"
                ),
                reason_digest=_digest(
                    row["reason_digest"], "persisted reason_digest"
                ),
                generation=_integer(
                    row["generation"], "persisted generation", minimum=1
                ),
                revision=_integer(
                    row["revision"], "persisted revision", minimum=1
                ),
                status=status,
                requested_order=_integer(
                    row["requested_order"],
                    "persisted requested_order",
                    minimum=1,
                ),
                completed_order=(
                    None
                    if completed_raw is None
                    else _integer(
                        completed_raw,
                        "persisted completed_order",
                        minimum=1,
                    )
                ),
            )
        except PrivacyDeletionError as exc:
            raise DeletionCorruption("persisted subject is invalid") from exc

    def _copy_from_row(self, row: sqlite3.Row) -> MaterializedCopy:
        try:
            resolution = row["resolution"]
            if resolution is not None and resolution not in {DELETED, TOMBSTONED}:
                raise PrivacyDeletionError("unknown persisted resolution")
            receipt = row["resolution_receipt_digest"]
            order = row["resolution_order"]
            if resolution is None:
                if receipt is not None or order is not None:
                    raise PrivacyDeletionError(
                        "unresolved copy carries resolution evidence"
                    )
            elif receipt is None or order is None:
                raise PrivacyDeletionError(
                    "resolved copy lacks complete resolution evidence"
                )
            return MaterializedCopy(
                namespace=self.namespace,
                tenant_id=_text(row["tenant_id"], "persisted tenant_id"),
                subject_id=_text(row["subject_id"], "persisted subject_id"),
                copy_id=_text(row["copy_id"], "persisted copy_id"),
                target_class=_target_class(row["target_class"]),
                store_id=_text(row["store_id"], "persisted store_id"),
                resource_ref=_text(
                    row["resource_ref"], "persisted resource_ref", maximum=2048
                ),
                content_digest=_digest(
                    row["content_digest"], "persisted content_digest"
                ),
                parent_copy_id=(
                    None
                    if row["parent_copy_id"] is None
                    else _text(
                        row["parent_copy_id"], "persisted parent_copy_id"
                    )
                ),
                discovered_order=_integer(
                    row["discovered_order"],
                    "persisted discovered_order",
                    minimum=1,
                ),
                resolution=resolution,
                resolution_receipt_digest=(
                    None
                    if receipt is None
                    else _digest(
                        receipt, "persisted resolution_receipt_digest"
                    )
                ),
                resolution_order=(
                    None
                    if order is None
                    else _integer(
                        order, "persisted resolution_order", minimum=1
                    )
                ),
            )
        except PrivacyDeletionError as exc:
            raise DeletionCorruption("persisted copy is invalid") from exc

    def _scan_from_row(self, row: sqlite3.Row) -> TargetScan:
        try:
            ids = json.loads(row["active_copy_ids_json"])
            if (
                not isinstance(ids, list)
                or any(not isinstance(value, str) for value in ids)
                or ids != sorted(set(ids))
            ):
                raise PrivacyDeletionError(
                    "persisted scan copy ids are invalid"
                )
            return TargetScan(
                namespace=self.namespace,
                tenant_id=_text(row["tenant_id"], "persisted tenant_id"),
                subject_id=_text(row["subject_id"], "persisted subject_id"),
                target_class=_target_class(row["target_class"]),
                subject_revision=_integer(
                    row["subject_revision"],
                    "persisted subject_revision",
                    minimum=1,
                ),
                inventory_digest=_digest(
                    row["inventory_digest"], "persisted inventory_digest"
                ),
                active_copy_ids=tuple(ids),
                scanned_order=_integer(
                    row["scanned_order"],
                    "persisted scanned_order",
                    minimum=1,
                ),
            )
        except (PrivacyDeletionError, json.JSONDecodeError) as exc:
            raise DeletionCorruption("persisted scan is invalid") from exc

    def _next_order(self) -> int:
        row = self._connection.execute(
            """
            SELECT order_index FROM privacy_clock WHERE namespace = ?
            """,
            (self.namespace,),
        ).fetchone()
        if row is None:
            raise DeletionCorruption("privacy clock is missing")
        prior = _integer(
            row["order_index"], "persisted order_index", minimum=0
        )
        if prior >= _INT64_MAX:
            raise DeletionCorruption("privacy clock exhausted")
        next_order = prior + 1
        cursor = self._connection.execute(
            """
            UPDATE privacy_clock SET order_index = ?
            WHERE namespace = ? AND order_index = ?
            """,
            (next_order, self.namespace, prior),
        )
        if cursor.rowcount != 1:
            raise DeletionConflict("privacy clock advance lost race")
        return next_order

    def _begin(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._connection.execute("COMMIT")

    def _rollback(self) -> None:
        self._connection.execute("ROLLBACK")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLitePrivacyDeletionAuthority":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "CACHE",
    "CHECKPOINT",
    "COMPLETE",
    "DELETED",
    "DeletionCertificate",
    "DeletionConflict",
    "DeletionCorruption",
    "DeletionFence",
    "DeletionIncomplete",
    "EPISODIC_MEMORY",
    "EXPORT_ARTIFACT",
    "MATERIALIZED_SUMMARY",
    "MaterializedCopy",
    "PRIMARY_RECORD",
    "PROVENANCE_REFERENCE",
    "PROPAGATING",
    "PrivacyDeletionError",
    "REQUIRED_TARGET_CLASSES",
    "SEARCH_INDEX",
    "SEMANTIC_MEMORY",
    "SQLitePrivacyDeletionAuthority",
    "SubjectTombstone",
    "TRAINING_CANDIDATE",
    "TOMBSTONED",
    "TargetScan",
    "VECTOR_INDEX",
]

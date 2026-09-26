"""Governed data lifecycle metadata and deletion propagation receipts.

The registry stores governance metadata only, never user payloads. It gives
memory, retrieval, artifact, and durable-store owners one common contract for:
* tenant-scoped inventory/export;
* retention deadlines;
* deletion planning across declared storage targets;
* acknowledgement of deletion propagation;
* fail-closed state transitions.

It is intentionally storage-agnostic. A store adapter consumes deletion actions
and acknowledges them only after the underlying data has actually been removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterable

from skeleton.vault.data_governance import DataClass, DataGovernanceDenied


class LifecycleError(RuntimeError):
    """Base lifecycle metadata failure."""


class LifecycleConflict(LifecycleError):
    """Requested transition conflicts with existing lifecycle state."""


class LifecycleState(str, Enum):
    ACTIVE = "active"
    DELETE_PENDING = "delete_pending"
    DELETED = "deleted"


def _required_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"{field_name} is required")
    normalized = value.strip()
    if len(normalized) > 512:
        raise LifecycleError(f"{field_name} is too long")
    return normalized


def _normalize_targets(values: Iterable[str]) -> tuple[str, ...]:
    targets = tuple(
        dict.fromkeys(_required_id(value, "deletion target") for value in values)
    )
    if not targets:
        raise LifecycleError("at least one deletion target is required")
    return targets


def _finite_timestamp(value: float, field_name: str) -> float:
    if isinstance(value, bool):
        raise LifecycleError(f"{field_name} must be finite")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise LifecycleError(f"{field_name} must be finite and non-negative")
    return number


@dataclass(frozen=True, slots=True)
class GovernedDataRecord:
    record_id: str
    tenant_id: str
    owner_plane: str
    source_ref: str
    data_class: DataClass | str | int
    purposes: tuple[str, ...]
    deletion_targets: tuple[str, ...]
    created_at: float = field(default_factory=time.time)
    retention_until: float | None = None
    exportable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _required_id(self.record_id, "record_id"),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _required_id(self.tenant_id, "tenant_id"),
        )
        object.__setattr__(
            self,
            "owner_plane",
            _required_id(self.owner_plane, "owner_plane"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _required_id(self.source_ref, "source_ref"),
        )
        object.__setattr__(
            self,
            "data_class",
            DataClass.parse(self.data_class),
        )
        purposes = tuple(
            dict.fromkeys(
                _required_id(value, "purpose").lower()
                for value in self.purposes
            )
        )
        if not purposes:
            raise LifecycleError("at least one purpose is required")
        object.__setattr__(self, "purposes", purposes)
        object.__setattr__(
            self,
            "deletion_targets",
            _normalize_targets(self.deletion_targets),
        )
        created = _finite_timestamp(self.created_at, "created_at")
        object.__setattr__(self, "created_at", created)
        if self.retention_until is not None:
            retention = _finite_timestamp(
                self.retention_until,
                "retention_until",
            )
            if retention < created:
                raise LifecycleError(
                    "retention_until must not precede created_at"
                )
            object.__setattr__(self, "retention_until", retention)

    def inventory_dict(self, *, state: LifecycleState) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "owner_plane": self.owner_plane,
            "source_ref": self.source_ref,
            "data_class": self.data_class.label,
            "purposes": list(self.purposes),
            "deletion_targets": list(self.deletion_targets),
            "created_at": self.created_at,
            "retention_until": self.retention_until,
            "exportable": self.exportable,
            "state": state.value,
        }


@dataclass(frozen=True, slots=True)
class DeletionAction:
    record_id: str
    tenant_id: str
    target: str
    source_ref: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "target": self.target,
            "source_ref": self.source_ref,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DeletionPlan:
    plan_id: str
    tenant_id: str
    reason: str
    actions: tuple[DeletionAction, ...]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "tenant_id": self.tenant_id,
            "reason": self.reason,
            "actions": [action.as_dict() for action in self.actions],
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    receipt_id: str
    plan_id: str
    record_id: str
    target: str
    state: LifecycleState
    completed_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "plan_id": self.plan_id,
            "record_id": self.record_id,
            "target": self.target,
            "state": self.state.value,
            "completed_at": self.completed_at,
        }


@dataclass(slots=True)
class _Entry:
    record: GovernedDataRecord
    state: LifecycleState = LifecycleState.ACTIVE
    active_plan_id: str | None = None
    deletion_reason: str | None = None
    acknowledged_targets: set[str] = field(default_factory=set)


def _digest(prefix: str, *values: object) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\x1f")
    return prefix + digest.hexdigest()[:24]


class DataLifecycleRegistry:
    """Thread-safe governance metadata registry and deletion coordinator.

    Supplying a SQLite path persists lifecycle metadata, deletion plans,
    acknowledgement state and receipts across process restarts. Governed user
    payloads remain in their canonical owner repositories.
    """

    _SNAPSHOT_SCHEMA_VERSION = 1

    def __init__(self, path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, _Entry] = {}
        self._plans: dict[str, DeletionPlan] = {}
        self._receipts: list[DeletionReceipt] = []
        self._connection: sqlite3.Connection | None = None
        if path is not None:
            self._connection = sqlite3.connect(
                str(path),
                check_same_thread=False,
                isolation_level=None,
                timeout=5.0,
            )
            self._connection.row_factory = sqlite3.Row
            with self._lock:
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS data_lifecycle_snapshot (
                        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                        schema_version INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                self._load_snapshot_locked()

    @staticmethod
    def _record_payload(record: GovernedDataRecord) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "tenant_id": record.tenant_id,
            "owner_plane": record.owner_plane,
            "source_ref": record.source_ref,
            "data_class": record.data_class.label,
            "purposes": list(record.purposes),
            "deletion_targets": list(record.deletion_targets),
            "created_at": record.created_at,
            "retention_until": record.retention_until,
            "exportable": record.exportable,
        }

    @staticmethod
    def _record_from_payload(payload: dict[str, Any]) -> GovernedDataRecord:
        return GovernedDataRecord(
            record_id=payload["record_id"],
            tenant_id=payload["tenant_id"],
            owner_plane=payload["owner_plane"],
            source_ref=payload["source_ref"],
            data_class=payload["data_class"],
            purposes=tuple(payload["purposes"]),
            deletion_targets=tuple(payload["deletion_targets"]),
            created_at=float(payload["created_at"]),
            retention_until=(
                None
                if payload.get("retention_until") is None
                else float(payload["retention_until"])
            ),
            exportable=bool(payload["exportable"]),
        )

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "schema_version": self._SNAPSHOT_SCHEMA_VERSION,
            "entries": [
                {
                    "record": self._record_payload(entry.record),
                    "state": entry.state.value,
                    "active_plan_id": entry.active_plan_id,
                    "deletion_reason": entry.deletion_reason,
                    "acknowledged_targets": sorted(entry.acknowledged_targets),
                }
                for _, entry in sorted(self._entries.items())
            ],
            "plans": [
                plan.as_dict()
                for _, plan in sorted(self._plans.items())
            ],
            "receipts": [receipt.as_dict() for receipt in self._receipts],
        }

    def _restore_payload_locked(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != self._SNAPSHOT_SCHEMA_VERSION:
            raise LifecycleError("unsupported lifecycle snapshot schema version")

        entries: dict[str, _Entry] = {}
        for raw in payload.get("entries", []):
            if not isinstance(raw, dict) or not isinstance(raw.get("record"), dict):
                raise LifecycleError("lifecycle snapshot entry is invalid")
            record = self._record_from_payload(raw["record"])
            state = LifecycleState(raw["state"])
            acknowledged_raw = raw.get("acknowledged_targets") or []
            if not isinstance(acknowledged_raw, list):
                raise LifecycleError("lifecycle acknowledged targets are invalid")
            acknowledged = {
                _required_id(value, "acknowledged target")
                for value in acknowledged_raw
            }
            if not acknowledged.issubset(set(record.deletion_targets)):
                raise LifecycleError(
                    "lifecycle snapshot acknowledges undeclared deletion target"
                )
            entry = _Entry(
                record=record,
                state=state,
                active_plan_id=raw.get("active_plan_id"),
                deletion_reason=raw.get("deletion_reason"),
                acknowledged_targets=acknowledged,
            )
            if record.record_id in entries:
                raise LifecycleError("duplicate lifecycle record in snapshot")
            entries[record.record_id] = entry

        plans: dict[str, DeletionPlan] = {}
        for raw in payload.get("plans", []):
            if not isinstance(raw, dict):
                raise LifecycleError("lifecycle snapshot plan is invalid")
            actions = tuple(
                DeletionAction(
                    record_id=item["record_id"],
                    tenant_id=item["tenant_id"],
                    target=item["target"],
                    source_ref=item["source_ref"],
                    reason=item["reason"],
                )
                for item in raw.get("actions", [])
            )
            plan = DeletionPlan(
                plan_id=raw["plan_id"],
                tenant_id=raw["tenant_id"],
                reason=raw["reason"],
                actions=actions,
                created_at=float(raw["created_at"]),
            )
            if plan.plan_id in plans:
                raise LifecycleError("duplicate deletion plan in snapshot")
            plans[plan.plan_id] = plan

        receipts = [
            DeletionReceipt(
                receipt_id=raw["receipt_id"],
                plan_id=raw["plan_id"],
                record_id=raw["record_id"],
                target=raw["target"],
                state=LifecycleState(raw["state"]),
                completed_at=float(raw["completed_at"]),
            )
            for raw in payload.get("receipts", [])
        ]

        for entry in entries.values():
            if entry.active_plan_id is not None and entry.active_plan_id not in plans:
                raise LifecycleError(
                    "lifecycle snapshot references unknown active deletion plan"
                )

        self._entries = entries
        self._plans = plans
        self._receipts = receipts

    def _load_snapshot_locked(self) -> None:
        if self._connection is None:
            return
        row = self._connection.execute(
            """
            SELECT schema_version, payload_json
            FROM data_lifecycle_snapshot
            WHERE singleton = 1
            """
        ).fetchone()
        if row is None:
            return
        if int(row["schema_version"]) != self._SNAPSHOT_SCHEMA_VERSION:
            raise LifecycleError("unsupported lifecycle snapshot schema version")
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError as exc:
            raise LifecycleError("lifecycle snapshot is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise LifecycleError("lifecycle snapshot must be an object")
        self._restore_payload_locked(payload)

    def _persist_locked(self) -> None:
        if self._connection is None:
            return
        payload = json.dumps(
            self._snapshot_locked(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                """
                INSERT INTO data_lifecycle_snapshot(
                    singleton, schema_version, payload_json, updated_at
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (self._SNAPSHOT_SCHEMA_VERSION, payload, time.time()),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _recover_after_persist_failure_locked(self) -> None:
        if self._connection is None:
            return
        self._entries = {}
        self._plans = {}
        self._receipts = []
        self._load_snapshot_locked()

    def _persist_or_recover_locked(self) -> None:
        try:
            self._persist_locked()
        except Exception:
            self._recover_after_persist_failure_locked()
            raise

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def register(self, record: GovernedDataRecord) -> GovernedDataRecord:
        with self._lock:
            if record.record_id in self._entries:
                raise LifecycleConflict(
                    f"record already registered: {record.record_id}"
                )
            self._entries[record.record_id] = _Entry(record=record)
            self._persist_or_recover_locked()
        return record

    def ensure_registered(self, record: GovernedDataRecord) -> GovernedDataRecord:
        """Idempotently register an identical record or fail on identity reuse.

        This is the retry-safe boundary for durable write reconciliation. A
        caller replaying the same governed write receives the original record;
        reusing a record_id with different lifecycle metadata fails closed.
        """

        if not isinstance(record, GovernedDataRecord):
            raise TypeError("record must be a GovernedDataRecord")
        with self._lock:
            existing = self._entries.get(record.record_id)
            if existing is None:
                self._entries[record.record_id] = _Entry(record=record)
                self._persist_or_recover_locked()
                return record
            if existing.record == record:
                return existing.record
            raise LifecycleConflict(
                f"record identity conflicts with existing governance metadata: {record.record_id}"
            )

    def reconcile_registered(
        self,
        record: GovernedDataRecord,
    ) -> GovernedDataRecord:
        """Create or update active lifecycle metadata for one canonical record.

        Record identity, tenant, owner, source, purposes, deletion targets,
        creation time and exportability are immutable. Classification and
        retention deadline may change while the record is active. Pending or
        deleted records cannot be revived by a canonical write.
        """

        if not isinstance(record, GovernedDataRecord):
            raise TypeError("record must be a GovernedDataRecord")
        with self._lock:
            existing = self._entries.get(record.record_id)
            if existing is None:
                self._entries[record.record_id] = _Entry(record=record)
                self._persist_or_recover_locked()
                return record
            if existing.state is not LifecycleState.ACTIVE:
                raise LifecycleConflict(
                    "cannot reconcile lifecycle metadata for non-active record"
                )
            current = existing.record
            immutable_pairs = (
                (current.tenant_id, record.tenant_id, "tenant"),
                (current.owner_plane, record.owner_plane, "owner plane"),
                (current.source_ref, record.source_ref, "source reference"),
                (current.purposes, record.purposes, "purposes"),
                (
                    current.deletion_targets,
                    record.deletion_targets,
                    "deletion targets",
                ),
                (current.created_at, record.created_at, "created_at"),
                (current.exportable, record.exportable, "exportability"),
            )
            for left, right, field in immutable_pairs:
                if left != right:
                    raise LifecycleConflict(
                        "canonical lifecycle identity changed: " + field
                    )
            if current == record:
                return current
            existing.record = record
            self._persist_or_recover_locked()
            return record

    def get(self, record_id: str) -> dict[str, Any]:
        key = _required_id(record_id, "record_id")
        with self._lock:
            try:
                entry = self._entries[key]
            except KeyError as exc:
                raise LifecycleError("unknown lifecycle record") from exc
            return entry.record.inventory_dict(state=entry.state)

    def inventory(
        self,
        tenant_id: str,
        *,
        include_deleted: bool = False,
        export_only: bool = False,
    ) -> tuple[dict[str, Any], ...]:
        tenant = _required_id(tenant_id, "tenant_id")
        with self._lock:
            rows = []
            for entry in self._entries.values():
                record = entry.record
                if record.tenant_id != tenant:
                    continue
                if not include_deleted and entry.state is LifecycleState.DELETED:
                    continue
                if export_only and not record.exportable:
                    continue
                rows.append(record.inventory_dict(state=entry.state))
        rows.sort(key=lambda row: row["record_id"])
        return tuple(rows)

    def export_inventory(self, tenant_id: str) -> dict[str, Any]:
        """Return payload-free tenant export metadata."""

        rows = self.inventory(tenant_id, export_only=True)
        return {
            "tenant_id": _required_id(tenant_id, "tenant_id"),
            "records": list(rows),
            "count": len(rows),
        }

    def _plan(
        self,
        entries: list[_Entry],
        *,
        tenant_id: str,
        reason: str,
        now: float,
        persist: bool = False,
    ) -> DeletionPlan:
        actions: list[DeletionAction] = []
        ids = sorted(entry.record.record_id for entry in entries)
        plan_id = _digest(
            "del-",
            tenant_id,
            reason,
            ",".join(ids),
            f"{now:.6f}",
        )

        for entry in entries:
            if entry.state is LifecycleState.DELETED:
                continue
            if (
                entry.state is LifecycleState.DELETE_PENDING
                and entry.active_plan_id != plan_id
            ):
                raise LifecycleConflict(
                    f"record already pending deletion: {entry.record.record_id}"
                )
            entry.state = LifecycleState.DELETE_PENDING
            entry.active_plan_id = plan_id
            entry.deletion_reason = reason
            for target in entry.record.deletion_targets:
                if target in entry.acknowledged_targets:
                    continue
                actions.append(
                    DeletionAction(
                        record_id=entry.record.record_id,
                        tenant_id=tenant_id,
                        target=target,
                        source_ref=entry.record.source_ref,
                        reason=reason,
                    )
                )

        plan = DeletionPlan(
            plan_id=plan_id,
            tenant_id=tenant_id,
            reason=reason,
            actions=tuple(
                sorted(
                    actions,
                    key=lambda action: (action.record_id, action.target),
                )
            ),
            created_at=now,
        )
        self._plans[plan.plan_id] = plan
        if persist:
            self._persist_or_recover_locked()
        return plan

    def request_deletion(
        self,
        tenant_id: str,
        *,
        record_ids: Iterable[str] | None = None,
        reason: str = "tenant-request",
        now: float | None = None,
    ) -> DeletionPlan:
        tenant = _required_id(tenant_id, "tenant_id")
        normalized_reason = _required_id(reason, "reason")
        timestamp = time.time() if now is None else _finite_timestamp(now, "now")

        selected_ids = (
            None
            if record_ids is None
            else tuple(dict.fromkeys(_required_id(v, "record_id") for v in record_ids))
        )

        with self._lock:
            if selected_ids is None:
                entries = [
                    entry
                    for entry in self._entries.values()
                    if entry.record.tenant_id == tenant
                    and entry.state is not LifecycleState.DELETED
                ]
            else:
                entries = []
                for record_id in selected_ids:
                    try:
                        entry = self._entries[record_id]
                    except KeyError as exc:
                        raise LifecycleError(
                            f"unknown lifecycle record: {record_id}"
                        ) from exc
                    if entry.record.tenant_id != tenant:
                        raise DataGovernanceDenied(
                            "cross-tenant deletion request denied"
                        )
                    if entry.state is not LifecycleState.DELETED:
                        entries.append(entry)

            active_plan_ids = {
                entry.active_plan_id
                for entry in entries
                if entry.state is LifecycleState.DELETE_PENDING
                and entry.active_plan_id is not None
            }
            if active_plan_ids:
                if len(active_plan_ids) != 1:
                    raise LifecycleConflict(
                        "selected records belong to multiple active deletion plans"
                    )
                active_plan_id = next(iter(active_plan_ids))
                if any(
                    entry.state is LifecycleState.ACTIVE
                    for entry in entries
                ):
                    raise LifecycleConflict(
                        "cannot merge active records into an existing deletion plan"
                    )
                existing = self._plans[active_plan_id]
                outstanding = []
                by_record = {
                    entry.record.record_id: entry
                    for entry in entries
                }
                for action in existing.actions:
                    entry = by_record.get(action.record_id)
                    if entry is None:
                        continue
                    if action.target in entry.acknowledged_targets:
                        continue
                    outstanding.append(action)
                return DeletionPlan(
                    plan_id=existing.plan_id,
                    tenant_id=existing.tenant_id,
                    reason=existing.reason,
                    actions=tuple(outstanding),
                    created_at=existing.created_at,
                )

            return self._plan(
                entries,
                tenant_id=tenant,
                reason=normalized_reason,
                now=timestamp,
                persist=True,
            )

    def pending_deletion_plan(
        self,
        plan_id: str,
        *,
        tenant_id: str | None = None,
    ) -> DeletionPlan:
        """Return only unacknowledged actions for a durable deletion plan.

        This is the retry/reconciliation read boundary for distributed physical
        owners. It never creates, merges, or mutates a plan.
        """

        plan_key = _required_id(plan_id, "plan_id")
        tenant = (
            None
            if tenant_id is None
            else _required_id(tenant_id, "tenant_id")
        )
        with self._lock:
            try:
                plan = self._plans[plan_key]
            except KeyError as exc:
                raise LifecycleError("unknown deletion plan") from exc
            if tenant is not None and plan.tenant_id != tenant:
                raise DataGovernanceDenied(
                    "cross-tenant deletion plan access denied"
                )

            outstanding: list[DeletionAction] = []
            for action in plan.actions:
                try:
                    entry = self._entries[action.record_id]
                except KeyError as exc:
                    raise LifecycleError(
                        "deletion plan references unknown lifecycle record"
                    ) from exc
                if entry.record.tenant_id != plan.tenant_id:
                    raise LifecycleError(
                        "deletion plan lifecycle tenant mismatch"
                    )
                if entry.active_plan_id != plan.plan_id:
                    if entry.state is LifecycleState.DELETED:
                        continue
                    raise LifecycleConflict(
                        "deletion plan is not active for lifecycle record"
                    )
                if action.target in entry.acknowledged_targets:
                    continue
                outstanding.append(action)

            return DeletionPlan(
                plan_id=plan.plan_id,
                tenant_id=plan.tenant_id,
                reason=plan.reason,
                actions=tuple(outstanding),
                created_at=plan.created_at,
            )

    def plan_retention_expiry_for_tenant(
        self,
        tenant_id: str,
        *,
        now: float | None = None,
    ) -> DeletionPlan | None:
        """Create one durable retention plan for an authorized tenant only."""

        tenant = _required_id(tenant_id, "tenant_id")
        timestamp = (
            time.time()
            if now is None
            else _finite_timestamp(now, "now")
        )
        with self._lock:
            entries = [
                entry
                for entry in self._entries.values()
                if entry.record.tenant_id == tenant
                and entry.state is LifecycleState.ACTIVE
                and entry.record.retention_until is not None
                and entry.record.retention_until <= timestamp
            ]
            if not entries:
                return None
            plan = self._plan(
                entries,
                tenant_id=tenant,
                reason="retention-expired",
                now=timestamp,
                persist=True,
            )
            return plan

    def plan_retention_expiry(
        self,
        *,
        now: float | None = None,
    ) -> tuple[DeletionPlan, ...]:
        timestamp = time.time() if now is None else _finite_timestamp(now, "now")
        with self._lock:
            by_tenant: dict[str, list[_Entry]] = {}
            for entry in self._entries.values():
                record = entry.record
                if entry.state is not LifecycleState.ACTIVE:
                    continue
                if record.retention_until is None or record.retention_until > timestamp:
                    continue
                by_tenant.setdefault(record.tenant_id, []).append(entry)

            plans = [
                self._plan(
                    entries,
                    tenant_id=tenant,
                    reason="retention-expired",
                    now=timestamp,
                )
                for tenant, entries in sorted(by_tenant.items())
            ]
            if plans:
                self._persist_or_recover_locked()
        return tuple(plans)

    def acknowledge_deletion(
        self,
        plan_id: str,
        record_id: str,
        target: str,
        *,
        now: float | None = None,
    ) -> DeletionReceipt:
        plan_key = _required_id(plan_id, "plan_id")
        record_key = _required_id(record_id, "record_id")
        target_key = _required_id(target, "target")
        timestamp = time.time() if now is None else _finite_timestamp(now, "now")

        with self._lock:
            try:
                plan = self._plans[plan_key]
            except KeyError as exc:
                raise LifecycleError("unknown deletion plan") from exc
            try:
                entry = self._entries[record_key]
            except KeyError as exc:
                raise LifecycleError("unknown lifecycle record") from exc

            if entry.active_plan_id != plan.plan_id:
                raise LifecycleConflict(
                    "deletion acknowledgement does not match active plan"
                )
            if target_key not in entry.record.deletion_targets:
                raise LifecycleError(
                    "deletion acknowledgement target is not declared"
                )
            if target_key in entry.acknowledged_targets:
                raise LifecycleConflict(
                    "deletion target already acknowledged"
                )

            entry.acknowledged_targets.add(target_key)
            if entry.acknowledged_targets == set(entry.record.deletion_targets):
                entry.state = LifecycleState.DELETED

            receipt = DeletionReceipt(
                receipt_id=_digest(
                    "delr-",
                    plan.plan_id,
                    record_key,
                    target_key,
                    f"{timestamp:.6f}",
                ),
                plan_id=plan.plan_id,
                record_id=record_key,
                target=target_key,
                state=entry.state,
                completed_at=timestamp,
            )
            self._receipts.append(receipt)
            self._persist_or_recover_locked()
            return receipt

    def receipts(
        self,
        *,
        tenant_id: str | None = None,
    ) -> tuple[DeletionReceipt, ...]:
        with self._lock:
            if tenant_id is None:
                return tuple(self._receipts)
            tenant = _required_id(tenant_id, "tenant_id")
            record_ids = {
                record_id
                for record_id, entry in self._entries.items()
                if entry.record.tenant_id == tenant
            }
            return tuple(
                receipt
                for receipt in self._receipts
                if receipt.record_id in record_ids
            )


__all__ = [
    "DataLifecycleRegistry",
    "DeletionAction",
    "DeletionPlan",
    "DeletionReceipt",
    "GovernedDataRecord",
    "LifecycleConflict",
    "LifecycleError",
    "LifecycleState",
]

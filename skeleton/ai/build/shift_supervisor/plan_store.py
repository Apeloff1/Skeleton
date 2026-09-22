from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .models import PlanItem, PlanRevision, WorkerState
from .policy import may_admit_worker


class InMemoryPlanStore:
    """Thread-safe reference store with bounded import/export support.

    The runtime remains dependency-free, while scheduled jobs can persist this
    state through an external durable medium (for example a GitHub issue body)
    and restore it on the next run.
    """

    STATE_VERSION = 1

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, PlanItem] = {}
        self._workers: dict[str, WorkerState] = {}
        self._revisions: list[PlanRevision] = []

    def snapshot_items(self) -> list[PlanItem]:
        with self._lock:
            return [replace(item) for item in self._items.values()]

    def snapshot_workers(self) -> list[WorkerState]:
        with self._lock:
            return [replace(worker) for worker in self._workers.values()]

    def snapshot_revisions(self) -> list[PlanRevision]:
        with self._lock:
            return [replace(revision) for revision in self._revisions]

    def upsert_worker(self, worker: WorkerState) -> None:
        with self._lock:
            self._workers[worker.worker_id] = replace(worker)

    def add_items(self, items: Iterable[PlanItem]) -> list[str]:
        added: list[str] = []
        with self._lock:
            existing_fingerprints = {
                self._fingerprint(item.title, item.description, item.target_team)
                for item in self._items.values()
                if item.status not in {"done", "rejected"}
            }
            for item in items:
                fp = self._fingerprint(item.title, item.description, item.target_team)
                if item.id in self._items or fp in existing_fingerprints:
                    continue
                self._items[item.id] = replace(item)
                existing_fingerprints.add(fp)
                added.append(item.id)
        return added

    def update_item(self, item: PlanItem) -> None:
        with self._lock:
            if item.id not in self._items:
                raise KeyError(item.id)
            item.updated_at = datetime.now(timezone.utc)
            self._items[item.id] = replace(item)

    def claim_next_for_worker(
        self,
        worker_id: str,
        *,
        overtime_soft_limit_minutes: int = 120,
    ) -> PlanItem | None:
        """Atomically claim the highest-priority eligible legacy plan item.

        Explicitly squad-stamped work is reserved for the four-agent squad
        runtime even when the stamp is malformed or unsupported. This keeps the
        lowest-level claim primitive aligned with :class:`PlanQueueAPI` so a
        direct store caller cannot bypass canonical squad ownership.
        """
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                raise KeyError(worker_id)
            if not may_admit_worker(
                worker=worker,
                overtime_soft_limit_minutes=overtime_soft_limit_minutes,
            ).allowed:
                return None
            now = datetime.now(timezone.utc)
            if self._worker_reserved_by_active_squad(worker_id, now=now):
                return None

            active_owned = any(
                item.owner == worker_id and item.status in {"assigned", "working", "blocked"}
                for item in self._items.values()
            )
            if active_owned:
                return None

            eligible = [
                item
                for item in self._items.values()
                if item.target_team == worker.team
                and item.status == "queued"
                and item.owner is None
                and "squad_size" not in item.metadata
                and self._dependencies_satisfied(item)
            ]
            if not eligible:
                return None

            eligible.sort(key=lambda item: (-item.priority, item.created_at, item.id))
            item = eligible[0]
            item.owner = worker_id
            item.status = "assigned"
            item.updated_at = now
            self._items[item.id] = replace(item)

            worker.current_task_id = item.id
            worker.status = "working"
            worker.last_heartbeat_at = now
            self._workers[worker_id] = replace(worker)
            return replace(item)

    def finish_claim(
        self,
        worker_id: str,
        item_id: str,
        *,
        outcome: str = "done",
    ) -> PlanItem:
        """Finish or release a worker-owned item and clear worker capacity."""
        if outcome not in {"done", "rejected", "queued"}:
            raise ValueError("outcome must be done, rejected, or queued")
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                raise KeyError(worker_id)
            item = self._items.get(item_id)
            if item is None:
                raise KeyError(item_id)
            if item.owner != worker_id:
                raise PermissionError(f"{worker_id!r} does not own {item_id!r}")

            now = datetime.now(timezone.utc)
            item.status = outcome  # type: ignore[assignment]
            item.updated_at = now
            if outcome == "queued":
                item.owner = None
            self._items[item.id] = replace(item)

            if worker.current_task_id == item_id:
                worker.current_task_id = None
                if worker.status != "offline":
                    worker.status = "idle"
                worker.last_heartbeat_at = now
                self._workers[worker_id] = replace(worker)
            return replace(item)

    def append_revision(self, revision: PlanRevision) -> None:
        with self._lock:
            self._revisions.append(replace(revision))
            if len(self._revisions) > 256:
                self._revisions = self._revisions[-256:]

    def export_state(
        self,
        *,
        max_items: int = 32,
        max_workers: int = 96,
        max_revisions: int = 24,
    ) -> dict[str, Any]:
        """Return bounded JSON-safe state for cross-run persistence."""
        with self._lock:
            items = sorted(
                self._items.values(),
                key=lambda item: (
                    item.status in {"done", "rejected"},
                    -item.priority,
                    -item.updated_at.timestamp(),
                    item.id,
                ),
            )[: max(0, max_items)]
            workers = sorted(
                (
                    worker
                    for worker in self._workers.values()
                    if worker.status != "offline"
                    or worker.current_task_id
                    or worker.normal_shift_minutes > 0
                    or worker.overtime_minutes > 0
                    or self._nonnegative_int(worker.metadata.get("daily_work_minutes")) > 0
                ),
                key=lambda worker: (
                    worker.status == "offline",
                    -worker.overtime_minutes,
                    -worker.normal_shift_minutes,
                    worker.worker_id,
                ),
            )[: max(0, max_workers)]
            revisions = self._revisions[-max(0, max_revisions) :] if max_revisions else []
            return {
                "version": self.STATE_VERSION,
                "plan_items": [self._item_payload(item) for item in items],
                "workers": [self._worker_payload(worker) for worker in workers],
                "revisions": [self._revision_payload(revision) for revision in revisions],
            }

    def restore_state(self, state: Mapping[str, Any]) -> None:
        """Replace local state from a previously exported payload.

        Invalid individual rows are ignored, but an unsupported outer version
        fails closed so a future incompatible state shape is never misread.
        """
        version = state.get("version", self.STATE_VERSION)
        if version != self.STATE_VERSION:
            raise ValueError(f"unsupported shift-supervisor state version: {version!r}")

        raw_items = state.get("plan_items", state.get("items", []))
        raw_workers = state.get("workers", [])
        raw_revisions = state.get("revisions", [])
        items: dict[str, PlanItem] = {}
        workers: dict[str, WorkerState] = {}
        revisions: list[PlanRevision] = []

        if isinstance(raw_items, list):
            for row in raw_items[:256]:
                item = self._parse_item(row)
                if item is not None:
                    items[item.id] = item
        if isinstance(raw_workers, list):
            for row in raw_workers[:512]:
                worker = self._parse_worker(row)
                if worker is not None:
                    workers[worker.worker_id] = worker
        if isinstance(raw_revisions, list):
            for row in raw_revisions[-256:]:
                revision = self._parse_revision(row)
                if revision is not None:
                    revisions.append(revision)

        with self._lock:
            self._items = items
            self._workers = workers
            self._revisions = revisions

    def _dependencies_satisfied(self, item: PlanItem) -> bool:
        for dependency_id in item.dependencies:
            dependency = self._items.get(dependency_id)
            if dependency is None or dependency.status != "done":
                return False
        return True

    def _worker_reserved_by_active_squad(self, worker_id: str, *, now: datetime) -> bool:
        worker = self._workers.get(worker_id)
        current_squad = (
            str(worker.metadata.get("current_squad_id", "")) if worker is not None else ""
        )
        for item in self._items.values():
            if item.status not in {"assigned", "working", "blocked"}:
                continue
            owner = str(item.owner or "")
            if not owner.startswith("squad-"):
                continue
            raw = item.metadata.get("squad_lease")
            if isinstance(raw, Mapping):
                expires_at = self._decode_dt(raw.get("expires_at"))
                if expires_at is not None and expires_at <= now:
                    continue
                members = raw.get("members")
                if isinstance(members, Mapping) and worker_id in {
                    str(value) for value in members.values()
                }:
                    return True
            if current_squad == owner:
                return True
        return False

    @classmethod
    def _item_payload(cls, item: PlanItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
            "target_team": item.target_team,
            "status": item.status,
            "owner": item.owner,
            "dependencies": list(item.dependencies),
            "source": item.source,
            "rationale": item.rationale,
            "research_refs": list(item.research_refs),
            "expected_output": item.expected_output,
            "validation": list(item.validation),
            "created_at": cls._encode_dt(item.created_at),
            "updated_at": cls._encode_dt(item.updated_at),
            "metadata": dict(item.metadata),
        }

    @classmethod
    def _worker_payload(cls, worker: WorkerState) -> dict[str, Any]:
        return {
            "worker_id": worker.worker_id,
            "team": worker.team,
            "status": worker.status,
            "clocked_in_at": cls._encode_dt(worker.clocked_in_at),
            "clocked_out_at": cls._encode_dt(worker.clocked_out_at),
            "last_heartbeat_at": cls._encode_dt(worker.last_heartbeat_at),
            "current_task_id": worker.current_task_id,
            "normal_shift_minutes": worker.normal_shift_minutes,
            "overtime_minutes": worker.overtime_minutes,
            "overtime_task_ids": list(worker.overtime_task_ids),
            "metadata": dict(worker.metadata),
        }

    @classmethod
    def _revision_payload(cls, revision: PlanRevision) -> dict[str, Any]:
        return {
            "revision_id": revision.revision_id,
            "actor": revision.actor,
            "created_at": cls._encode_dt(revision.created_at),
            "added_item_ids": list(revision.added_item_ids),
            "updated_item_ids": list(revision.updated_item_ids),
            "summary": revision.summary,
            "correlation_id": revision.correlation_id,
        }

    @classmethod
    def _parse_item(cls, value: Any) -> PlanItem | None:
        if not isinstance(value, Mapping):
            return None
        item_id = str(value.get("id", "")).strip()
        title = str(value.get("title", "")).strip()
        description = str(value.get("description", "")).strip()
        team = str(value.get("target_team", "")).strip().lower()
        status = str(value.get("status", "queued")).strip().lower()
        if not item_id or not title or not description or team not in {"night", "idle"}:
            return None
        if status not in {"queued", "assigned", "working", "blocked", "done", "rejected"}:
            status = "queued"
        try:
            priority = max(1, min(100, int(value.get("priority", 50))))
        except (TypeError, ValueError):
            priority = 50
        return PlanItem(
            id=item_id,
            title=title,
            description=description,
            priority=priority,
            target_team=team,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            owner=cls._optional_str(value.get("owner")),
            dependencies=cls._string_list(value.get("dependencies")),
            source=str(value.get("source", "unknown")),
            rationale=str(value.get("rationale", "")),
            research_refs=cls._string_list(value.get("research_refs")),
            expected_output=str(value.get("expected_output", "")),
            validation=cls._string_list(value.get("validation")),
            created_at=cls._decode_dt(value.get("created_at")) or datetime.now(timezone.utc),
            updated_at=cls._decode_dt(value.get("updated_at")) or datetime.now(timezone.utc),
            metadata=dict(value.get("metadata", {})) if isinstance(value.get("metadata"), Mapping) else {},
        )

    @classmethod
    def _parse_worker(cls, value: Any) -> WorkerState | None:
        if not isinstance(value, Mapping):
            return None
        worker_id = str(value.get("worker_id", "")).strip()
        team = str(value.get("team", "")).strip().lower()
        status = str(value.get("status", "offline")).strip().lower()
        if not worker_id or team not in {"night", "idle"}:
            return None
        if status not in {"offline", "idle", "working", "blocked"}:
            status = "offline"
        return WorkerState(
            worker_id=worker_id,
            team=team,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            clocked_in_at=cls._decode_dt(value.get("clocked_in_at")),
            clocked_out_at=cls._decode_dt(value.get("clocked_out_at")),
            last_heartbeat_at=cls._decode_dt(value.get("last_heartbeat_at")),
            current_task_id=cls._optional_str(value.get("current_task_id")),
            normal_shift_minutes=cls._nonnegative_int(value.get("normal_shift_minutes")),
            overtime_minutes=cls._nonnegative_int(value.get("overtime_minutes")),
            overtime_task_ids=cls._string_list(value.get("overtime_task_ids")),
            metadata=dict(value.get("metadata", {})) if isinstance(value.get("metadata"), Mapping) else {},
        )

    @classmethod
    def _parse_revision(cls, value: Any) -> PlanRevision | None:
        if not isinstance(value, Mapping):
            return None
        revision_id = str(value.get("revision_id", "")).strip()
        actor = str(value.get("actor", "")).strip()
        created_at = cls._decode_dt(value.get("created_at"))
        if not revision_id or not actor or created_at is None:
            return None
        return PlanRevision(
            revision_id=revision_id,
            actor=actor,
            created_at=created_at,
            added_item_ids=cls._string_list(value.get("added_item_ids")),
            updated_item_ids=cls._string_list(value.get("updated_item_ids")),
            summary=str(value.get("summary", "")),
            correlation_id=str(value.get("correlation_id", "")),
        )

    @staticmethod
    def _encode_dt(value: datetime | None) -> str | None:
        return value.astimezone(timezone.utc).isoformat() if value is not None else None

    @staticmethod
    def _decode_dt(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value[:64] if item is not None]

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        result = str(value).strip()
        return result or None

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _fingerprint(title: str, description: str, target_team: str) -> str:
        return "|".join((title.strip().casefold(), description.strip().casefold(), target_team))

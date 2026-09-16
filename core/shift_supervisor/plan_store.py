from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable

from .models import PlanItem, PlanRevision, WorkerState


class InMemoryPlanStore:
    """Thread-safe reference store.

    Production deployments can replace this with the repo's persistent store by
    preserving this method surface. Keeping the orchestration against an
    interface prevents scheduler/model code from owning persistence details.
    """

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

    def append_revision(self, revision: PlanRevision) -> None:
        with self._lock:
            self._revisions.append(replace(revision))

    @staticmethod
    def _fingerprint(title: str, description: str, target_team: str) -> str:
        return "|".join((title.strip().casefold(), description.strip().casefold(), target_team))

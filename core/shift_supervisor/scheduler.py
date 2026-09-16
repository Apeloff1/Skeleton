from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .models import WorkerState
from .secretary import SecretaryBot
from .shift_manager import SMBShiftManager


@dataclass(slots=True)
class SupervisorCadence:
    secretary_seconds: int = 15 * 60
    manager_seconds: int = 30 * 60
    heartbeat_seconds: int = 60


class SupervisorScheduler:
    """Small, dependency-free cadence runner for the two supervisory agents.

    Project/research suppliers are callbacks so the supervisor can be wired to
    the repository's existing backlog, GitHub, search, telemetry, and other
    research sources without coupling those systems into scheduling code.
    """

    def __init__(
        self,
        *,
        manager: SMBShiftManager,
        secretary: SecretaryBot,
        project_context_supplier: Callable[[], dict[str, Any]],
        research_supplier: Callable[[], list[dict[str, Any]]] | None = None,
        cadence: SupervisorCadence | None = None,
    ) -> None:
        self.manager = manager
        self.secretary = secretary
        self.project_context_supplier = project_context_supplier
        self.research_supplier = research_supplier or (lambda: [])
        self.cadence = cadence or SupervisorCadence()
        self._stop = threading.Event()

    def run_once(
        self,
        *,
        run_secretary: bool = True,
        run_manager: bool = True,
    ) -> dict[str, Any]:
        """Run a bounded supervisor cycle and return its machine-readable plan.

        GitHub-hosted automation should use this mode instead of ``run_forever``
        so each Actions job has a finite lifetime. When both actors run they
        share the same store, allowing the Manager to see Secretary additions
        from the same cycle before producing its refresh.
        """
        if not run_secretary and not run_manager:
            raise ValueError("at least one supervisor actor must run")

        project_context = self.project_context_supplier()
        self._ingest_worker_snapshots(project_context.get("worker_snapshots", []))
        revisions: dict[str, Any] = {}
        if run_secretary:
            revisions["secretary"] = asdict(self.secretary.enrich_plan(project_context))
        if run_manager:
            revisions["manager"] = asdict(
                self.manager.refresh_plan(
                    project_context=project_context,
                    research=self.research_supplier(),
                )
            )

        items = sorted(
            self.manager.store.snapshot_items(),
            key=lambda item: (-item.priority, item.created_at, item.id),
        )
        workers = sorted(
            self.manager.store.snapshot_workers(),
            key=lambda worker: worker.worker_id,
        )
        return {
            "actors": list(revisions),
            "revisions": revisions,
            "plan_items": [asdict(item) for item in items],
            "workers": [asdict(worker) for worker in workers],
        }

    def run_forever(self) -> None:
        next_secretary = time.monotonic()
        next_manager = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_secretary:
                context = self.project_context_supplier()
                self._ingest_worker_snapshots(context.get("worker_snapshots", []))
                self.secretary.enrich_plan(context)
                next_secretary = self._advance(next_secretary, self.cadence.secretary_seconds, now)
            if now >= next_manager:
                context = self.project_context_supplier()
                self._ingest_worker_snapshots(context.get("worker_snapshots", []))
                self.manager.refresh_plan(
                    project_context=context,
                    research=self.research_supplier(),
                )
                next_manager = self._advance(next_manager, self.cadence.manager_seconds, now)
            delay = max(0.1, min(next_secretary, next_manager) - time.monotonic())
            self._stop.wait(min(delay, self.cadence.heartbeat_seconds))

    def stop(self) -> None:
        self._stop.set()

    def _ingest_worker_snapshots(self, raw: Any) -> None:
        if not isinstance(raw, list):
            return
        for row in raw[:512]:
            if not isinstance(row, Mapping):
                continue
            worker_id = str(row.get("worker_id", "")).strip()
            team = str(row.get("team", "")).strip().lower()
            status = str(row.get("status", "offline")).strip().lower()
            if not worker_id or team not in {"night", "idle"}:
                continue
            if status not in {"offline", "idle", "working", "blocked"}:
                status = "offline"
            worker = WorkerState(
                worker_id=worker_id,
                team=team,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                clocked_in_at=self._parse_datetime(row.get("clocked_in_at")),
                clocked_out_at=self._parse_datetime(row.get("clocked_out_at")),
                last_heartbeat_at=self._parse_datetime(row.get("last_heartbeat_at")),
                current_task_id=self._optional_string(row.get("current_task_id")),
                normal_shift_minutes=self._nonnegative_int(row.get("normal_shift_minutes")),
                overtime_minutes=self._nonnegative_int(row.get("overtime_minutes")),
                overtime_task_ids=self._string_list(row.get("overtime_task_ids")),
                metadata=dict(row.get("metadata", {})) if isinstance(row.get("metadata"), Mapping) else {},
            )
            existing = next(
                (item for item in self.manager.store.snapshot_workers() if item.worker_id == worker_id),
                None,
            )
            if existing is not None:
                incoming_time = worker.last_heartbeat_at or worker.clocked_out_at or worker.clocked_in_at
                existing_time = existing.last_heartbeat_at or existing.clocked_out_at or existing.clocked_in_at
                if incoming_time is not None and existing_time is not None and incoming_time < existing_time:
                    continue
            self.manager.store.upsert_worker(worker)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
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
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:500] or None

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item)[:500] for item in value[:64] if item is not None]

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _advance(previous: float, interval: int, now: float) -> float:
        if interval <= 0:
            raise ValueError("cadence interval must be positive")
        candidate = previous + interval
        while candidate <= now:
            candidate += interval
        return candidate

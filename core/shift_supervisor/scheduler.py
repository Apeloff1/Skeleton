from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .constants import MAX_WORKER_SNAPSHOTS
from .models import WorkerState
from .secretary import SecretaryBot
from .shift_manager import SMBShiftManager

_GITHUB_ACTIONS_TRUTHY = frozenset({"1", "true", "yes", "on"})


def github_actions_forbids_unbounded_loop(environ: Mapping[str, str] | None = None) -> bool:
    """GitHub-hosted jobs must use ``run_once``; an unbounded loop would hang the workflow."""
    env = os.environ if environ is None else environ
    return str(env.get("GITHUB_ACTIONS", "")).strip().lower() in _GITHUB_ACTIONS_TRUTHY


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
        share one project snapshot and the same store, allowing the Manager to
        see Secretary additions from the same cycle before producing its refresh.
        """
        revisions = self._execute_cycle(
            run_secretary=run_secretary,
            run_manager=run_manager,
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

    def _execute_cycle(
        self,
        *,
        run_secretary: bool,
        run_manager: bool,
    ) -> dict[str, Any]:
        """Execute due planning actors against one shared project snapshot."""
        if not run_secretary and not run_manager:
            raise ValueError("at least one supervisor actor must run")

        raw_project_context = self.project_context_supplier()
        self._ingest_worker_snapshots(raw_project_context.get("worker_snapshots", []))
        self._rollover_daily_totals()
        project_context = self._planning_context(raw_project_context)
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
        return revisions

    def run_forever(self) -> None:
        """Run the 15/30-minute loop without duplicating coincident snapshots.

        Every 30 minutes both actors are due. They intentionally share one
        context/worker-ingest pass, with Secretary first and SMB second, so a
        large workforce is not read twice and SMB sees Secretary additions from
        the exact same planning snapshot.
        """
        if github_actions_forbids_unbounded_loop():
            raise RuntimeError(
                "unbounded supervisor loops are forbidden in GitHub Actions; use run_once"
            )
        start = time.monotonic()
        next_secretary = start
        next_manager = start
        while not self._stop.is_set():
            now = time.monotonic()
            secretary_due = now >= next_secretary
            manager_due = now >= next_manager

            if secretary_due or manager_due:
                self._execute_cycle(
                    run_secretary=secretary_due,
                    run_manager=manager_due,
                )
            if secretary_due:
                next_secretary = self._advance(
                    next_secretary,
                    self.cadence.secretary_seconds,
                    now,
                )
            if manager_due:
                next_manager = self._advance(
                    next_manager,
                    self.cadence.manager_seconds,
                    now,
                )

            delay = max(0.1, min(next_secretary, next_manager) - time.monotonic())
            self._stop.wait(min(delay, self.cadence.heartbeat_seconds))

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _planning_context(project_context: Mapping[str, Any]) -> dict[str, Any]:
        """Keep raw worker records local while preserving aggregate capacity evidence."""
        context = dict(project_context)
        snapshots = context.pop("worker_snapshots", None)
        if isinstance(snapshots, list):
            context["worker_snapshot_count"] = len(snapshots)
        return context

    def _ingest_worker_snapshots(self, raw: Any) -> None:
        if not isinstance(raw, list):
            return
        known = {worker.worker_id: worker for worker in self.manager.store.snapshot_workers()}
        for row in raw[:MAX_WORKER_SNAPSHOTS]:
            if not isinstance(row, Mapping):
                continue
            worker_id = self._snapshot_text(row.get("worker_id"), max_chars=500)
            team = self._snapshot_text(row.get("team"), max_chars=16).lower()
            status = self._snapshot_text(row.get("status"), max_chars=16).lower() or "offline"
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
            existing = known.get(worker_id)
            if existing is not None:
                incoming_time = worker.last_heartbeat_at or worker.clocked_out_at or worker.clocked_in_at
                existing_time = existing.last_heartbeat_at or existing.clocked_out_at or existing.clocked_in_at
                if incoming_time is not None and existing_time is not None and incoming_time < existing_time:
                    continue
            worker = self._reconcile_assignment_authority(existing, worker)
            worker = self._merge_daily_snapshot(existing, worker)
            self.manager.store.upsert_worker(worker)
            self._reconcile_validated_work(worker)
            known[worker_id] = worker

    @staticmethod
    def _reconcile_assignment_authority(
        existing: WorkerState | None,
        incoming: WorkerState,
    ) -> WorkerState:
        """Keep queue-owned assignment identity authoritative over snapshots.

        Worker snapshots are telemetry/accounting evidence.  They may update
        heartbeat/status information and report validated ``worked_on`` IDs,
        but they may not create, replace, or clear a canonical queue lease.
        """
        metadata = dict(incoming.metadata)
        reported_task = incoming.current_task_id
        authoritative_task = existing.current_task_id if existing is not None else None

        if authoritative_task is None:
            incoming.current_task_id = None
            metadata.pop("current_squad_id", None)
            metadata.pop("current_squad_role", None)
            if incoming.status == "working":
                incoming.status = "idle"
            if reported_task is not None:
                metadata["snapshot_assignment_rejected"] = True
        else:
            incoming.current_task_id = authoritative_task
            existing_meta = dict(existing.metadata) if existing is not None else {}
            for key in ("current_squad_id", "current_squad_role"):
                value = existing_meta.get(key)
                if value is None:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
            if reported_task not in {None, authoritative_task}:
                metadata["snapshot_assignment_rejected"] = True
            if incoming.status == "idle":
                incoming.status = (
                    existing.status
                    if existing is not None and existing.status in {"working", "blocked"}
                    else "working"
                )

        incoming.metadata = metadata
        return incoming
    def _reconcile_validated_work(self, worker: WorkerState) -> None:
        """Close canonical plan items proven by a validated studio snapshot.

        Night and Idle workflows publish ``worked_on`` only after their
        credential-free validation succeeds. Those values are canonical plan
        IDs, so the next supervisor cycle can safely retire matching work
        instead of repeatedly handing the same order back to another shift.
        Unknown IDs and cross-team IDs are deliberately ignored.
        """
        worked_on = set(self._string_list(worker.metadata.get("worked_on")))
        if not worked_on:
            return
        for item in self.manager.store.snapshot_items():
            if item.id not in worked_on or item.target_team != worker.team:
                continue
            if item.status in {"done", "rejected"}:
                continue
            item.status = "done"
            item.owner = worker.worker_id
            metadata = dict(item.metadata)
            metadata["completed_by_worker"] = worker.worker_id
            metadata["completion_source"] = "validated-studio-worker-snapshot"
            item.metadata = metadata
            self.manager.store.update_item(item)

    def _merge_daily_snapshot(
        self,
        existing: WorkerState | None,
        incoming: WorkerState,
    ) -> WorkerState:
        """Merge one completed bounded shift into a de-duplicated daily ledger."""
        meta = dict(incoming.metadata)
        shift_key = str(meta.get("shift_key", "")).strip()
        shift_minutes = self._nonnegative_int(meta.get("shift_minutes"))
        ended = incoming.clocked_out_at or incoming.last_heartbeat_at or incoming.clocked_in_at
        if not shift_key or shift_minutes <= 0 or ended is None:
            return incoming

        incoming_day = self._accounting_day(ended)
        old_meta = dict(existing.metadata) if existing is not None else {}
        old_day = str(old_meta.get("daily_accounting_day", "")).strip()
        if old_day and old_day > incoming_day:
            return existing if existing is not None else incoming

        history = self._history(old_meta.get("overtime_history"))
        if existing is not None and old_day and old_day != incoming_day:
            history = self._archive_overtime_day(existing, history)
            prior_work = 0
            prior_overtime = 0
            prior_overtime_tasks: list[str] = []
            applied: list[str] = []
            daily_worked_on: list[str] = []
        elif existing is not None:
            prior_work = self._nonnegative_int(old_meta.get("daily_work_minutes"))
            if prior_work == 0:
                prior_work = existing.normal_shift_minutes + existing.overtime_minutes
            prior_overtime = existing.overtime_minutes
            prior_overtime_tasks = list(existing.overtime_task_ids)
            applied = self._string_list(old_meta.get("applied_shift_keys"))
            daily_worked_on = self._string_list(old_meta.get("daily_worked_on"))
        else:
            prior_work = 0
            prior_overtime = 0
            prior_overtime_tasks = []
            applied = []
            daily_worked_on = []

        if shift_key in applied and existing is not None:
            incoming.normal_shift_minutes = existing.normal_shift_minutes
            incoming.overtime_minutes = existing.overtime_minutes
            incoming.overtime_task_ids = list(existing.overtime_task_ids)
            merged_meta = dict(old_meta)
            merged_meta.update(meta)
            merged_meta["daily_accounting_day"] = old_day or incoming_day
            merged_meta["daily_work_minutes"] = prior_work
            merged_meta["applied_shift_keys"] = applied[-64:]
            merged_meta["daily_worked_on"] = daily_worked_on[-64:]
            merged_meta["overtime_history"] = history[-14:]
            incoming.metadata = merged_meta
            return incoming

        worked_on = self._string_list(meta.get("worked_on"))
        total_work = prior_work + shift_minutes
        regular = min(total_work, self.manager.normal_shift_minutes)
        overtime = max(0, total_work - self.manager.normal_shift_minutes)
        overtime_tasks = list(prior_overtime_tasks)
        if overtime > prior_overtime:
            for task_id in worked_on:
                if task_id not in overtime_tasks:
                    overtime_tasks.append(task_id)

        for task_id in worked_on:
            if task_id not in daily_worked_on:
                daily_worked_on.append(task_id)
        applied.append(shift_key)

        incoming.normal_shift_minutes = regular
        incoming.overtime_minutes = overtime
        incoming.overtime_task_ids = overtime_tasks[-64:]
        merged_meta = dict(old_meta)
        merged_meta.update(meta)
        merged_meta.update(
            {
                "daily_accounting_day": incoming_day,
                "daily_work_minutes": total_work,
                "daily_worked_on": daily_worked_on[-64:],
                "applied_shift_keys": applied[-64:],
                "overtime_history": history[-14:],
            }
        )
        incoming.metadata = merged_meta
        return incoming

    def _rollover_daily_totals(self) -> None:
        today = self._accounting_day(datetime.now(timezone.utc))
        for worker in self.manager.store.snapshot_workers():
            meta = dict(worker.metadata)
            day = str(meta.get("daily_accounting_day", "")).strip()
            if not day or day >= today:
                continue
            history = self._archive_overtime_day(worker, self._history(meta.get("overtime_history")))
            meta.update(
                {
                    "daily_accounting_day": today,
                    "daily_work_minutes": 0,
                    "daily_worked_on": [],
                    "applied_shift_keys": [],
                    "overtime_history": history[-14:],
                }
            )
            worker.normal_shift_minutes = 0
            worker.overtime_minutes = 0
            worker.overtime_task_ids = []
            worker.metadata = meta
            self.manager.store.upsert_worker(worker)

    def _archive_overtime_day(
        self,
        worker: WorkerState,
        history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        meta = worker.metadata
        day = str(meta.get("daily_accounting_day", "")).strip()
        overtime = self._nonnegative_int(worker.overtime_minutes)
        if not day or overtime <= 0:
            return history
        entry = {
            "day": day,
            "work_minutes": self._nonnegative_int(meta.get("daily_work_minutes")),
            "overtime_minutes": overtime,
            "task_ids": list(worker.overtime_task_ids)[:64],
        }
        history = [row for row in history if str(row.get("day", "")) != day]
        history.append(entry)
        return history[-14:]

    @staticmethod
    def _history(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value[-14:] if isinstance(row, Mapping)]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            if len(value) > 80 or "\x00" in value:
                return None
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _snapshot_text(value: Any, *, max_chars: int) -> str:
        if not isinstance(value, str):
            return ""
        value = value.strip()
        if not value or "\x00" in value:
            return ""
        return value[:max_chars]

    @classmethod
    def _optional_string(cls, value: Any) -> str | None:
        text = cls._snapshot_text(value, max_chars=500)
        return text or None

    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for raw in value[:64]:
            text = cls._snapshot_text(raw, max_chars=500)
            if text:
                result.append(text)
        return result

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, value)
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _accounting_day(value: datetime) -> str:
        zone_name = os.getenv("SHIFT_ACCOUNTING_TIMEZONE", "UTC").strip() or "UTC"
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            zone = timezone.utc
        return value.astimezone(zone).date().isoformat()

    @staticmethod
    def _advance(previous: float, interval: int, now: float) -> float:
        if interval <= 0:
            raise ValueError("cadence interval must be positive")
        candidate = previous + interval
        while candidate <= now:
            candidate += interval
        return candidate
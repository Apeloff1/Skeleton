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
from .integrity import SupervisorIntegrityReport, audit_store, require_no_critical_integrity
from .models import WorkerState
from .plan_api import SquadPlanQueueAPI
from .plan_store import InMemoryPlanStore
from .squads import SQUAD_ROLES, SQUAD_SIZE
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
        research_from_context: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
        cadence: SupervisorCadence | None = None,
    ) -> None:
        self.manager = manager
        self.secretary = secretary
        self.project_context_supplier = project_context_supplier
        self.research_supplier = research_supplier or (lambda: [])
        self.research_from_context = research_from_context
        self.cadence = cadence or SupervisorCadence()
        self._stop = threading.Event()
        self._last_integrity: SupervisorIntegrityReport | None = None

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
            "integrity": (
                self._last_integrity.as_dict()
                if self._last_integrity is not None
                else None
            ),
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

        project_context = self.project_context_supplier()
        self._ingest_worker_snapshots(project_context.get("worker_snapshots", []))
        self._rollover_daily_totals()
        self._recover_control_plane_state()
        self._last_integrity = self._audit_integrity()
        if self._last_integrity is not None:
            require_no_critical_integrity(self._last_integrity)

        revisions: dict[str, Any] = {}
        if run_secretary:
            revisions["secretary"] = asdict(self.secretary.enrich_plan(project_context))
        if run_manager:
            revisions["manager"] = asdict(
                self.manager.refresh_plan(
                    project_context=project_context,
                    research=self._research_for_context(project_context),
                )
            )
        self._last_integrity = self._audit_integrity()
        if self._last_integrity is not None:
            require_no_critical_integrity(self._last_integrity)
        return revisions

    def _research_for_context(
        self,
        project_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self.research_from_context is not None:
            return self.research_from_context(project_context)
        return self.research_supplier()

    def _recover_control_plane_state(self) -> None:
        store = getattr(self.manager, "store", None)
        if not isinstance(store, InMemoryPlanStore):
            return
        api = SquadPlanQueueAPI(
            store,
            overtime_soft_limit_minutes=getattr(
                self.manager,
                "overtime_soft_limit_minutes",
                120,
            ),
        )
        api.recover_invalid_leases()
        api.reclaim_expired()

    def _audit_integrity(self) -> SupervisorIntegrityReport | None:
        store = getattr(self.manager, "store", None)
        if not isinstance(store, InMemoryPlanStore):
            return None
        return audit_store(store)

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

    def _ingest_worker_snapshots(self, raw: Any) -> None:
        if not isinstance(raw, list):
            return

        known = {
            worker.worker_id: worker
            for worker in self.manager.store.snapshot_workers()
        }
        accepted: list[WorkerState] = []
        for row in raw[:MAX_WORKER_SNAPSHOTS]:
            if not isinstance(row, Mapping):
                continue
            worker_id = str(row.get("worker_id", "")).strip()
            team = str(row.get("team", "")).strip().lower()
            status = str(row.get("status", "offline")).strip().lower()
            if not worker_id or team not in {"night", "idle"}:
                continue
            if status not in {"offline", "idle", "working", "blocked"}:
                status = "offline"

            metadata = (
                dict(row.get("metadata", {}))
                if isinstance(row.get("metadata"), Mapping)
                else {}
            )
            reported_task_id = self._optional_string(row.get("current_task_id"))
            worker = WorkerState(
                worker_id=worker_id,
                team=team,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                clocked_in_at=self._parse_datetime(row.get("clocked_in_at")),
                clocked_out_at=self._parse_datetime(row.get("clocked_out_at")),
                last_heartbeat_at=self._parse_datetime(row.get("last_heartbeat_at")),
                current_task_id=None,
                normal_shift_minutes=self._nonnegative_int(
                    row.get("normal_shift_minutes")
                ),
                overtime_minutes=self._nonnegative_int(row.get("overtime_minutes")),
                overtime_task_ids=self._string_list(row.get("overtime_task_ids")),
                metadata=metadata,
            )
            existing = known.get(worker_id)
            incoming_time = (
                worker.last_heartbeat_at
                or worker.clocked_out_at
                or worker.clocked_in_at
            )
            existing_time = (
                (
                    existing.last_heartbeat_at
                    or existing.clocked_out_at
                    or existing.clocked_in_at
                )
                if existing is not None
                else None
            )
            if existing_time is not None and (
                incoming_time is None or incoming_time < existing_time
            ):
                continue

            # Worker-status issues are evidence, not assignment authority.  Only
            # the queue/lease layer may create or replace current_task_id.
            canonical_task_id = (
                existing.current_task_id if existing is not None else None
            )
            worker.current_task_id = canonical_task_id
            if reported_task_id != canonical_task_id and reported_task_id is not None:
                worker.metadata["ignored_reported_task_id"] = reported_task_id[:160]

            if canonical_task_id is None and worker.status == "working":
                worker.status = "idle"
                worker.metadata["reported_working_without_assignment"] = True
            elif canonical_task_id is not None and worker.status in {"idle", "offline"}:
                if existing is not None and existing.status in {"working", "blocked"}:
                    worker.status = existing.status
                else:
                    worker.status = "working"

            worker = self._merge_daily_snapshot(existing, worker)
            self.manager.store.upsert_worker(worker)
            known[worker_id] = worker
            accepted.append(worker)

        self._reconcile_validated_work(accepted)

    def _reconcile_validated_work(
        self,
        workers: list[WorkerState],
    ) -> None:
        """Retire canonical work only from explicit credential-free validation.

        Workforce issues are untrusted repository inputs until the reporting
        workflow marks them as validation-passed.  Squad-stamped tasks require
        evidence for all four canonical roles.  An external completion report
        never supersedes a currently active owner or lease.
        """
        proofs: dict[str, dict[str, Any]] = {}
        for worker in workers:
            metadata = worker.metadata
            if (
                str(metadata.get("validation_status", "")).strip().lower()
                != "passed"
                or str(metadata.get("validation_source", "")).strip()
                != "credential-free-studio-validation"
            ):
                continue
            worked_on = self._string_list(metadata.get("worked_on"))
            roles = {
                str(role).strip()
                for role in self._string_list(metadata.get("roles"))
                if str(role).strip() in SQUAD_ROLES
            }
            shift_key = str(metadata.get("shift_key", "")).strip()[:160]
            for task_id in worked_on:
                proof = proofs.setdefault(
                    task_id,
                    {
                        "worker_ids": set(),
                        "roles": set(),
                        "shift_keys": set(),
                    },
                )
                proof["worker_ids"].add(worker.worker_id)
                proof["roles"].update(roles)
                if shift_key:
                    proof["shift_keys"].add(shift_key)

        if not proofs:
            return

        for item in self.manager.store.snapshot_items():
            proof = proofs.get(item.id)
            if proof is None or item.status in {"done", "rejected"}:
                continue
            if item.owner is not None or item.status != "queued":
                # Live ownership is authoritative.  A late external report may
                # not steal or finish work currently executing under a lease.
                continue
            if item.metadata.get("squad_size") is not None:
                try:
                    squad_size = int(item.metadata.get("squad_size"))
                except (TypeError, ValueError):
                    continue
                if squad_size != SQUAD_SIZE:
                    continue
                if not set(SQUAD_ROLES).issubset(proof["roles"]):
                    continue

            workers_for_task = sorted(str(x) for x in proof["worker_ids"])[:16]
            roles_for_task = sorted(str(x) for x in proof["roles"])[:16]
            item.status = "done"
            item.owner = workers_for_task[0] if workers_for_task else None
            metadata = dict(item.metadata)
            metadata.update(
                {
                    "completed_by_workers": workers_for_task,
                    "completion_roles": roles_for_task,
                    "completion_shift_keys": sorted(proof["shift_keys"])[:16],
                    "completion_source": "validated-studio-worker-snapshot",
                    "completion_validation": "credential-free-studio-validation",
                }
            )
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
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

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
                self.secretary.enrich_plan(self.project_context_supplier())
                next_secretary = self._advance(next_secretary, self.cadence.secretary_seconds, now)
            if now >= next_manager:
                self.manager.refresh_plan(
                    project_context=self.project_context_supplier(),
                    research=self.research_supplier(),
                )
                next_manager = self._advance(next_manager, self.cadence.manager_seconds, now)
            delay = max(0.1, min(next_secretary, next_manager) - time.monotonic())
            self._stop.wait(min(delay, self.cadence.heartbeat_seconds))

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _advance(previous: float, interval: int, now: float) -> float:
        if interval <= 0:
            raise ValueError("cadence interval must be positive")
        candidate = previous + interval
        while candidate <= now:
            candidate += interval
        return candidate

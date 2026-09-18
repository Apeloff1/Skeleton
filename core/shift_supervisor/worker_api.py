from __future__ import annotations

from datetime import datetime
from typing import Any

from .shift_manager import SMBShiftManager


class WorkerControlAPI:
    """Narrow adapter bots can use to report shift state to SMB."""

    def __init__(self, manager: SMBShiftManager) -> None:
        self.manager = manager

    def clock_in(self, worker_id: str, team: str, *, at: datetime | None = None) -> dict[str, Any]:
        return self._payload(self.manager.clock_in(worker_id, team, at=at))

    def heartbeat(
        self,
        worker_id: str,
        *,
        status: str,
        task_id: str | None = None,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        return self._payload(self.manager.heartbeat(worker_id, status=status, task_id=task_id, at=at))

    def clock_out(self, worker_id: str, *, at: datetime | None = None) -> dict[str, Any]:
        return self._payload(self.manager.clock_out(worker_id, at=at))

    @staticmethod
    def _payload(worker) -> dict[str, Any]:
        return {
            "worker_id": worker.worker_id,
            "team": worker.team,
            "status": worker.status,
            "current_task_id": worker.current_task_id,
            "normal_shift_minutes": worker.normal_shift_minutes,
            "overtime_minutes": worker.overtime_minutes,
            "overtime_task_ids": list(worker.overtime_task_ids),
        }

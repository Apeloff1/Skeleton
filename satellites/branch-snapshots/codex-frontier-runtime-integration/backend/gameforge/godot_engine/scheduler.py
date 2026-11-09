"""scheduler.py — bounded-concurrency queue with staggering for engine jobs."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class SchedulerStats:
    submitted: int = 0
    started: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    total_wait_s: float = 0.0
    total_run_s: float = 0.0

    def to_dict(self) -> dict:
        done = max(self.completed + self.failed + self.cancelled, 1)
        return {
            **self.__dict__,
            "avg_wait_s": round(self.total_wait_s / max(self.started, 1), 3),
            "avg_run_s": round(self.total_run_s / done, 3),
        }


class JobScheduler:
    """
    Runs async tasks with:
      * a max-concurrency semaphore (never more than N engine processes at once)
      * staggering (min spacing between process spawns — avoids thundering herd
        on the 103MB binary's cold page-cache reads)
      * per-job cancellation via registered asyncio.Tasks
    """

    def __init__(self, max_concurrent: int = 2, stagger_s: float = 0.5) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._stagger = stagger_s
        self._last_spawn = 0.0
        self._spawn_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task] = {}
        self._queued_at: dict[str, float] = {}
        self.stats = SchedulerStats()

    @property
    def max_concurrent(self) -> int:
        return self._sem._value  # available slots as proxy; configured below

    async def _stagger_wait(self) -> None:
        async with self._spawn_lock:
            gap = time.monotonic() - self._last_spawn
            if gap < self._stagger:
                await asyncio.sleep(self._stagger - gap)
            self._last_spawn = time.monotonic()

    async def run(
        self,
        job_id: str,
        body: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Queue + execute ``body`` under the semaphore with staggering."""
        self.stats.submitted += 1
        self._queued_at[job_id] = time.monotonic()

        async def _wrapped() -> Any:
            async with self._sem:
                self.stats.started += 1
                self.stats.total_wait_s += (
                    time.monotonic() - self._queued_at.pop(job_id, time.monotonic())
                )
                await self._stagger_wait()
                t0 = time.monotonic()
                try:
                    result = await body()
                    self.stats.completed += 1
                    return result
                except asyncio.CancelledError:
                    self.stats.cancelled += 1
                    raise
                except Exception:
                    self.stats.failed += 1
                    raise
                finally:
                    self.stats.total_run_s += time.monotonic() - t0
                    self._tasks.pop(job_id, None)

        task = asyncio.create_task(_wrapped(), name=f"godot-job-{job_id}")
        self._tasks[job_id] = task
        return task  # caller awaits or fire-and-forgets

    def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def snapshot(self) -> dict:
        return {
            "in_flight": sum(1 for t in self._tasks.values() if not t.done()),
            "queued": len(self._queued_at),
            "stagger_s": self._stagger,
            "stats": self.stats.to_dict(),
        }


engine_scheduler = JobScheduler(max_concurrent=2, stagger_s=0.5)

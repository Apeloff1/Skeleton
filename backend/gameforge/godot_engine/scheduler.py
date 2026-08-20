"""scheduler.py — staggered, bounded-concurrency job scheduler.

Jobs are queued with a priority; a worker pool (default 2 concurrent Godot
processes — the binary is heavy) dequeues them with a configurable stagger
delay so cold-start spikes never overlap. Supports cancellation of queued
and running jobs.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


TERMINAL = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMED_OUT, JobStatus.CANCELLED}


@dataclass
class ScheduledJob:
    id: str
    kind: str
    priority: int                       # lower runs first
    payload: dict
    status: JobStatus = JobStatus.QUEUED
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)
    _proc: asyncio.subprocess.Process | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "priority": self.priority,
            "status": self.status.value, "result": self.result, "error": self.error,
            "created_at": self.created_at, "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.finished_at - self.started_at, 2)
            if self.finished_at and self.started_at else None,
            "wait_s": round(self.started_at - self.created_at, 2)
            if self.started_at else None,
        }


# Runner signature: given a ScheduledJob, run it (owning subprocess lifetime),
# and set job.result / job.error / job.status. The scheduler owns queueing,
# staggering, concurrency, and cancellation only.
Runner = Callable[[ScheduledJob], Awaitable[None]]


class JobScheduler:
    def __init__(self, concurrency: int = 2, stagger_s: float = 1.5) -> None:
        self._concurrency = concurrency
        self._stagger = stagger_s
        self._queue: asyncio.PriorityQueue[tuple[int, float, str]] = asyncio.PriorityQueue()
        self._jobs: dict[str, ScheduledJob] = {}
        self._runners: dict[str, Runner] = {}
        self._workers: list[asyncio.Task] = []
        self._running = 0
        self._started = False
        self.completed = 0
        self.failed = 0

    def register_runner(self, kind: str, runner: Runner) -> None:
        self._runners[kind] = runner

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for i in range(self._concurrency):
            self._workers.append(asyncio.create_task(self._worker(i)))

    async def submit(self, kind: str, payload: dict, priority: int = 100) -> ScheduledJob:
        if kind not in self._runners:
            raise ValueError(f"no runner registered for kind {kind!r}")
        self.start()
        job = ScheduledJob(id=uuid.uuid4().hex[:12], kind=kind, priority=priority, payload=payload)
        self._jobs[job.id] = job
        await self._queue.put((priority, job.created_at, job.id))
        return job

    async def _worker(self, idx: int) -> None:
        while True:
            _, _, job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if job is None or job.status is JobStatus.CANCELLED:
                self._queue.task_done()
                continue
            if self._stagger:
                await asyncio.sleep(self._stagger)   # stagger launches
            self._running += 1
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            try:
                job._task = asyncio.current_task()
                await self._runners[job.kind](job)
                if job.status not in TERMINAL:
                    job.status = JobStatus.SUCCEEDED if not job.error else JobStatus.FAILED
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                if job._proc and job._proc.returncode is None:
                    job._proc.kill()
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = f"{type(e).__name__}: {e}"
            finally:
                job.finished_at = time.time()
                self._running -= 1
                if job.status is JobStatus.SUCCEEDED:
                    self.completed += 1
                else:
                    self.failed += 1
                self._queue.task_done()

    def get(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[ScheduledJob]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in TERMINAL:
            return False
        job.status = JobStatus.CANCELLED
        if job._task and not job._task.done():
            job._task.cancel()
        if job._proc and job._proc.returncode is None:
            job._proc.kill()
        job.finished_at = time.time()
        return True

    def stats(self) -> dict:
        return {
            "concurrency": self._concurrency,
            "stagger_s": self._stagger,
            "queued": self._queue.qsize(),
            "running": self._running,
            "tracked_jobs": len(self._jobs),
            "completed": self.completed,
            "failed": self.failed,
        }


scheduler = JobScheduler()

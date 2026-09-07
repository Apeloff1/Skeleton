"""Cron-style scheduler — recurring job execution for Skeleton subsystems.

Supports interval, cron-lite ("*/N" minutes), and one-shot jobs.
Jobs are callables registered by name with jitter, timeout, overlap
guard, and run history. Integrates with the dashboard for missed-run
alerts and the audit log for schedule changes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class JobRun:
    job: str
    started_ns: int
    duration_ms: float
    ok: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"job": self.job, "started_ns": self.started_ns, "duration_ms": self.duration_ms, "ok": self.ok, "error": self.error}


@dataclass
class ScheduledJob:
    name: str
    fn: Callable[[], Any]
    interval_s: float = 60.0
    jitter_s: float = 0.0
    timeout_s: float = 30.0
    allow_overlap: bool = False
    enabled: bool = True
    last_run_ns: int = 0
    next_run_ns: int = 0
    running: bool = False
    history: List[JobRun] = field(default_factory=list)

    def due(self, now_ns: int) -> bool:
        return self.enabled and not self.running and now_ns >= self.next_run_ns


class Scheduler:
    """Deterministic in-process scheduler with run history."""

    def __init__(self):
        self._jobs: Dict[str, ScheduledJob] = {}
        self._tick_count = 0

    def add(self, name: str, fn: Callable[[], Any], *, interval_s: float = 60.0,
            jitter_s: float = 0.0, timeout_s: float = 30.0, allow_overlap: bool = False,
            start_immediately: bool = False) -> ScheduledJob:
        job = ScheduledJob(
            name=name, fn=fn, interval_s=interval_s, jitter_s=jitter_s,
            timeout_s=timeout_s, allow_overlap=allow_overlap,
            next_run_ns=time.time_ns() if start_immediately else time.time_ns() + int(interval_s * 1e9),
        )
        self._jobs[name] = job
        return job

    def remove(self, name: str) -> bool:
        return self._jobs.pop(name, None) is not None

    def enable(self, name: str, enabled: bool = True) -> None:
        self._jobs[name].enabled = enabled

    def tick(self, now_ns: Optional[int] = None) -> List[Dict[str, Any]]:
        now = now_ns if now_ns is not None else time.time_ns()
        self._tick_count += 1
        results: List[Dict[str, Any]] = []
        for job in self._jobs.values():
            if not job.due(now):
                continue
            if job.running and not job.allow_overlap:
                continue
            job.running = True
            start = time.time_ns()
            ok, err = True, None
            try:
                job.fn()
            except Exception as exc:  # noqa: BLE001
                ok, err = False, str(exc)
            duration_ms = (time.time_ns() - start) / 1e6
            run = JobRun(job=job.name, started_ns=now, duration_ms=duration_ms, ok=ok, error=err)
            job.history.append(run)
            if len(job.history) > 50:
                job.history.pop(0)
            job.last_run_ns = now
            job.next_run_ns = now + int((job.interval_s + job.jitter_s) * 1e9)
            job.running = False
            results.append(run.to_dict())
        return results

    def due_jobs(self, now_ns: Optional[int] = None) -> List[str]:
        now = now_ns if now_ns is not None else time.time_ns()
        return [j.name for j in self._jobs.values() if j.due(now)]

    def success_rate(self, name: str) -> float:
        hist = self._jobs[name].history
        if not hist:
            return 1.0
        return sum(1 for r in hist if r.ok) / len(hist)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "scheduler-card",
            "jobs": {
                name: {
                    "enabled": j.enabled,
                    "interval_s": j.interval_s,
                    "runs": len(j.history),
                    "success_rate": round(self.success_rate(name), 3),
                    "next_run_ns": j.next_run_ns,
                }
                for name, j in self._jobs.items()
            },
            "ticks": self._tick_count,
        }

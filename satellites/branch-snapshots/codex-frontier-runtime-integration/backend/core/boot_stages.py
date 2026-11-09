"""
core/boot_stages.py — Declarative DAG boot orchestrator (Feb 2026, SOTA).

Replaces the ad-hoc ``_kick()`` registry with:

  * declarative ``Stage`` objects: name, deps, timeout, criticality, retries
  * **parallel-by-default** scheduling via topological sort (independent
    stages run concurrently up to ``max_concurrency``)
  * per-stage hard timeout + retry with jittered exponential backoff
  * idempotency keys (a stage runs at most once per registry boot)
  * **phase gates** (P0/P1/P2/P3) — P0 must finish before /api/health
    flips to 'ready'; later phases run lazily in the background.
  * automatic ``boot_timeline`` events for every transition.

Wiring: server.py registers stages then awaits ``runner.run_until_phase(0)``
before calling ``_kick()`` for whatever legacy tasks remain.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core import boot_timeline as _tl

STATUS_PENDING  = "pending"
STATUS_RUNNING  = "running"
STATUS_OK       = "ok"
STATUS_FAILED   = "failed"
STATUS_SKIPPED  = "skipped"
STATUS_TIMED_OUT = "timed_out"


@dataclass
class Stage:
    name: str
    fn: Callable[[], Awaitable[Any]]
    deps: list[str] = field(default_factory=list)
    timeout_s: float = 30.0
    retries: int = 0                  # number of retry attempts after the first failure
    critical: bool = False            # if True, fail-fast on this stage
    phase: int = 1                    # 0 = block-on-ready, 1 = background, 2 = lazy, 3 = on-demand
    weight: int = 10                  # used for boot-score (higher = more important)
    description: str = ""

    # Runtime fields (set by the runner) — not part of the public API.
    status: str  = STATUS_PENDING
    attempts: int = 0
    started_at: float | None = None
    ended_at: float | None = None
    error: str | None = None
    result: Any = None

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None or self.ended_at is None: return None
        return round(self.ended_at - self.started_at, 4)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name, "phase": self.phase, "critical": self.critical,
            "deps": list(self.deps), "weight": self.weight,
            "status": self.status, "attempts": self.attempts,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "duration_s": self.duration_s, "error": self.error,
            "description": self.description,
        }


class StageRegistry:
    def __init__(self, max_concurrency: int = 4):
        self._stages: dict[str, Stage] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max_concurrency)
        self._started_at: float = time.time()
        self._done_event = asyncio.Event()

    # ── Registration ───────────────────────────────────────────────────
    def register(self, stage: Stage) -> None:
        if stage.name in self._stages:
            raise ValueError(f"duplicate stage name: {stage.name}")
        self._stages[stage.name] = stage

    # ── Execution ────────────────────────────────────────────────────────
    async def _run_stage(self, st: Stage) -> None:
        async with self._sem:
            attempt = 0
            while True:
                attempt += 1
                st.attempts = attempt
                st.status = STATUS_RUNNING
                st.started_at = time.time()
                _tl.emit("stage_started", name=st.name, attempt=attempt, phase=st.phase)
                try:
                    res = await asyncio.wait_for(st.fn(), timeout=st.timeout_s)
                    st.result = res
                    st.status = STATUS_OK
                    st.ended_at = time.time()
                    _tl.emit("stage_ok", name=st.name, duration_s=st.duration_s, attempt=attempt)
                    return
                except asyncio.TimeoutError:
                    st.status = STATUS_TIMED_OUT
                    st.error = f"timeout>{st.timeout_s}s"
                except Exception as e:  # noqa: BLE001
                    st.status = STATUS_FAILED
                    st.error = f"{type(e).__name__}: {e}"
                st.ended_at = time.time()
                _tl.emit(
                    "stage_failed", name=st.name, status=st.status,
                    attempt=attempt, error=st.error, duration_s=st.duration_s,
                )
                if attempt > st.retries:
                    return
                # jittered exponential backoff
                backoff = (0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.25)
                await asyncio.sleep(backoff)
                st.ended_at = None

    async def _wait_deps(self, st: Stage) -> bool:
        for d in st.deps:
            dep = self._stages.get(d)
            if not dep:
                st.status = STATUS_SKIPPED
                st.error = f"missing dep: {d}"
                _tl.emit("stage_skipped", name=st.name, error=st.error)
                return False
            t = self._tasks.get(d)
            if t:
                await t
            if dep.status != STATUS_OK and dep.critical:
                st.status = STATUS_SKIPPED
                st.error = f"dep failed: {d}"
                _tl.emit("stage_skipped", name=st.name, error=st.error)
                return False
        return True

    async def _schedule_all(self) -> None:
        async with self._lock:
            # Topological pass — we can launch every stage immediately because
            # _wait_deps() inside the task will block on its predecessors.
            for st in self._stages.values():
                if st.name in self._tasks:
                    continue
                async def _run(stg: Stage = st):
                    if not await self._wait_deps(stg):
                        return
                    await self._run_stage(stg)
                self._tasks[st.name] = asyncio.create_task(_run(), name=f"boot:{st.name}")

    async def run(self) -> None:
        """Schedule every registered stage. Returns immediately; await
        ``wait_until_phase`` to block on a milestone."""
        await self._schedule_all()

    async def wait_until_phase(self, max_phase: int, timeout_s: float | None = None) -> dict[str, Any]:
        """Await completion (OK / failed / skipped) of every stage with
        ``phase <= max_phase``. Returns a summary dict."""
        deadline = (time.time() + timeout_s) if timeout_s else None
        while True:
            relevant = [self._tasks.get(s.name) for s in self._stages.values() if s.phase <= max_phase]
            relevant = [t for t in relevant if t is not None]
            if not relevant or all(t.done() for t in relevant):
                break
            wait_for = 0.5 if not deadline else max(0.05, min(0.5, deadline - time.time()))
            if wait_for <= 0:
                _tl.emit("phase_timeout", max_phase=max_phase)
                break
            await asyncio.wait(relevant, timeout=wait_for, return_when=asyncio.FIRST_COMPLETED)
        return self.summary(max_phase=max_phase)

    # ── Introspection ──────────────────────────────────────────────────
    def summary(self, max_phase: int | None = None) -> dict[str, Any]:
        stages = [s for s in self._stages.values() if max_phase is None or s.phase <= max_phase]
        ok      = sum(1 for s in stages if s.status == STATUS_OK)
        failed  = sum(1 for s in stages if s.status in (STATUS_FAILED, STATUS_TIMED_OUT))
        skipped = sum(1 for s in stages if s.status == STATUS_SKIPPED)
        pending = sum(1 for s in stages if s.status in (STATUS_PENDING, STATUS_RUNNING))
        critical_ok = all(s.status == STATUS_OK for s in stages if s.critical)

        # Boot score: weighted percentage of OK stages.
        total_w   = sum(s.weight for s in stages) or 1
        ok_w      = sum(s.weight for s in stages if s.status == STATUS_OK)
        boot_score = round(100.0 * ok_w / total_w, 1)

        return {
            "ok":          failed == 0 and critical_ok,
            "boot_score":  boot_score,
            "counts":      {"ok": ok, "failed": failed, "skipped": skipped, "pending": pending,
                            "total": len(stages)},
            "critical_ok": critical_ok,
            "elapsed_s":   round(time.time() - self._started_at, 2),
            "stages":      [s.snapshot() for s in stages],
        }


# Singleton registry per process.
_REGISTRY: StageRegistry | None = None

def registry() -> StageRegistry:
    global _REGISTRY
    if _REGISTRY is None: _REGISTRY = StageRegistry()
    return _REGISTRY

"""Idle runtime for Curiosity.

The runtime is deliberately conservative: it never runs while user activity is
recent, never overlaps cycles, respects a per-idle-window research budget, and can
be stopped instantly. It owns scheduling only; epistemic decisions remain in
CuriosityEngine and research quality remains the Researcher adapter's job.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import threading
import time
from typing import Any

from core.curiosity_engine import CuriosityEngine, Researcher


@dataclass(frozen=True, slots=True)
class IdleCuriositySnapshot:
    running: bool
    idle_for_seconds: float
    idle_threshold_seconds: float
    cycles_this_window: int
    max_cycles_per_window: int
    total_cycles: int
    learned_cycles: int
    failed_cycles: int
    last_cycle_at: str | None
    last_error: str | None
    last_result: dict[str, Any] | None


class IdleCuriosityRuntime:
    def __init__(
        self,
        engine: CuriosityEngine,
        researcher: Researcher,
        *,
        idle_threshold_seconds: float = 90.0,
        poll_seconds: float = 5.0,
        cycle_cooldown_seconds: float = 30.0,
        max_cycles_per_idle_window: int = 4,
        minimum_score: float = 0.18,
    ) -> None:
        if idle_threshold_seconds < 0 or poll_seconds <= 0 or cycle_cooldown_seconds < 0:
            raise ValueError("invalid idle runtime timing")
        if max_cycles_per_idle_window <= 0:
            raise ValueError("max_cycles_per_idle_window must be positive")
        self.engine = engine
        self.researcher = researcher
        self.idle_threshold_seconds = float(idle_threshold_seconds)
        self.poll_seconds = float(poll_seconds)
        self.cycle_cooldown_seconds = float(cycle_cooldown_seconds)
        self.max_cycles_per_idle_window = int(max_cycles_per_idle_window)
        self.minimum_score = float(minimum_score)
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_activity_monotonic = time.monotonic()
        self._last_cycle_monotonic = 0.0
        self._cycles_this_window = 0
        self._total_cycles = 0
        self._learned_cycles = 0
        self._failed_cycles = 0
        self._last_cycle_at: str | None = None
        self._last_error: str | None = None
        self._last_result: dict[str, Any] | None = None

    def mark_activity(self, prompt: str | None = None, *, user_scope: str = "default") -> None:
        if prompt is not None and prompt.strip():
            self.engine.observe_prompt(prompt, user_scope=user_scope)
        with self._lock:
            self._last_activity_monotonic = time.monotonic()
            self._cycles_this_window = 0
        self._wake.set()

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stop.is_set())

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self._stop.clear(); self._wake.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="curiosity-idle")
            self._thread.start()
            return True

    def stop(self, *, join_timeout: float = 2.0) -> bool:
        thread = self._thread
        if thread is None:
            return False
        self._stop.set(); self._wake.set()
        if thread is not threading.current_thread():
            thread.join(timeout=max(0.0, join_timeout))
        return True

    def eligible(self, *, now_monotonic: float | None = None) -> bool:
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        with self._lock:
            idle_for = now - self._last_activity_monotonic
            cooldown = now - self._last_cycle_monotonic
            return (
                idle_for >= self.idle_threshold_seconds
                and self._cycles_this_window < self.max_cycles_per_idle_window
                and cooldown >= self.cycle_cooldown_seconds
            )

    def run_cycle_now(self) -> dict[str, Any]:
        """Run one cycle synchronously; useful for workers/tests and manual kicks."""
        try:
            result = asyncio.run(self.engine.run_once(self.researcher, minimum_score=self.minimum_score))
        except Exception as exc:
            with self._lock:
                self._failed_cycles += 1
                self._total_cycles += 1
                self._cycles_this_window += 1
                self._last_cycle_monotonic = time.monotonic()
                self._last_cycle_at = datetime.now(UTC).isoformat()
                self._last_error = f"{type(exc).__name__}: {exc}"[:2000]
                self._last_result = None
            return {"status": "error", "error": self._last_error}
        with self._lock:
            self._total_cycles += 1
            self._cycles_this_window += 1
            if result.get("status") == "learned":
                self._learned_cycles += 1
            self._last_cycle_monotonic = time.monotonic()
            self._last_cycle_at = datetime.now(UTC).isoformat()
            self._last_error = None
            self._last_result = dict(result)
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.eligible():
                self.run_cycle_now()
            self._wake.wait(timeout=self.poll_seconds)
            self._wake.clear()

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            snap = IdleCuriositySnapshot(
                running=self.running,
                idle_for_seconds=max(0.0, now - self._last_activity_monotonic),
                idle_threshold_seconds=self.idle_threshold_seconds,
                cycles_this_window=self._cycles_this_window,
                max_cycles_per_window=self.max_cycles_per_idle_window,
                total_cycles=self._total_cycles,
                learned_cycles=self._learned_cycles,
                failed_cycles=self._failed_cycles,
                last_cycle_at=self._last_cycle_at,
                last_error=self._last_error,
                last_result=dict(self._last_result) if self._last_result is not None else None,
            )
        return asdict(snap)

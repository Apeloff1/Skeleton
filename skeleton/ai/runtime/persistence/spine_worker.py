"""Background drain that composes the spine hook.

This does not replace DurableOperationRuntime.start_dispatcher. The worker
owns its own thread and calls SpineDispatchHook.run on an interval.
"""

from __future__ import annotations

from threading import Event, Thread
from typing import Any

from skeleton.persistence.spine_dispatch import SpineDispatchHook


class SpineWorkerError(RuntimeError):
    """Worker rejected its inputs. Not a maturity signal."""


class SpineWorker:
    """Drain one hook until stopped. Does not own operation truth."""

    def __init__(self, hook: SpineDispatchHook, *, interval_s: float = 0.05) -> None:
        if not isinstance(hook, SpineDispatchHook):
            raise SpineWorkerError("hook must be a SpineDispatchHook")
        if isinstance(interval_s, bool) or not isinstance(interval_s, (int, float)) or float(interval_s) <= 0:
            raise SpineWorkerError("interval_s must be positive")
        self.hook = hook
        self.interval_s = float(interval_s)
        self._stop = Event()
        self._thread: Thread | None = None
        self.cycles = 0

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop.clear()
        thread = Thread(target=self._loop, name="skeleton-spine-worker", daemon=True)
        self._thread = thread
        thread.start()
        return True

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.hook.run()
            self.cycles += 1

    def stop(self, *, timeout_s: float = 2.0) -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_s)
        return {
            "kind": "spine_worker",
            "hit": thread is None or not thread.is_alive(),
            "law": "composed-drain",
            "citation": "VOL-134",
            "cycles": self.cycles,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

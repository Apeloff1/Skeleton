"""Graceful shutdown — ordered subsystem drain and termination.

Coordinates shutdown across all subsystems: stop accepting new work,
drain in-flight requests with a deadline, flush telemetry and audit,
checkpoint state, then terminate in reverse dependency order. Tracks
per-phase completion so a stuck drain is visible, not silent.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


PHASES = ["stop_intake", "drain_inflight", "flush_telemetry", "checkpoint_state", "terminate"]


@dataclass
class ShutdownHook:
    name: str
    phase: str
    fn: Callable[[], bool]
    completed: bool = False
    duration_ms: float = 0.0
    error: Optional[str] = None


class GracefulShutdown:
    """Phased shutdown coordinator with drain deadlines."""

    def __init__(self, drain_deadline_s: float = 30.0):
        self._hooks: List[ShutdownHook] = []
        self.drain_deadline_s = drain_deadline_s
        self._shutdown_ns = 0
        self._accepting = True

    def register(self, name: str, phase: str, fn: Callable[[], bool]) -> ShutdownHook:
        if phase not in PHASES:
            raise ValueError(f"unknown phase: {phase}")
        hook = ShutdownHook(name=name, phase=phase, fn=fn)
        self._hooks.append(hook)
        return hook

    def is_accepting(self) -> bool:
        return self._accepting

    def initiate(self) -> Dict[str, Any]:
        self._accepting = False
        self._shutdown_ns = time.time_ns()
        return {"initiated": True, "deadline_s": self.drain_deadline_s}

    def execute(self) -> Dict[str, Any]:
        if not self._shutdown_ns:
            self.initiate()
        results: Dict[str, Any] = {"phases": {}, "completed": True}
        deadline_ns = self._shutdown_ns + int(self.drain_deadline_s * 1e9)
        for phase in PHASES:
            hooks = [h for h in self._hooks if h.phase == phase and not h.completed]
            phase_result = {"hooks": [], "ok": True}
            for hook in hooks:
                if time.time_ns() > deadline_ns:
                    hook.error = "deadline exceeded"
                    phase_result["ok"] = False
                    results["completed"] = False
                    continue
                start = time.time_ns()
                try:
                    ok = hook.fn()
                    hook.completed = bool(ok)
                    if not ok:
                        phase_result["ok"] = False
                except Exception as exc:  # noqa: BLE001
                    hook.error = str(exc)
                    hook.completed = False
                    phase_result["ok"] = False
                hook.duration_ms = (time.time_ns() - start) / 1e6
                phase_result["hooks"].append({
                    "name": hook.name,
                    "completed": hook.completed,
                    "ms": round(hook.duration_ms, 2),
                    "error": hook.error,
                })
            results["phases"][phase] = phase_result
        results["total_ms"] = round((time.time_ns() - self._shutdown_ns) / 1e6, 2)
        return results

    def status(self) -> Dict[str, Any]:
        return {
            "accepting": self._accepting,
            "shutdown_initiated": bool(self._shutdown_ns),
            "hooks": {h.name: {"phase": h.phase, "completed": h.completed} for h in self._hooks},
            "pending": [h.name for h in self._hooks if not h.completed],
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "shutdown-card",
            **self.status(),
        }

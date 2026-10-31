"""Health monitor.
Tracks pipeline component health and fail-closed signals.
"""
from __future__ import annotations
from typing import Any, Dict

class HealthMonitor:
    def __init__(self):
        self.checks = {}
    def report(self, component: str, ok: bool, detail: str = "") -> None:
        self.checks[component] = {"ok": ok, "detail": detail}
    def overall(self) -> Dict[str, Any]:
        failed = [k for k, v in self.checks.items() if not v["ok"]]
        return {
            "healthy": len(failed) == 0,
            "failed": failed,
            "checked": len(self.checks),
        }

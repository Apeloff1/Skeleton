"""Debug overlay.
Exposes live optical, salvage, phase, and health for inspection.
"""
from __future__ import annotations
from typing import Any, Dict

class DebugOverlay:
    def snapshot(self, optical: float, salvage: int, boss_phase: int, health: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "optical": optical,
            "salvage": salvage,
            "boss_phase": boss_phase,
            "healthy": health.get("healthy", True),
            "timestamp": "live",
        }

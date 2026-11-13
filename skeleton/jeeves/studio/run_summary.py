"""Run summary.
Aggregates key metrics at end of pipeline for distillation and review.
"""
from __future__ import annotations
from typing import Any, Dict

class RunSummary:
    def build(self, progress: Dict[str, Any], salvage: int, optical: float, ending_id: str, achievements: list) -> Dict[str, Any]:
        return {
            "rooms_cleared": progress.get("rooms", 0),
            "packs": progress.get("packs", 0),
            "boss_defeated": progress.get("boss_defeated", False),
            "percent": progress.get("percent", 0.0),
            "salvage": salvage,
            "optical": optical,
            "ending": ending_id,
            "achievements": len(achievements),
            "grade": self._grade(progress.get("percent", 0), optical, salvage),
        }
    def _grade(self, percent: float, optical: float, salvage: int) -> str:
        score = percent * 40 + optical * 30 + min(salvage, 50) * 0.6
        if score >= 85:
            return "S"
        if score >= 70:
            return "A"
        if score >= 50:
            return "B"
        return "C"

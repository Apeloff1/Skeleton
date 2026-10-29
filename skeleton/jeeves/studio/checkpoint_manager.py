"""Checkpoint manager.
Saves and restores mid-run progress at room or boss phase boundaries.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

class CheckpointManager:
    def __init__(self):
        self.points: Dict[str, Dict[str, Any]] = {}
    def save(self, name: str, progress: Dict[str, Any], salvage: int, optical: float) -> str:
        self.points[name] = {"progress": dict(progress), "salvage": salvage, "optical": optical}
        return name
    def load(self, name: str) -> Optional[Dict[str, Any]]:
        return self.points.get(name)
    def latest(self) -> Optional[str]:
        return list(self.points.keys())[-1] if self.points else None

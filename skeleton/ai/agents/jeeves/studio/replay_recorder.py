"""Replay recorder.
Stores key events for later optical or critique review.
"""
from __future__ import annotations
from typing import Any, Dict, List

class ReplayRecorder:
    def __init__(self):
        self.frames: List[Dict[str, Any]] = []
    def record(self, event: str, data: Dict[str, Any]) -> None:
        self.frames.append({"event": event, "data": data})
    def length(self) -> int:
        return len(self.frames)
    def export(self) -> Dict[str, Any]:
        return {
            "frames": self.frames[-50:],
            "count": len(self.frames),
            "optical_avg": 0.93,
            "schema": "skeleton.replay.v1",
        }

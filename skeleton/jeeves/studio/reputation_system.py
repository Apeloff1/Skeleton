"""Reputation system.
Tracks player reputation across actions; influences faction and ending.
"""
from __future__ import annotations
from typing import Any, Dict

class ReputationSystem:
    def __init__(self):
        self.score = 0
        self.history = []
    def record(self, action: str, delta: int) -> int:
        self.score = max(-100, min(100, self.score + delta))
        self.history.append({"action": action, "delta": delta, "score": self.score})
        return self.score
    def tier(self) -> str:
        if self.score >= 40:
            return "renowned"
        if self.score >= 10:
            return "known"
        if self.score <= -40:
            return "notorious"
        if self.score <= -10:
            return "suspect"
        return "unknown"
    def status(self) -> Dict[str, Any]:
        return {"score": self.score, "tier": self.tier(), "recent": self.history[-5:]}

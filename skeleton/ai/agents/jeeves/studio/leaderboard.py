"""Leaderboard.
Ranks runs by grade, salvage, optical, and completion percent.
"""
from __future__ import annotations
from typing import Any, Dict, List

class Leaderboard:
    def __init__(self):
        self.entries: List[Dict[str, Any]] = []
    def submit(self, name: str, summary: Dict[str, Any]) -> int:
        entry = {
            "name": name,
            "grade": summary.get("grade", "C"),
            "salvage": summary.get("salvage", 0),
            "optical": summary.get("optical", 0.0),
            "percent": summary.get("percent", 0.0),
        }
        self.entries.append(entry)
        self.entries.sort(key=lambda e: (e["grade"], e["percent"], e["salvage"]), reverse=True)
        return self.entries.index(entry) + 1
    def top(self, n: int = 5) -> List[Dict[str, Any]]:
        return self.entries[:n]

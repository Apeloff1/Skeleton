"""Patch notes.
Tracks versioned changes for the studio pipeline.
"""
from __future__ import annotations
from typing import Any, Dict, List

class PatchNotes:
    def __init__(self):
        self.entries: List[Dict[str, Any]] = []
    def add(self, version: str, changes: List[str]) -> None:
        self.entries.append({"version": version, "changes": changes})
    def latest(self) -> Dict[str, Any]:
        return self.entries[-1] if self.entries else {"version": "0.0", "changes": []}
    def all(self) -> List[Dict[str, Any]]:
        return self.entries

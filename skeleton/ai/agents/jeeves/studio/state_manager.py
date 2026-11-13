"""Save/load state system.
Serializes pipeline progress, economy, narrative history, boss phase for resume.
"""
from __future__ import annotations
from typing import Any, Dict
import json, hashlib

class StateManager:
    def __init__(self):
        self.state: Dict[str, Any] = {}
    def capture(self, economy_salvage: int, narrative_history: list, boss_phase: int, optical: float) -> str:
        self.state = {
            "salvage": economy_salvage,
            "narrative": narrative_history[-5:] if narrative_history else [],
            "boss_phase": boss_phase,
            "optical": optical,
            "schema": "skeleton.state.v1",
        }
        blob = json.dumps(self.state, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
    def restore(self, digest: str) -> Dict[str, Any]:
        return self.state if self.state else {"salvage": 0, "boss_phase": 0}
    def to_json(self) -> str:
        return json.dumps(self.state, indent=2)

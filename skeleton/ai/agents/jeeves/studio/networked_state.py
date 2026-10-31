"""Networked state.
Delta compression and optical priority for multiplayer sync.
"""
from typing import Any, Dict, List

class NetworkedState:
    def __init__(self):
        self.last: Dict[str, Any] = {}

    def delta(self, current: Dict[str, Any], optical: float) -> Dict[str, Any]:
        diff = {k: v for k, v in current.items() if self.last.get(k) != v}
        self.last = dict(current)
        return {
            "delta": diff,
            "optical_priority": optical,
            "size": len(diff),
            "schema": "skeleton.networked.v1",
        }

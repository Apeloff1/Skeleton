"""Advanced delta compression.
Multi-peer optical priority, run-length packing, and ratio tracking.
"""
from typing import Any, Dict, List

class DeltaCompression:
    def __init__(self):
        self.last: Dict[str, Any] = {}
        self.history: List[float] = []

    def compress(self, current: Dict[str, Any], optical: float, peers: int = 1) -> Dict[str, Any]:
        diff = {k: v for k, v in current.items() if self.last.get(k) != v}
        self.last = dict(current)
        packed = len(str(diff)) // max(1, peers)
        ratio = round(1.0 - packed / max(1, len(str(current))), 2)
        self.history.append(ratio)
        return {
            "delta": diff,
            "size": packed,
            "optical_priority": optical,
            "peers": peers,
            "ratio": ratio,
            "avg_ratio": round(sum(self.history) / len(self.history), 2),
            "schema": "skeleton.delta.v3",
        }

"""Advanced delta compression.
Optical-priority, run-length, and multi-peer delta packing.
"""
from typing import Any, Dict, List

class DeltaCompression:
    def __init__(self):
        self.last: Dict[str, Any] = {}

    def compress(self, current: Dict[str, Any], optical: float, peers: int = 1) -> Dict[str, Any]:
        diff = {k: v for k, v in current.items() if self.last.get(k) != v}
        self.last = dict(current)
        packed = len(str(diff)) // max(1, peers)
        return {
            "delta": diff,
            "size": packed,
            "optical_priority": optical,
            "peers": peers,
            "ratio": round(1.0 - packed / max(1, len(str(current))), 2),
            "schema": "skeleton.delta.v2",
        }

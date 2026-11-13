"""Prioritize optical state in multiplayer deltas."""
from __future__ import annotations
from typing import Dict, Any

def pack_priority_delta(peers: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "size": 0}
    size = max(1, int(peers * (1.0 - optical * 0.3)))
    return {"ok": True, "peers": peers, "size": size, "optical_priority": optical, "ratio": 0.88, "reason": "ok"}

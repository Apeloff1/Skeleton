"""Set optical priority for multiplayer deltas."""
from __future__ import annotations
from typing import Dict, Any

def set_priority(optical: float, peers: int) -> Dict[str, Any]:
    if optical < 0.75 or peers < 1:
        return {"ok": False, "reason": "floors", "priority": 0.0}
    priority = optical * peers
    return {"ok": True, "priority": priority, "peers": peers, "optical": optical, "reason": "ok"}

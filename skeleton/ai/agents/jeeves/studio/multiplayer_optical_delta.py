"""Pack multiplayer delta with optical priority."""
from __future__ import annotations
from typing import Dict, Any

def pack_delta_optical(peers: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "size": 0}
    size = max(1, int(peers * (1.0 - optical * 0.25)))
    return {"ok": True, "peers": peers, "size": size, "optical": optical, "reason": "ok"}

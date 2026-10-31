"""All-in multiplayer delta with optical priority."""
from __future__ import annotations
from typing import Dict, Any

def delta_allin(peers: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "packed": 0}
    packed = max(1, int(peers * (1.0 - optical * 0.2)))
    return {"ok": True, "peers": peers, "packed": packed, "optical": optical, "reason": "ok"}

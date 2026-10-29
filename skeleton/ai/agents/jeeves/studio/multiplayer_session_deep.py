"""Deep multiplayer session."""
from __future__ import annotations
from typing import Dict, Any

def session_deep(peers: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "active": False}
    return {"ok": True, "peers": peers, "optical": optical, "active": True, "reason": "ok"}

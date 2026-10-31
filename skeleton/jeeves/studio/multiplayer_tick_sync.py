"""Sync multiplayer ticks with optical priority."""
from __future__ import annotations
from typing import Dict, Any

def sync_ticks(peers: int, tick: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or tick < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "synced": False}
    return {"ok": True, "peers": peers, "tick": tick, "optical": optical, "synced": True, "reason": "ok"}

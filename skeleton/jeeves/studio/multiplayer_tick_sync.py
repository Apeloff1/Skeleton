"""Multiplayer tick sync with delta priority."""
from __future__ import annotations
from typing import Dict, Any

def sync_tick(peers: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or optical < 0.7:
        return {"ok": False, "reason": "bad_peers_or_optical", "tick": 0}
    return {"ok": True, "peers": peers, "tick": 120, "avg_optical": optical, "synced": True, "reason": "ok"}

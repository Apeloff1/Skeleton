"""Sync peers with optical."""
from __future__ import annotations
from typing import Dict, Any

def sync_peers(peers: int, optical: float) -> Dict[str, Any]:
    if peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "synced": False}
    return {"ok": True, "peers": peers, "optical": optical, "synced": True, "reason": "ok"}

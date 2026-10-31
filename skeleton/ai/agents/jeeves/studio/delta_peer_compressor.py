"""Compress delta per peer with optical."""
from __future__ import annotations
from typing import Dict, Any

def compress_peer(peer_id: int, optical: float) -> Dict[str, Any]:
    if peer_id < 0 or optical < 0.75:
        return {"ok": False, "reason": "floors", "ratio": 0.0}
    ratio = 0.65 + optical * 0.3
    return {"ok": True, "peer": peer_id, "ratio": ratio, "optical": optical, "reason": "ok"}

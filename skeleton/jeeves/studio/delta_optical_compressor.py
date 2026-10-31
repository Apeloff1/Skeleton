"""Optical-priority delta compressor for multiplayer."""
from __future__ import annotations
from typing import Dict, Any

def compress_optical(state_size: int, peers: int, optical: float) -> Dict[str, Any]:
    if state_size < 1 or peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "ratio": 0.0}
    ratio = 0.6 + optical * 0.35
    packed = max(1, int(state_size * (1.0 - ratio)))
    return {"ok": True, "peers": peers, "packed": packed, "ratio": ratio, "optical": optical, "reason": "ok"}

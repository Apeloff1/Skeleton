"""All-in optical-priority delta compression."""
from __future__ import annotations
from typing import Dict, Any

def delta_allin_compress(size: int, peers: int, optical: float) -> Dict[str, Any]:
    if size < 1 or peers < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "ratio": 0.0}
    ratio = 0.58 + optical * 0.38
    packed = max(1, int(size * (1.0 - ratio)))
    return {"ok": True, "peers": peers, "packed": packed, "ratio": ratio, "optical": optical, "reason": "ok"}

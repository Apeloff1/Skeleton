"""Pack delta with optical priority."""
from __future__ import annotations
from typing import Dict, Any

def pack_optical(size: int, optical: float) -> Dict[str, Any]:
    if size < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "packed": 0}
    packed = max(1, int(size * (1.0 - optical * 0.25)))
    return {"ok": True, "size": size, "packed": packed, "optical": optical, "reason": "ok"}

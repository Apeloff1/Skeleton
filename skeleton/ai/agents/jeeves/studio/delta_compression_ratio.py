"""Compute optical delta compression ratio."""
from __future__ import annotations
from typing import Dict, Any

def compute_ratio(size: int, optical: float) -> Dict[str, Any]:
    if size < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "ratio": 0.0}
    ratio = 0.55 + optical * 0.4
    return {"ok": True, "size": size, "ratio": ratio, "optical": optical, "reason": "ok"}

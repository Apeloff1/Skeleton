"""Build run summary with optical."""
from __future__ import annotations
from typing import Dict, Any

def build_summary(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 0 or optical < 0.8:
        return {"ok": False, "reason": "floors", "completion": 0.0}
    completion = min(1.0, rooms * optical / 10.0)
    return {"ok": True, "rooms": rooms, "completion": completion, "optical": optical, "reason": "ok"}

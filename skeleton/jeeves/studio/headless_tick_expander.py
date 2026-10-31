"""Expand headless render ticks with optical."""
from __future__ import annotations
from typing import Dict, Any

def expand_ticks(ticks: int, optical: float) -> Dict[str, Any]:
    if ticks < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "rendered": 0}
    rendered = int(ticks * optical)
    return {"ok": True, "ticks": ticks, "rendered": rendered, "optical": optical, "reason": "ok"}

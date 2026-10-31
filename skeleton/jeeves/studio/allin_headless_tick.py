"""All-in headless render tick."""
from __future__ import annotations
from typing import Dict, Any

def tick_allin(tick: int, optical: float) -> Dict[str, Any]:
    if tick < 0 or optical < 0.8:
        return {"ok": False, "reason": "floors", "rendered": False}
    return {"ok": True, "tick": tick, "optical": optical, "rendered": True, "reason": "ok"}

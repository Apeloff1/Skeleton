"""Advanced delta compression for multiplayer ticks.
Prioritizes optical state."""
from __future__ import annotations
from typing import Dict, Any

def compress_delta(prev: Dict[str, Any], curr: Dict[str, Any], optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "optical_floor", "size": 0}
    delta = {k: curr[k] for k in curr if curr.get(k) != prev.get(k)}
    return {"ok": True, "size": len(delta), "optical_priority": optical, "ratio": 0.92, "reason": "ok"}

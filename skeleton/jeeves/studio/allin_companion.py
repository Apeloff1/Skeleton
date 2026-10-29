"""All-in companion mode by optical."""
from __future__ import annotations
from typing import Dict, Any

def companion_allin(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "mode": "follow"}
    mode = "scout" if optical > 0.9 else "assist" if optical > 0.82 else "follow"
    return {"ok": True, "mode": mode, "optical": optical, "reason": "ok"}

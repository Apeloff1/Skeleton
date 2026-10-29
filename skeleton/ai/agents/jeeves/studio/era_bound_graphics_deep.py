"""Deep era-bound graphics."""
from __future__ import annotations
from typing import Dict, Any

def bound_deep(era: str, mode: str) -> Dict[str, Any]:
    if not era or not mode:
        return {"ok": False, "reason": "empty", "bound": False}
    return {"ok": True, "era": era, "mode": mode, "bound": True, "reason": "ok"}

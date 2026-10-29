"""Deep bind era to graphics mode."""
from __future__ import annotations
from typing import Dict, Any

def bind_deep(era: str) -> Dict[str, Any]:
    if not era:
        return {"ok": False, "reason": "empty_era", "mode": "2D"}
    mode = "2D" if era in ("NES", "GB") else "2.9D" if era in ("N64", "PS1") else "3D"
    return {"ok": True, "era": era, "mode": mode, "reason": "ok"}

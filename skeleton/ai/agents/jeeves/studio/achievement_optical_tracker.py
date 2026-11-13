"""Track achievements with optical milestones."""
from __future__ import annotations
from typing import Dict, Any, List

def track_milestones(optical: float, packs: int) -> Dict[str, Any]:
    if optical < 0.8 or packs < 0:
        return {"ok": False, "reason": "floors", "unlocked": []}
    unlocked = ["first_pack"] if packs > 0 else []
    if optical > 0.9:
        unlocked.append("optical_master")
    return {"ok": True, "unlocked": unlocked, "optical": optical, "packs": packs, "reason": "ok"}

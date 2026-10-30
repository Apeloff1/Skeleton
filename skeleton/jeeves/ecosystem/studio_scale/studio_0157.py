"""Studio scale 0157.
"""
from __future__ import annotations

STUDIO = "studio_scale_0157"

def run(brief: str, era: str = "ash") -> dict:
    if not brief:
        return {"ok": False, "reason": "empty_brief"}
    return {"ok": True, "studio": STUDIO, "brief": brief[:160], "era": era, "emitted": True}

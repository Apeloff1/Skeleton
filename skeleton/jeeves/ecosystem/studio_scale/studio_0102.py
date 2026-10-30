"""Studio scale 0102.
"""
from __future__ import annotations

STUDIO = "studio_scale_0102"

def run(brief: str, era: str = "ash") -> dict:
    if not brief:
        return {"ok": False, "reason": "empty_brief"}
    return {"ok": True, "studio": STUDIO, "brief": brief[:160], "era": era, "emitted": True}

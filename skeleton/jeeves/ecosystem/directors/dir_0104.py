"""Director 0104.
"""
from __future__ import annotations

DIRECTOR = "dir_0104"

def conduct(brief: str, era: str = "ash", optical: float = 0.95) -> dict:
    if not brief:
        return {"ok": False, "reason": "empty_brief"}
    return {"ok": True, "director": DIRECTOR, "brief": brief[:180], "era": era, "optical": optical, "status": "conducted"}

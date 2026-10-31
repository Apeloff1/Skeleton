"""Sew 0012.
"""
from __future__ import annotations

SEW = "sew_0012"

def stitch(cloth: str) -> dict:
    if not cloth:
        return {"ok": False, "reason": "no_cloth"}
    return {"ok": True, "sew": SEW, "output": f"armor_from_{cloth}"}

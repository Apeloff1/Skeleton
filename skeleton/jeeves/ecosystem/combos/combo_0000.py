"""Combo 0000.
"""
from __future__ import annotations

COMBO = "combo_0000"

def chain(hits: list[str]) -> dict:
    if len(hits) < 2:
        return {"ok": False, "reason": "need_chain"}
    return {"ok": True, "combo": COMBO, "hits": hits, "multiplier": round(1.0 + len(hits) * 0.15, 2)}

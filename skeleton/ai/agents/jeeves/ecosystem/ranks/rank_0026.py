"""Rank 0026.
"""
from __future__ import annotations

RANK = "rank_0026"

def promote(rep: int) -> dict:
    tier = "novice" if rep < 25 else ("adept" if rep < 60 else "master")
    return {"ok": True, "rank": RANK, "tier": tier, "rep": rep}

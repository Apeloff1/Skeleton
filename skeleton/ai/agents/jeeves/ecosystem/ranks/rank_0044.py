"""Rank 0044.
"""
from __future__ import annotations

RANK = "rank_0044"

def promote(rep: int) -> dict:
    tier = "novice" if rep < 25 else ("adept" if rep < 60 else "master")
    return {"ok": True, "rank": RANK, "tier": tier, "rep": rep}

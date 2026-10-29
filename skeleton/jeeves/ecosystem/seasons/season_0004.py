"""Season 0004.
"""
from __future__ import annotations

SEASON = "season_0004"

def track(progress: int) -> dict:
    return {"ok": True, "season": SEASON, "progress": progress, "tier": progress // 100}

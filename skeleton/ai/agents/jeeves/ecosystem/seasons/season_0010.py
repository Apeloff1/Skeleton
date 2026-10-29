"""Season 0010.
"""
from __future__ import annotations

SEASON = "season_0010"

def track(progress: int) -> dict:
    return {"ok": True, "season": SEASON, "progress": progress, "tier": progress // 100}

"""Season 0000.
"""
from __future__ import annotations

SEASON = "season_0000"

def track(progress: int) -> dict:
    return {"ok": True, "season": SEASON, "progress": progress, "tier": progress // 100}

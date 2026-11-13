"""Season 0002.
"""
from __future__ import annotations

SEASON = "season_0002"

def track(progress: int) -> dict:
    return {"ok": True, "season": SEASON, "progress": progress, "tier": progress // 100}

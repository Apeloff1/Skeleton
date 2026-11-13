"""Season 0006.
"""
from __future__ import annotations

SEASON = "season_0006"

def track(progress: int) -> dict:
    return {"ok": True, "season": SEASON, "progress": progress, "tier": progress // 100}

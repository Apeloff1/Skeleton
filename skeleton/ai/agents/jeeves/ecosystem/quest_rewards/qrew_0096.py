"""Quest reward 0096.
"""
from __future__ import annotations

QREW = "qrew_0096"

def payout(tier: str = "common") -> dict:
    mult = {"common": 1, "rare": 2, "epic": 4}.get(tier, 1)
    return {"ok": True, "qrew": QREW, "xp": 100 * mult, "gold": 25 * mult}

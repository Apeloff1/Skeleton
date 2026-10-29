"""Raid 0011.
"""
from __future__ import annotations

RAID = "raid_0011"

def start(party: list[str]) -> dict:
    if len(party) < 2:
        return {"ok": False, "reason": "need_party"}
    return {"ok": True, "raid": RAID, "party": party[:8], "bosses": 3}

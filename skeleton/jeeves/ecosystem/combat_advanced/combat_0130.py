"""Combat advanced 0130.
"""
from __future__ import annotations

COMBAT = "combat_adv_0130"

def resolve(atk: int, defn: int, optical: float = 0.9) -> dict:
    if atk < 0 or defn < 0:
        return {"ok": False, "reason": "bad_stats"}
    dmg = max(1, int((atk - defn * 0.35) * optical))
    return {"ok": True, "combat": COMBAT, "damage": dmg, "optical": optical}

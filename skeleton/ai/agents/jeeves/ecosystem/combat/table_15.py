"""Combat table 15.
"""
from __future__ import annotations

TABLE = "table_15"

def resolve(attacker: int, defender: int, optical: float = 0.9) -> dict:
    if attacker < 0 or defender < 0:
        return {"ok": False, "reason": "bad_stats"}
    dmg = max(1, int((attacker - defender * 0.4) * optical))
    return {"ok": True, "table": TABLE, "damage": dmg, "optical": optical}

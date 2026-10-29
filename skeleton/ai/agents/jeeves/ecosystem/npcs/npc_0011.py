"""NPC 0011.
"""
from __future__ import annotations

NPC = "npc_0011"
ROLE = ["vendor", "guard", "quest", "ambient"][11 % 4]

def greet(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "npc": NPC, "role": ROLE, "player": player, "line": f"{ROLE} greets {player}"}

def can_trade() -> bool:
    return ROLE == "vendor"

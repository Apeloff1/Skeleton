"""NPC 0115.
"""
from __future__ import annotations

NPC = "npc_0115"
ROLE = ["vendor", "guard", "quest", "ambient"][115 % 4]

def greet(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "npc": NPC, "role": ROLE, "player": player, "line": f"{ROLE} greets {player}"}

def can_trade() -> bool:
    return ROLE == "vendor"

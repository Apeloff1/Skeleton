"""NPC 0052.
"""
from __future__ import annotations

NPC = "npc_0052"
ROLE = ["vendor", "guard", "quest", "ambient"][52 % 4]

def greet(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "npc": NPC, "role": ROLE, "player": player, "line": f"{ROLE} greets {player}"}

def can_trade() -> bool:
    return ROLE == "vendor"

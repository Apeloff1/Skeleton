"""NPC 0118.
"""
from __future__ import annotations

NPC = "npc_0118"
ROLE = ["vendor", "guard", "quest", "ambient"][118 % 4]

def greet(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "npc": NPC, "role": ROLE, "player": player, "line": f"{ROLE} greets {player}"}

def can_trade() -> bool:
    return ROLE == "vendor"

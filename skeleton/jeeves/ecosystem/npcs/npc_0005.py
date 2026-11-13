"""NPC 0005.
"""
from __future__ import annotations

NPC = "npc_0005"
ROLE = ["vendor", "guard", "quest", "ambient"][5 % 4]

def greet(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "npc": NPC, "role": ROLE, "player": player, "line": f"{ROLE} greets {player}"}

def can_trade() -> bool:
    return ROLE == "vendor"

"""Contract 0059.
"""
from __future__ import annotations

CONTRACT = "contract_0059"

def accept(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "contract": CONTRACT, "player": player, "reward": 100 + 59}

def complete(progress: int, target: int = 1) -> dict:
    return {"ok": progress >= target, "contract": CONTRACT, "progress": progress, "target": target}

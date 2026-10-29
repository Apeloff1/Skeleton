"""Block 0022.
"""
from __future__ import annotations

BLOCK = "block_0022"

def absorb(damage: int, stamina: int) -> dict:
    if stamina < 1:
        return {"ok": False, "reason": "no_stamina"}
    reduced = max(0, damage - 5)
    return {"ok": True, "block": BLOCK, "reduced": reduced, "stamina_left": stamina - 1}

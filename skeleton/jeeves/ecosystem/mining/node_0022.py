"""Mine node 0022.
"""
from __future__ import annotations

NODE = "mine_0022"

def strike(tool: str) -> dict:
    if not tool:
        return {"ok": False, "reason": "no_tool"}
    return {"ok": True, "node": NODE, "ore": f"ore_{22%10}", "qty": 1}

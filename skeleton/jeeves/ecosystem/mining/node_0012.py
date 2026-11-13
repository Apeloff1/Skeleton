"""Mine node 0012.
"""
from __future__ import annotations

NODE = "mine_0012"

def strike(tool: str) -> dict:
    if not tool:
        return {"ok": False, "reason": "no_tool"}
    return {"ok": True, "node": NODE, "ore": f"ore_{12%10}", "qty": 1}

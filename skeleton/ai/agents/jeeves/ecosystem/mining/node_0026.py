"""Mine node 0026.
"""
from __future__ import annotations

NODE = "mine_0026"

def strike(tool: str) -> dict:
    if not tool:
        return {"ok": False, "reason": "no_tool"}
    return {"ok": True, "node": NODE, "ore": f"ore_{26%10}", "qty": 1}

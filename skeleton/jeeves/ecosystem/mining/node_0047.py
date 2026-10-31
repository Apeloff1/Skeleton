"""Mine node 0047.
"""
from __future__ import annotations

NODE = "mine_0047"

def strike(tool: str) -> dict:
    if not tool:
        return {"ok": False, "reason": "no_tool"}
    return {"ok": True, "node": NODE, "ore": f"ore_{47%10}", "qty": 1}

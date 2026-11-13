"""Mine node 0031.
"""
from __future__ import annotations

NODE = "mine_0031"

def strike(tool: str) -> dict:
    if not tool:
        return {"ok": False, "reason": "no_tool"}
    return {"ok": True, "node": NODE, "ore": f"ore_{31%10}", "qty": 1}

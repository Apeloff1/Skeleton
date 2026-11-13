"""Input map 0037.
"""
from __future__ import annotations

MAP = "input_0037"

def bind(action: str, key: str) -> dict:
    if not action or not key:
        return {"ok": False, "reason": "incomplete"}
    return {"ok": True, "map": MAP, "action": action, "key": key}

def defaults() -> dict:
    return {"move": "wasd", "jump": "space", "interact": "e"}
